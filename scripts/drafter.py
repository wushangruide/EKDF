"""
Uses Claude Sonnet to draft personalized cold emails for matched postdoc positions.
"""
import logging
import anthropic

logger = logging.getLogger(__name__)

_client = anthropic.Anthropic()

_SYSTEM_PROMPT = """\
You are an expert academic writing assistant helping a PhD researcher write cold emails to potential postdoc supervisors.

Write a professional, concise, and personalized cold email. The email must:
1. Be 200-300 words (not too long)
2. Open with a specific reference to the professor's or lab's research (use what's in the job description)
3. Briefly introduce the researcher's background and key achievement
4. Explain why this position is a natural fit for their research direction
5. End with a clear, polite call to action (ask if there is an opening / express interest)
6. Have a professional subject line

Return ONLY this JSON format:
{
  "subject": "<email subject line>",
  "body": "<full email body in plain text, with \\n for line breaks>"
}

Use [placeholder] notation for any information you need but don't have (e.g., [specific paper title], [Your Name]).
Do NOT make up institution names, paper titles, or specific facts not provided.
"""

_PROFILE_BLOCK = ""


def set_profile(profile: dict) -> None:
    global _PROFILE_BLOCK
    rp = profile.get("research_profile", {})
    researcher = profile.get("researcher", {})
    papers = "\n".join(f"  - {p}" for p in rp.get("representative_papers", []))
    _PROFILE_BLOCK = f"""
Researcher profile:
- Name: {researcher.get('name', '[Your Name]')}
- Current university: {researcher.get('university', '[Your University]')}
- Department: {researcher.get('department', '[Department]')}
- Homepage: {researcher.get('homepage', '[Homepage URL]')}
- Expected graduation: {researcher.get('phd_year', '[Year]')}
- Primary research: {', '.join(rp.get('primary_areas', []))}
- Secondary research: {', '.join(rp.get('secondary_areas', []))}
- Crossover interests: {', '.join(rp.get('crossover_interests', []))}
- Key skills: {', '.join(rp.get('skills', []))}
- Representative papers:
{papers if papers else '  - [Paper 1], [Venue], [Year]'}
""".strip()


def draft_email(job, score_result: dict) -> dict:
    """
    Draft a cold email for a job listing.
    Returns dict with keys: subject, body
    """
    matched = ", ".join(score_result.get("matched_areas", []))
    listing_text = f"""
Job title: {job.title}
Institution: {job.institution}
Location: {job.location}
Source: {job.source}
URL: {job.url}
Deadline: {job.deadline or 'Not specified'}
Relevance match: {matched} (score {score_result.get('score')}/10)
Reason this matches: {score_result.get('reason', '')}

Full description:
{job.description[:2000]}
""".strip()

    try:
        response = _client.messages.create(
            model="claude-sonnet-4-6",
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
                    "content": (
                        f"{_PROFILE_BLOCK}\n\n"
                        f"Write a cold email for this position:\n{listing_text}"
                    ),
                }
            ],
        )
        import json
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception as e:
        logger.error(f"Email draft error for '{job.title}': {e}")
        return {
            "subject": f"Postdoctoral Position Inquiry – {job.title}",
            "body": "[Email draft failed — please draft manually]",
        }


def draft_all(matched_jobs: list[tuple]) -> list[dict]:
    """
    Draft emails for all matched jobs.
    Returns list of dicts with: job, score_result, email
    """
    results = []
    for i, (job, score_result) in enumerate(matched_jobs):
        logger.info(f"  Drafting email [{i+1}/{len(matched_jobs)}]: {job.title[:60]}")
        email = draft_email(job, score_result)
        results.append({"job": job, "score_result": score_result, "email": email})
    return results
