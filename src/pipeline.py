"""
Bounty Hunter Pipeline Orchestrator.

Scrapes bounties from all platforms, deduplicates against state,
saves results, and creates GitHub Issues for high-value findings.

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
        # Sort by max payout (highest first)
        bounties.sort(key=lambda b: b.max_payout_usd, reverse=True)
        bounties = bounties[:max_bounties]
        log.info("[%s] found %d bounties (top %d kept)", platform_name, len(bounties), len(bounties))
        # Save bounties
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

    # Sort all by max payout
    all_bounties.sort(key=lambda b: b.max_payout_usd, reverse=True)
    return all_bounties


def deduplicate(bounties: List[Bounty]) -> List[Bounty]:
    """Filter out bounties we've already seen (using state)."""
    state = State("bounties_seen", ttl_hours=24 * 7)  # 1 week TTL
    state.prune()
    before = len(bounties)
    fresh = [b for b in bounties if not state.has(b.dedup_key)]
    # Add new ones to state
    for b in fresh:
        state.add(b.dedup_key, data={"platform": b.platform, "project": b.project_name, "max_payout": b.max_payout_usd})
    log.info("dedup: %d -> %d (skipped %d already seen)", before, len(fresh), before - len(fresh))
    return fresh


def save_summary(bounties: List[Bounty]) -> Path:
    """Save summary JSON for this run."""
    state_dir = Path("state")
    state_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "total_bounties": len(bounties),
        "by_platform": {},
        "top_10": [b.to_dict() for b in bounties[:10]],
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
        log.info("no bounties found — skipping notification")
        return

    gh = GitHubClient()
    if gh._dry_run:
        log.info("[DRY-RUN] would create summary Issue for %d bounties", len(bounties))
        return

    # Only notify if there are bounties with >= $10k payout
    high_value = [b for b in bounties if b.max_payout_usd >= 10_000]
    if not high_value:
        log.info("no high-value bounties (>= $10k) — skipping notification")
        return

    # Build issue body
    lines = [f"## 🎯 Pipeline Run Summary\n"]
    lines.append(f"**Total bounties found:** {len(bounties)}\n")
    lines.append(f"**High-value (>= $10k):** {len(high_value)}\n\n")
    lines.append("### Top 10 Bounties\n")
    lines.append("| # | Platform | Project | Max Payout | URL |")
    lines.append("|---|----------|---------|------------|-----|")
    for i, b in enumerate(bounties[:10], 1):
        payout = f"${b.max_payout_usd:,}"
        lines.append(f"| {i} | {b.platform} | {b.project_name} | {payout} | [link]({b.url}) |")

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
    parser.add_argument("--max-bounties", type=int, default=10)
    parser.add_argument(
        "--dry-run",
        type=lambda x: x.lower() == "true",
        default=True,
        help="true=dry-run (default), false=real operations",
    )
    args = parser.parse_args()

    silence_noisy_libs()
    log.info("=== Bounty Hunter Pipeline starting ===")
    log.info("platform=%s max=%d dry_run=%s", args.platform, args.max_bounties, args.dry_run)

    # 1. Scrape
    if args.platform == "all":
        bounties = scrape_all(args.max_bounties)
    else:
        bounties = scrape_platform(args.platform, args.max_bounties)

    log.info("total bounties scraped: %d", len(bounties))

    # 2. Deduplicate
    fresh_bounties = deduplicate(bounties)

    # 3. Save summary
    save_summary(fresh_bounties)

    # 4. Notify operator (create GitHub Issue if high-value bounties found)
    if not args.dry_run:
        notify_operator_if_needed(fresh_bounties)
    else:
        log.info("[DRY-RUN] skipping operator notification")

    log.info("=== Pipeline complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
