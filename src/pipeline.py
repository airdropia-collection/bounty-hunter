"""
Bounty Hunter Pipeline Orchestrator.

Scrapes bounties from all platforms, deduplicates against state,
downloads contract source, runs AI vulnerability analysis,
applies doubt-driven review, and creates GitHub Issues for
high-confidence findings.

Usage:
    python -m src.pipeline --dry-run true
    python -m src.pipeline --platform immunefi --max-bounties 5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.analyzers.contract_downloader import ContractDownloader
from src.analyzers.vuln_detector import VulnerabilityDetector
from src.scrapers.base import Bounty
from src.scrapers.code4rena import Code4renaScraper
from src.scrapers.dework import DeworkScraper
from src.scrapers.immunefi import ImmunefiScraper
from src.scrapers.issuehunt import IssueHuntScraper
from src.scrapers.sherlock import SherlockScraper
from src.utils import state_manager
from src.utils.github_client import GitHubClient
from src.utils.logger import get_logger, silence_noisy_libs
from src.utils.state import State
from src.utils.telegram import get_notifier

log = get_logger("pipeline")

# ──────────────────────────────────────────────────────────────────── #
# VERIFIED-PLATFORMS-ONLY POLICY (user directive 2026-07-17)
# Only these TWO escrow platforms are scraped by default.
# Random GitHub issues claiming cash rewards are IGNORED unless they
# appear via one of these platforms.
#
# ⚠️ Algora was REMOVED on 2026-07-17 (platform pivoted to recruiting).
# ⚠️ Bountycaster was REMOVED on 2026-07-17 (required Privy/Farcaster auth).
# ✅ Dework was ADDED on 2026-07-17 (Web3 DAO bounties, public API for
#    org/workspace metadata, DEWORK_AUTH_TOKEN for task data).
# ──────────────────────────────────────────────────────────────────── #
VERIFIED_SCRAPER_MAP = {
    "issuehunt": IssueHuntScraper,
    "dework": DeworkScraper,
}

# Legacy platforms (Immunefi / Code4rena / Sherlock) — kept for manual
# invocation via `--platform immunefi` etc., but NOT included when
# `--platform all` is used. Set INCLUDE_LEGACY_SCRAPERS=true to include.
LEGACY_SCRAPER_MAP = {
    "immunefi": ImmunefiScraper,
    "code4rena": Code4renaScraper,
    "sherlock": SherlockScraper,
}

# Final SCRAPER_MAP: verified by default, plus legacy if env var set
if os.getenv("INCLUDE_LEGACY_SCRAPERS", "false").lower() == "true":
    SCRAPER_MAP = {**VERIFIED_SCRAPER_MAP, **LEGACY_SCRAPER_MAP}
else:
    SCRAPER_MAP = dict(VERIFIED_SCRAPER_MAP)


def scrape_platform(platform_name: str, max_bounties: int = 10) -> list[Bounty]:
    """Scrape bounties from a single platform."""
    scraper_class = SCRAPER_MAP.get(platform_name)
    if not scraper_class:
        log.error("unknown platform: %s", platform_name)
        return []

    scraper = scraper_class()
    try:
        bounties = scraper.scrape()
        bounties.sort(key=lambda b: b.max_payout_usd, reverse=True)
        bounties = bounties[:max_bounties]
        log.info("[%s] found %d bounties (top %d kept)", platform_name, len(bounties), len(bounties))
        scraper.save_bounties(bounties)
        return bounties
    except Exception as exc:
        log.exception("[%s] error: %s", platform_name, exc)
        return []


def scrape_all(max_per_platform: int = 10) -> list[Bounty]:
    """Scrape bounties from all platforms."""
    all_bounties: list[Bounty] = []
    for platform_name in SCRAPER_MAP:
        bounties = scrape_platform(platform_name, max_per_platform)
        all_bounties.extend(bounties)
    all_bounties.sort(key=lambda b: b.max_payout_usd, reverse=True)
    return all_bounties


def deduplicate(bounties: list[Bounty]) -> list[Bounty]:
    """Filter out bounties we've already seen."""
    state = State("bounties_seen", ttl_hours=24 * 7)
    state.prune()
    before = len(bounties)
    fresh = [b for b in bounties if not state.has(b.dedup_key)]
    for b in fresh:
        state.add(b.dedup_key, data={"platform": b.platform, "project": b.project_name, "max_payout": b.max_payout_usd})
    log.info("dedup: %d -> %d (skipped %d already seen)", before, len(fresh), before - len(fresh))
    return fresh


def verify_open_on_github(bounties: list[Bounty]) -> list[Bounty]:
    """Filter out bounties whose GitHub issue is actually closed.

    IssueHunt's `githubState` field is cached from when IssueHunt first
    fetched the issue — sometimes years out of date. The real GitHub
    state may have changed since (e.g., apache/incubator-superset#3821
    shows as 'open' on IssueHunt but is actually 'closed' on GitHub).

    This function makes a single GET /repos/{owner}/{repo}/issues/{n}
    call per bounty and filters out any whose live state != 'open'.

    Failures (rate limit, network, 404) are treated as 'keep' — we'd
    rather analyze a possibly-closed bounty than miss a real one due
    to a transient API error. A separate rate_limit check warns early.

    Added 2026-07-17 after doubt-driven review of bot issue #24 found
    that apache/incubator-superset#3821 was surfacing as actionable
    despite being closed on GitHub since 2019.
    """
    if not bounties:
        return bounties

    gh = GitHubClient()
    if gh._dry_run:
        log.info("[DRY-RUN] skipping GitHub state verification (would call API %d times)", len(bounties))
        return bounties

    import re as _re  # noqa: PLC0415

    import httpx  # noqa: PLC0415

    verified: list[Bounty] = []
    skipped = 0
    for b in bounties:
        # Only verify bounties that have a GitHub source URL
        github_url = next((u for u in b.source_urls if "github.com" in u), None)
        if not github_url:
            verified.append(b)
            continue

        # Parse owner/repo/number from URL like
        # https://github.com/owner/repo/issues/123
        m = _re.match(r"https?://github\.com/([^/]+)/([^/]+)/issues/(\d+)", github_url)
        if not m:
            verified.append(b)
            continue

        owner, repo, num = m.group(1), m.group(2), m.group(3)
        api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{num}"

        try:
            # Use httpx directly (GitHubClient wraps issue creation, not reads)
            # Auth via GH_PAT env var if set, otherwise anonymous (lower rate limit)
            headers = {"Accept": "application/vnd.github+json"}
            gh_pat = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN")
            if gh_pat:
                headers["Authorization"] = f"token {gh_pat}"

            resp = httpx.get(api_url, headers=headers, timeout=15, follow_redirects=True)
            if resp.status_code == 404:
                log.warning("[%s] GitHub issue not found (404) — skipping", b.project_name)
                skipped += 1
                continue
            if resp.status_code == 301:
                # Repo renamed — follow redirect (httpx already does, but just in case)
                log.info("[%s] GitHub redirect — keeping for now", b.project_name)
                verified.append(b)
                continue
            resp.raise_for_status()
            data = resp.json()
            live_state = data.get("state", "open")
            if live_state != "open":
                log.info(
                    "[%s] GitHub state is '%s' (IssueHunt said 'open') — skipping stale bounty",
                    b.project_name, live_state,
                )
                skipped += 1
                continue
            verified.append(b)
        except Exception as exc:
            # On any error, KEEP the bounty — better to analyze than to miss it
            log.warning("[%s] GitHub verify failed (%s) — keeping", b.project_name, exc)
            verified.append(b)

    log.info("verify_open_on_github: %d -> %d (skipped %d stale-closed)", len(bounties), len(verified), skipped)
    return verified


def analyze_bounty(bounty: Bounty) -> dict[str, Any]:
    """Download source code and run AI vulnerability analysis on a bounty.

    Returns dict with findings + doubt review results.
    """
    # Update execution pointer (agent.md §1)
    state_manager.update_pointer(
        stage="ANALYZING",
        last_action=f"Analyzing {bounty.project_name} ({bounty.platform})",
        current_target_repo=bounty.project_name,
    )

    # Skip blacklisted repos (agent.md §3 / Golden Rules)
    if state_manager.is_blacklisted(bounty.project_name):
        log.warning("[%s] blacklisted — skipping", bounty.project_name)
        tg = get_notifier()
        tg.send_filter_event(
            repo=bounty.project_name,
            reason="Blacklisted repo (Golden Rule)",
            details="Repo in state.json blacklisted_repos",
        )
        return {
            "bounty": bounty.to_dict(),
            "source_downloaded": False,
            "source_chars": 0,
            "findings": [],
            "reviewed_findings": [],
            "submittable_count": 0,
        }

    result: dict[str, Any] = {
        "bounty": bounty.to_dict(),
        "source_downloaded": False,
        "source_chars": 0,
        "findings": [],
        "reviewed_findings": [],
        "submittable_count": 0,
    }

    # 1. Download source code (multi-language — was Solidity-only)
    downloader = ContractDownloader()
    source_code = None
    detected_language = None
    for url in bounty.source_urls:
        source_code = downloader.download(url)
        if source_code:
            # Detect language from the downloaded source
            detected_language = downloader._detect_language(
                # Build a fake tree entry from the source for detection
                # (the source contains "// File: path" headers we can parse)
                [
                    {"path": line.replace("// File: ", "").strip(), "type": "blob"}
                    for line in source_code.split("\n")
                    if line.startswith("// File: ")
                ]
            ) if "// File: " in source_code else None
            break

    if not source_code:
        log.info("[%s] no source code available — skipping analysis", bounty.project_name)
        return result

    result["source_downloaded"] = True
    result["source_chars"] = len(source_code)
    log.info(
        "[%s] downloaded %d chars of source code (language: %s)",
        bounty.project_name, len(source_code), detected_language or "auto-detect",
    )

    # 2. AI vulnerability detection + verification (merged — single AI call)
    # Multi-language: detector uses language-aware prompts (Solidity, JS, Python, etc.)
    detector = VulnerabilityDetector()
    findings = detector.analyze(source_code, bounty.project_name, language=detected_language)
    result["findings"] = [f.to_dict() for f in findings]

    if not findings:
        log.info("[%s] no vulnerabilities found by AI", bounty.project_name)
        return result

    # Only VERIFIED findings are shown to user (INCONCLUSIVE logged but not shown)
    # Added 2026-07-17: also filter out VERIFIED findings with confidence_adjusted
    # below MIN_SUBMITTABLE_CONFIDENCE. The doubt-reviewer sometimes marks a
    # finding as VERIFIED but with confidence 0.00 (meaning it couldn't actually
    # substantiate the claim). These are noise — recent bot issues #24-#28 all
    # had confidence 0.00 and were rejected on doubt-driven review.
    MIN_SUBMITTABLE_CONFIDENCE = 0.30
    verified_all = [f for f in findings if f.verdict == "VERIFIED"]
    low_confidence_verified = [f for f in verified_all if f.confidence_adjusted < MIN_SUBMITTABLE_CONFIDENCE]
    verified_findings = [f for f in verified_all if f.confidence_adjusted >= MIN_SUBMITTABLE_CONFIDENCE]

    if low_confidence_verified:
        log.info(
            "[%s] %d VERIFIED finding(s) dropped (confidence < %.2f, likely false positive)",
            bounty.project_name, len(low_confidence_verified), MIN_SUBMITTABLE_CONFIDENCE,
        )

    result["reviewed_findings"] = [f.to_dict() for f in findings]
    result["submittable_count"] = len(verified_findings)

    verified_count = len(verified_findings)
    inconclusive_count = sum(1 for f in findings if f.verdict == "INCONCLUSIVE")
    log.info(
        "[%s] %d findings -> %d VERIFIED, %d INCONCLUSIVE -> %d for user review",
        bounty.project_name, len(findings), verified_count, inconclusive_count, verified_count,
    )

    return result


def create_finding_issues(analysis_results: list[dict[str, Any]], gh: GitHubClient) -> int:
    """Create GitHub Issues for submittable findings. Returns count created."""
    issues_created = 0

    for result in analysis_results:
        bounty = result["bounty"]
        if result["submittable_count"] == 0:
            continue

        # Only show VERIFIED findings to user
        submittable = []
        if "reviewed_findings" in result and result["reviewed_findings"]:
            submittable = [
                f for f in result["reviewed_findings"]
                if f.get("verdict") == "VERIFIED"
            ]
        else:
            submittable = []

        if not submittable:
            continue

        # Build issue body
        lines = [
            f"## 🔍 Vulnerability Finding: {bounty['project_name']}",
            "",
            f"**Platform:** {bounty['platform']}",
            f"**Bounty URL:** {bounty['url']}",
            f"**Max Payout:** ${bounty['max_payout_usd']:,}",
            f"**Source Downloaded:** {'✅' if result['source_downloaded'] else '❌'}",
            "",
            f"### Findings ({result['submittable_count']} worth reviewing)",
            "",
        ]

        for i, f in enumerate(submittable, 1):
            orig = f.get("original", f)
            verdict = f.get("verdict", "UNREVIEWED")
            verdict_emoji = {"VERIFIED": "✅", "FALSE_POSITIVE": "❌", "INCONCLUSIVE": "⚠️"}.get(verdict, "❓")
            lines.append(f"#### Finding #{i}: {verdict_emoji} {verdict} — {orig.get('title', 'Untitled')}")
            lines.append(f"- **Severity:** {orig.get('severity', '?')}")
            lines.append(f"- **AI Confidence:** {orig.get('confidence', 0):.2f} → **Verified Confidence:** {f.get('confidence_adjusted', 0):.2f}")
            lines.append(f"- **Verdict:** {verdict}")
            lines.append(f"- **Description:** {orig.get('description', '')}")
            lines.append(f"- **Impact:** {orig.get('impact', '')}")

            # Show verification evidence
            if f.get("evidence"):
                lines.append(f"- **Evidence:** {f['evidence'][:500]}")
            if f.get("inheritance_chain") and f["inheritance_chain"] != "Not resolved":
                lines.append(f"- **Inheritance Chain:** {f['inheritance_chain'][:300]}")
            if f.get("call_graph") and f["call_graph"] != "Not built":
                lines.append(f"- **Call Graph:** {f['call_graph'][:300]}")
            if f.get("falsification_attempts") and f["falsification_attempts"] != "Not attempted":
                lines.append(f"- **Falsification Attempts:** {f['falsification_attempts'][:300]}")

            if orig.get("swc_id"):
                lines.append(f"- **SWC ID:** {orig['swc_id']}")
            lines.append(f"- **Recommendation:** {f.get('recommendation', 'investigate')}")
            lines.append("")

        lines.extend([
            "### Actions",
            "- `/submit` — create a formal report and submit to platform",
            "- `/reject <reason>` — discard this finding",
            "- `/modify <instructions>` — request re-analysis with notes",
            "",
            "---",
            f"*Analyzed at: {datetime.now(UTC).isoformat()}*",
        ])

        issue = gh.create_issue(
            title=f"🔍 [{bounty['platform']}] {bounty['project_name']}: {result['submittable_count']} finding(s)",
            body="\n".join(lines),
            labels=["bounty-finding"],
        )
        if issue:
            issues_created += 1

    return issues_created


def save_summary(bounties: list[Bounty], analysis_results: list[dict[str, Any]]) -> Path:
    """Save summary JSON for this run."""
    state_dir = Path("state")
    state_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "run_at": datetime.now(UTC).isoformat(),
        "total_bounties": len(bounties),
        "analyzed": len(analysis_results),
        "total_findings": sum(len(r["findings"]) for r in analysis_results),
        "submittable_findings": sum(r["submittable_count"] for r in analysis_results),
        "by_platform": {},
        "top_bounties": [b.to_dict() for b in bounties[:10]],
    }
    for b in bounties:
        summary["by_platform"][b.platform] = summary["by_platform"].get(b.platform, 0) + 1

    path = state_dir / "pipeline_summary.json"
    path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("summary saved to %s", path)
    return path


def notify_operator_if_needed(bounties: list[Bounty]) -> None:
    """If we found high-value bounties, create a GitHub Issue summary."""
    if not bounties:
        return

    gh = GitHubClient()
    if gh._dry_run:
        log.info("[DRY-RUN] would create summary Issue for %d bounties", len(bounties))
        return

    high_value = [b for b in bounties if b.max_payout_usd >= 10_000]
    if not high_value:
        log.info("no high-value bounties (>= $10k) — skipping notification")
        return

    lines = ["## 🎯 Pipeline Run Summary\n"]
    lines.append(f"**Total bounties found:** {len(bounties)}\n")
    lines.append(f"**High-value (>= $10k):** {len(high_value)}\n\n")
    lines.append("### Top 10 Bounties\n")
    lines.append("| # | Platform | Project | Max Payout | URL |")
    lines.append("|---|----------|---------|------------|-----|")
    for i, b in enumerate(bounties[:10], 1):
        lines.append(f"| {i} | {b.platform} | {b.project_name} | ${b.max_payout_usd:,} | [link]({b.url}) |")
    lines.append(f"\n---\n*Run time: {datetime.now(UTC).isoformat()}*")

    gh.create_issue(
        title=f"🎯 Pipeline: {len(bounties)} bounties found ({len(high_value)} high-value)",
        body="\n".join(lines),
        labels=["pipeline-summary"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounty Hunter Pipeline")
    parser.add_argument(
        "--platform",
        default="all",
        choices=["all"] + list(SCRAPER_MAP.keys()),
    )
    parser.add_argument("--max-bounties", type=int, default=5)
    parser.add_argument(
        "--dry-run",
        type=lambda x: x.lower() == "true",
        default=True,
    )
    parser.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Skip AI analysis (scrape only)",
    )
    args = parser.parse_args()

    silence_noisy_libs()

    # ──────────────────────────────────────────────────────────────── #
    # MASTER BRAKE — agent.md §2
    # If system_status is PAUSED, exit immediately without doing anything.
    # This is checked BEFORE any Telegram notification so we don't even
    # ping the channel.
    # ──────────────────────────────────────────────────────────────── #
    if state_manager.is_paused():
        log.warning("🛑 SYSTEM IS PAUSED — aborting pipeline (agent.md §2)")
        # Optional: notify channel once per paused run so user knows the
        # brake is being respected.
        tg = get_notifier()
        tg.send(
            "🛑 *Pipeline skipped*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Reason: `system_status = PAUSED` in state.json\n"
            "Tap ▶️ Resume Flow to continue.\n"
            "━━━━━━━━━━━━━━━━━━",
            with_controls=True,
        )
        return 0

    log.info("=== Bounty Hunter Pipeline starting ===")
    log.info("platform=%s max=%d dry_run=%s skip_analysis=%s",
             args.platform, args.max_bounties, args.dry_run, args.skip_analysis)

    # Update execution pointer (agent.md §1)
    state_manager.update_pointer(
        stage="PIPELINE_START",
        last_action=f"Pipeline started (platform={args.platform}, max={args.max_bounties})",
        current_target_repo="NONE",
    )

    # 0. Telegram notification: pipeline started (with control buttons)
    tg = get_notifier()
    tg.send_pipeline_start(args.platform, args.max_bounties)

    # 1. Scrape
    state_manager.update_pointer(
        stage="SCRAPING",
        last_action=f"Scraping platform={args.platform}",
        current_target_repo="NONE",
    )
    if args.platform == "all":
        bounties = scrape_all(args.max_bounties)
    else:
        bounties = scrape_platform(args.platform, args.max_bounties)

    log.info("total bounties scraped: %d", len(bounties))

    # 2. Deduplicate
    fresh_bounties = deduplicate(bounties)

    # 2b. Verify live GitHub state (IssueHunt's githubState is often stale)
    fresh_bounties = verify_open_on_github(fresh_bounties)

    # 3. AI Analysis (optional)
    analysis_results: list[dict[str, Any]] = []
    if not args.skip_analysis and fresh_bounties:
        log.info("=== Starting AI Analysis ===")
        for bounty in fresh_bounties:
            # Re-check PAUSED before each bounty (user might tap stop mid-run)
            if state_manager.is_paused():
                log.warning("🛑 PAUSED mid-run — aborting analysis loop")
                tg.send(
                    "🛑 *Analysis halted mid-run*\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    f"Stopped before: `{bounty.project_name}`\n"
                    "━━━━━━━━━━━━━━━━━━",
                    with_controls=True,
                )
                break

            log.info("analyzing: %s (%s)", bounty.project_name, bounty.platform)
            try:
                result = analyze_bounty(bounty)
                analysis_results.append(result)
                # Telegram notification ONLY for VERIFIED findings
                if result["submittable_count"] > 0:
                    for f in result.get("reviewed_findings", []):
                        if f.get("verdict") == "VERIFIED":
                            tg.send_finding(
                                project=bounty.project_name,
                                title=f.get("title", "Unknown"),
                                severity=f.get("severity", "Info"),
                                confidence=f.get("confidence", 0),
                                url=bounty.url,
                            )
            except Exception as exc:
                log.exception("analysis failed for %s: %s", bounty.project_name, exc)
                tg.send_error(str(exc), context=f"analyzing {bounty.project_name}")

    # 4. Save summary
    save_summary(fresh_bounties, analysis_results)

    # 5. Create GitHub Issues for findings (create for both "submit" AND "investigate")
    total_submittable = sum(r["submittable_count"] for r in analysis_results)
    if not args.dry_run and analysis_results:
        state_manager.update_pointer(
            stage="CREATING_ISSUES",
            last_action=f"Creating {total_submittable} finding Issues",
            current_target_repo="NONE",
        )
        gh = GitHubClient()
        if not gh._dry_run:
            issues = create_finding_issues(analysis_results, gh)
            log.info("created %d finding Issues", issues)
        else:
            log.info("[DRY-RUN] would create finding Issues")
    elif args.dry_run and analysis_results:
        log.info("[DRY-RUN] skipping finding Issues (dry-run mode)")
        log.info("findings summary:")
        for r in analysis_results:
            log.info("  %s: %d findings, %d submittable",
                     r["bounty"]["project_name"], len(r["findings"]), r["submittable_count"])

    # 6. Notify operator about high-value bounties
    if not args.dry_run:
        notify_operator_if_needed(fresh_bounties)

    # 7. Telegram notification: pipeline complete (with control buttons)
    total_findings = sum(len(r["findings"]) for r in analysis_results)
    tg.send_pipeline_complete(
        total_bounties=len(fresh_bounties),
        total_findings=total_findings,
        submittable=total_submittable,
    )

    # Update execution pointer — pipeline complete
    state_manager.update_pointer(
        stage="MONITORING_AND_HUNTING",
        last_action=f"Pipeline complete (bounties={len(fresh_bounties)}, findings={total_findings})",
        current_target_repo="NONE",
    )

    log.info("=== Pipeline complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
