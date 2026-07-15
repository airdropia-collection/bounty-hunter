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
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from src.config import CONFIG
from src.scrapers.immunefi import ImmunefiScraper
from src.scrapers.code4rena import Code4renaScraper
from src.scrapers.sherlock import SherlockScraper
from src.scrapers.base import Bounty
from src.analyzers.contract_downloader import ContractDownloader
from src.analyzers.vuln_detector import VulnerabilityDetector
from src.analyzers.doubt_review import DoubtReviewer
from src.utils.logger import get_logger, silence_noisy_libs
from src.utils.state import State
from src.utils.github_client import GitHubClient

log = get_logger("pipeline")

SCRAPER_MAP = {
    "immunefi": ImmunefiScraper,
    "code4rena": Code4renaScraper,
    "sherlock": SherlockScraper,
}


def scrape_platform(platform_name: str, max_bounties: int = 10) -> List[Bounty]:
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


def scrape_all(max_per_platform: int = 10) -> List[Bounty]:
    """Scrape bounties from all platforms."""
    all_bounties: List[Bounty] = []
    for platform_name in SCRAPER_MAP:
        bounties = scrape_platform(platform_name, max_per_platform)
        all_bounties.extend(bounties)
    all_bounties.sort(key=lambda b: b.max_payout_usd, reverse=True)
    return all_bounties


def deduplicate(bounties: List[Bounty]) -> List[Bounty]:
    """Filter out bounties we've already seen."""
    state = State("bounties_seen", ttl_hours=24 * 7)
    state.prune()
    before = len(bounties)
    fresh = [b for b in bounties if not state.has(b.dedup_key)]
    for b in fresh:
        state.add(b.dedup_key, data={"platform": b.platform, "project": b.project_name, "max_payout": b.max_payout_usd})
    log.info("dedup: %d -> %d (skipped %d already seen)", before, len(fresh), before - len(fresh))
    return fresh


def analyze_bounty(bounty: Bounty) -> Dict[str, Any]:
    """Download source code and run AI vulnerability analysis on a bounty.

    Returns dict with findings + doubt review results.
    """
    result: Dict[str, Any] = {
        "bounty": bounty.to_dict(),
        "source_downloaded": False,
        "source_chars": 0,
        "findings": [],
        "reviewed_findings": [],
        "submittable_count": 0,
    }

    # 1. Download contract source
    downloader = ContractDownloader()
    source_code = None
    for url in bounty.source_urls:
        source_code = downloader.download(url)
        if source_code:
            break

    if not source_code:
        log.info("[%s] no source code available — skipping analysis", bounty.project_name)
        return result

    result["source_downloaded"] = True
    result["source_chars"] = len(source_code)
    log.info("[%s] downloaded %d chars of source code", bounty.project_name, len(source_code))

    # 2. AI vulnerability detection
    detector = VulnerabilityDetector()
    findings = detector.analyze(source_code, bounty.project_name)
    result["findings"] = [f.to_dict() for f in findings]

    if not findings:
        log.info("[%s] no vulnerabilities found by AI", bounty.project_name)
        return result

    # 3. Doubt-driven review (only if enabled)
    if CONFIG.ENABLE_DOUBT_REVIEW:
        reviewer = DoubtReviewer()
        reviewed = reviewer.review_many(findings, source_code)
        result["reviewed_findings"] = [r.to_dict() for r in reviewed]
        submittable = reviewer.filter_submittable(reviewed)
        result["submittable_count"] = len(submittable)
        log.info(
            "[%s] %d findings -> %d survive doubt review -> %d submittable",
            bounty.project_name, len(findings), sum(1 for r in reviewed if r.survives), len(submittable),
        )
    else:
        # No doubt review — all findings are "submittable" if confidence >= 0.7
        result["submittable_count"] = sum(1 for f in findings if f.confidence >= 0.7)

    return result


def create_finding_issues(analysis_results: List[Dict[str, Any]], gh: GitHubClient) -> int:
    """Create GitHub Issues for submittable findings. Returns count created."""
    issues_created = 0

    for result in analysis_results:
        bounty = result["bounty"]
        if result["submittable_count"] == 0:
            continue

        # Find submittable findings
        submittable = []
        if "reviewed_findings" in result and result["reviewed_findings"]:
            submittable = [r for r in result["reviewed_findings"] if r.get("recommendation") == "submit"]
        else:
            submittable = [f for f in result["findings"] if f.get("confidence", 0) >= 0.7]

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
            f"### Findings ({result['submittable_count']} submittable)",
            "",
        ]

        for i, f in enumerate(submittable, 1):
            lines.append(f"#### Finding #{i}: {f.get('original', {}).get('title', f.get('title', 'Untitled'))}")
            lines.append(f"- **Severity:** {f.get('original', {}).get('severity', f.get('severity', '?'))}")
            lines.append(f"- **Confidence:** {f.get('confidence_adjusted', f.get('confidence', 0)):.2f}")
            lines.append(f"- **Description:** {f.get('original', {}).get('description', f.get('description', ''))}")
            lines.append(f"- **Impact:** {f.get('original', {}).get('impact', f.get('impact', ''))}")
            lines.append(f"- **Recommendation:** {f.get('original', {}).get('recommendation', f.get('recommendation', ''))}")
            if f.get('original', {}).get('swc_id', f.get('swc_id', '')):
                lines.append(f"- **SWC ID:** {f.get('original', {}).get('swc_id', f.get('swc_id', ''))}")
            lines.append("")

        lines.extend([
            "### Actions",
            "- `/submit` — create a formal report and submit to platform",
            "- `/reject <reason>` — discard this finding",
            "- `/modify <instructions>` — request re-analysis with notes",
            "",
            "---",
            f"*Analyzed at: {datetime.now(timezone.utc).isoformat()}*",
        ])

        issue = gh.create_issue(
            title=f"🔍 [{bounty['platform']}] {bounty['project_name']}: {result['submittable_count']} finding(s)",
            body="\n".join(lines),
            labels=["bounty-finding"],
        )
        if issue:
            issues_created += 1

    return issues_created


def save_summary(bounties: List[Bounty], analysis_results: List[Dict[str, Any]]) -> Path:
    """Save summary JSON for this run."""
    state_dir = Path("state")
    state_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "run_at": datetime.now(timezone.utc).isoformat(),
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


def notify_operator_if_needed(bounties: List[Bounty]) -> None:
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

    lines = [f"## 🎯 Pipeline Run Summary\n"]
    lines.append(f"**Total bounties found:** {len(bounties)}\n")
    lines.append(f"**High-value (>= $10k):** {len(high_value)}\n\n")
    lines.append("### Top 10 Bounties\n")
    lines.append("| # | Platform | Project | Max Payout | URL |")
    lines.append("|---|----------|---------|------------|-----|")
    for i, b in enumerate(bounties[:10], 1):
        lines.append(f"| {i} | {b.platform} | {b.project_name} | ${b.max_payout_usd:,} | [link]({b.url}) |")
    lines.append(f"\n---\n*Run time: {datetime.now(timezone.utc).isoformat()}*")

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
    log.info("=== Bounty Hunter Pipeline starting ===")
    log.info("platform=%s max=%d dry_run=%s skip_analysis=%s",
             args.platform, args.max_bounties, args.dry_run, args.skip_analysis)

    # 1. Scrape
    if args.platform == "all":
        bounties = scrape_all(args.max_bounties)
    else:
        bounties = scrape_platform(args.platform, args.max_bounties)

    log.info("total bounties scraped: %d", len(bounties))

    # 2. Deduplicate
    fresh_bounties = deduplicate(bounties)

    # 3. AI Analysis (optional)
    analysis_results: List[Dict[str, Any]] = []
    if not args.skip_analysis and fresh_bounties:
        log.info("=== Starting AI Analysis ===")
        for bounty in fresh_bounties:
            log.info("analyzing: %s (%s)", bounty.project_name, bounty.platform)
            try:
                result = analyze_bounty(bounty)
                analysis_results.append(result)
            except Exception as exc:
                log.exception("analysis failed for %s: %s", bounty.project_name, exc)

    # 4. Save summary
    save_summary(fresh_bounties, analysis_results)

    # 5. Create GitHub Issues for findings (only if not dry-run)
    if not args.dry_run and analysis_results:
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

    log.info("=== Pipeline complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
