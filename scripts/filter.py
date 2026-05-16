"""
Two-phase filtering:
  Phase 1 (free): dedup against seen_jobs.json
  Phase 2 (Claude Haiku, batched): relevance scoring with prompt caching
"""
import json
import logging
import time
import anthropic

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = ""  # Built at runtime from profile

_client = anthropic.Anthropic()

PRUNE_DAYS = 90


def build_system_prompt(profile: dict) -> str:
    rp = profile.get("research_profile", {})
    locations = ", ".join(profile.get("target_locations", ["US", "Europe"]))
    return f"""You are a research position relevance evaluator.

Researcher profile:
- Primary areas: {", ".join(rp.get("primary_areas", []))}
- Secondary areas: {", ".join(rp.get("secondary_areas", []))}
- Crossover interests: {", ".join(rp.get("crossover_interests", []))}
- Target locations: {locations}
- Exclude: pure wet lab biology, pure hardware VLSI, humanities

Score each job 0-10 for relevance to this researcher.
Return ONLY a valid JSON array. No markdown. No explanation outside the array.
Format: [{{"job_id": "...", "score": <int>, "reason": "<one sentence>", "matched_areas": ["<area>"]}}]
"""


def set_profile(profile: dict) -> None:
    global _SYSTEM_PROMPT
    _SYSTEM_PROMPT = build_system_prompt(profile)


def _score_batch(jobs: list, retry: int = 0) -> list[dict]:
    """Score up to 10 jobs in a single Haiku call."""
    jobs_text = "\n---\n".join(
        f"job_id: {j.job_id}\ntitle: {j.title}\ninstitution: {j.institution}\n"
        f"location: {j.location}\ndescription: {j.description[:600]}"
        for j in jobs
    )
    try:
        response = _client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": f"Score these jobs for relevance:\n\n{jobs_text}",
                }
            ],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except anthropic.RateLimitError:
        if retry < 4:
            wait = 2 ** (retry + 1)
            logger.warning(f"Rate limit hit, retrying in {wait}s...")
            time.sleep(wait)
            return _score_batch(jobs, retry + 1)
        logger.error("Rate limit exceeded after retries")
        return [{"job_id": j.job_id, "score": 0, "reason": "rate limit", "matched_areas": []} for j in jobs]
    except (json.JSONDecodeError, anthropic.APIError) as e:
        logger.warning(f"Batch scoring error: {e}")
        return [{"job_id": j.job_id, "score": 0, "reason": "error", "matched_areas": []} for j in jobs]


def _chunks(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def filter_new_jobs(all_jobs: list, seen: dict) -> list:
    """Return jobs not yet in seen_jobs.json."""
    return [j for j in all_jobs if j.job_id not in seen.get("jobs", {})]


def score_jobs(new_jobs: list, threshold: int = 6) -> list[tuple]:
    """
    Score all new jobs with Haiku (batched, 10 per call).
    Returns sorted list of (job, score_result) tuples for jobs >= threshold.
    """
    if not new_jobs:
        return []

    all_scores: list[dict] = []
    batches = list(_chunks(new_jobs, 10))
    for i, batch in enumerate(batches):
        logger.info(f"  Scoring batch {i+1}/{len(batches)} ({len(batch)} jobs)...")
        scores = _score_batch(batch)
        all_scores.extend(scores)
        if i < len(batches) - 1:
            time.sleep(1)

    # Build lookup: job_id → score_result
    score_map = {s["job_id"]: s for s in all_scores}

    results = []
    for job in new_jobs:
        score_result = score_map.get(job.job_id, {"score": 0, "reason": "missing", "matched_areas": []})
        if score_result.get("score", 0) >= threshold:
            results.append((job, score_result))

    results.sort(key=lambda x: x[1].get("score", 0), reverse=True)
    return results


def update_seen(seen: dict, new_jobs: list) -> dict:
    """
    Mark ALL new jobs as seen (not just matching ones).
    This prevents re-scoring low-relevance jobs every day.
    """
    from datetime import datetime
    if "jobs" not in seen:
        seen["jobs"] = {}
    for job in new_jobs:
        seen["jobs"][job.job_id] = {
            "seen_at": datetime.utcnow().isoformat(),
            "title": job.title,
            "url": job.url,
        }
    return seen


def prune_seen(seen: dict) -> dict:
    """Remove seen_jobs entries older than PRUNE_DAYS."""
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(days=PRUNE_DAYS)
    seen["jobs"] = {
        job_id: meta
        for job_id, meta in seen.get("jobs", {}).items()
        if datetime.fromisoformat(meta["seen_at"]) > cutoff
    }
    return seen
