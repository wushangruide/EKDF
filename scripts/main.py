"""
Orchestrates the daily postdoc job scan pipeline.

Steps:
  1. Load config
  2. Load seen_jobs.json
  3. Scrape all sources
  4. Phase 1 filter: dedup against seen
  5. Phase 2 filter: Claude Haiku relevance scoring
  6. Draft emails with Claude Sonnet for matching jobs
  7. Send email digest
  8. Persist updated seen_jobs.json
"""
import json
import logging
import os
import sys
import time
from pathlib import Path

import yaml

from scraper import fetch_all
import filter as job_filter
import drafter
import notifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

SEEN_JOBS_PATH = Path("data/seen_jobs.json")
PROFILE_PATH = Path("config/profile.yml")


def load_seen() -> dict:
    if SEEN_JOBS_PATH.exists():
        return json.loads(SEEN_JOBS_PATH.read_text())
    return {"jobs": {}}


def save_seen(seen: dict) -> None:
    SEEN_JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEEN_JOBS_PATH.write_text(json.dumps(seen, indent=2, ensure_ascii=False))


def main() -> None:
    # ── 1. Load profile ──────────────────────────────────────────────
    profile = yaml.safe_load(PROFILE_PATH.read_text())
    threshold = profile.get("relevance_threshold", 6)

    job_filter.set_profile(profile)
    drafter.set_profile(profile)

    # ── 2. Load seen_jobs ─────────────────────────────────────────────
    seen = load_seen()
    logger.info(f"Loaded seen_jobs.json: {len(seen.get('jobs', {}))} entries")

    # ── 3. Scrape all sources ─────────────────────────────────────────
    logger.info("=== SCRAPING ===")
    all_jobs = fetch_all()
    logger.info(f"Total scraped: {len(all_jobs)} jobs")

    # ── 4. Phase 1: dedup ─────────────────────────────────────────────
    new_jobs = job_filter.filter_new_jobs(all_jobs, seen)
    logger.info(f"New (unseen) jobs: {len(new_jobs)}")

    scan_stats = {
        "total_scanned": len(all_jobs),
        "new_jobs": len(new_jobs),
    }

    # ── 5. Phase 2: Claude Haiku relevance scoring ───────────────────
    matched = []
    if new_jobs:
        logger.info(f"=== SCORING ({len(new_jobs)} new jobs) ===")
        matched = job_filter.score_jobs(new_jobs, threshold=threshold)
        logger.info(f"Jobs above threshold ({threshold}): {len(matched)}")
    else:
        logger.info("No new jobs to score.")

    # ── 6. Draft emails with Claude Sonnet ───────────────────────────
    drafted_items = []
    if matched:
        logger.info(f"=== DRAFTING EMAILS ({len(matched)} positions) ===")
        drafted_items = drafter.draft_all(matched)
    else:
        logger.info("No matching jobs — skipping email drafting.")

    # ── 7. Send digest email (always send — silence = broken system) ──
    logger.info("=== SENDING DIGEST ===")
    try:
        notifier.send_email(drafted_items, scan_stats, profile)
    except Exception as e:
        logger.error(f"Email notification failed: {e}")
        # Don't abort — still update seen_jobs

    # ── 8. Persist seen_jobs (mark ALL new jobs, not just matching) ───
    seen = job_filter.update_seen(seen, new_jobs)
    seen = job_filter.prune_seen(seen)
    save_seen(seen)
    logger.info(f"seen_jobs.json updated: {len(seen['jobs'])} total entries")

    logger.info("=== DONE ===")
    logger.info(
        f"Summary: {len(all_jobs)} scraped → {len(new_jobs)} new → "
        f"{len(matched)} matched → {len(drafted_items)} emails drafted"
    )


if __name__ == "__main__":
    main()
