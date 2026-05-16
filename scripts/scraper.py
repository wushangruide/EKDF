"""
Scrapes postdoc job listings from multiple academic job boards via RSS feeds.
"""
import time
import logging
from dataclasses import dataclass, field
from typing import Optional
import feedparser
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SEARCH_KEYWORDS = [
    "edge computing postdoc",
    "edge AI postdoc",
    "AI agents postdoc",
    "agentic AI postdoc",
    "cognitive science AI postdoc",
    "computational neuroscience AI postdoc",
    "on-device inference postdoc",
    "machine learning systems postdoc",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PostdocScanner/1.0; academic research tool)"
}


@dataclass
class Job:
    title: str
    institution: str
    url: str
    description: str
    location: str = ""
    deadline: str = ""
    source: str = ""
    job_id: str = field(default="")

    def __post_init__(self):
        if not self.job_id:
            self.job_id = self.url


def _safe_get(url: str, timeout: int = 15) -> Optional[requests.Response]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None


def _parse_rss(url: str, source_name: str) -> list[Job]:
    """Parse an RSS/Atom feed and return Job objects."""
    try:
        feed = feedparser.parse(url)
        jobs = []
        for entry in feed.entries:
            title = getattr(entry, "title", "")
            link = getattr(entry, "link", "")
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            # Strip HTML tags from summary
            if summary:
                summary = BeautifulSoup(summary, "lxml").get_text(separator=" ", strip=True)
            institution = getattr(entry, "author", "") or getattr(entry, "publisher", "")
            jobs.append(Job(
                title=title,
                institution=institution,
                url=link,
                description=summary[:2000],
                source=source_name,
            ))
        return jobs
    except Exception as e:
        logger.warning(f"RSS parse error for {url}: {e}")
        return []


# ──────────────────────────────────────────
# Source 1: Academic Jobs Online (AJO)
# ──────────────────────────────────────────

def fetch_academic_jobs_online() -> list[Job]:
    """
    AJO provides RSS feeds per discipline.
    CS feed: https://academicjobsonline.org/ajo/rss/cs
    """
    feeds = [
        ("https://academicjobsonline.org/ajo/rss/cs", "AcademicJobsOnline-CS"),
        ("https://academicjobsonline.org/ajo/rss/econ", "AcademicJobsOnline-Econ"),
    ]
    jobs = []
    for url, name in feeds:
        jobs.extend(_parse_rss(url, name))
        time.sleep(1)
    # Keep only postdoc listings
    return [j for j in jobs if _is_postdoc(j.title)]


# ──────────────────────────────────────────
# Source 2: jobs.ac.uk
# ──────────────────────────────────────────

def fetch_jobs_ac_uk() -> list[Job]:
    """jobs.ac.uk has RSS search endpoints."""
    all_jobs = []
    keywords_short = [
        "edge computing postdoc",
        "AI postdoc",
        "machine learning postdoc",
        "cognitive neuroscience postdoc",
    ]
    for kw in keywords_short:
        url = (
            f"https://www.jobs.ac.uk/search/rss.xml"
            f"?keywords={requests.utils.quote(kw)}"
            f"&type=postdoc"
        )
        jobs = _parse_rss(url, "jobs.ac.uk")
        all_jobs.extend(jobs)
        time.sleep(1.5)
    return _dedupe(all_jobs)


# ──────────────────────────────────────────
# Source 3: EURAXESS (European research jobs)
# ──────────────────────────────────────────

def fetch_euraxess() -> list[Job]:
    """EURAXESS provides a public JSON API."""
    base = "https://euraxess.ec.europa.eu/api/jobs"
    keywords_short = ["edge computing", "AI agents", "cognitive science AI"]
    all_jobs = []
    for kw in keywords_short:
        try:
            resp = _safe_get(
                f"{base}?keywords={requests.utils.quote(kw)}&type=Postdoctoral+Positions"
            )
            if resp is None:
                continue
            data = resp.json()
            items = data.get("results", data) if isinstance(data, dict) else data
            for item in items[:20]:
                url = item.get("url") or item.get("link", "")
                if not url.startswith("http"):
                    url = "https://euraxess.ec.europa.eu" + url
                all_jobs.append(Job(
                    title=item.get("title", ""),
                    institution=item.get("organisation", ""),
                    url=url,
                    description=item.get("description", "")[:2000],
                    location=item.get("country", ""),
                    deadline=item.get("applicationDeadline", ""),
                    source="EURAXESS",
                ))
        except Exception as e:
            logger.warning(f"EURAXESS fetch error for '{kw}': {e}")
        time.sleep(1.5)
    return _dedupe(all_jobs)


# ──────────────────────────────────────────
# Source 4: Academic Positions (HTML scraping)
# ──────────────────────────────────────────

def fetch_academic_positions() -> list[Job]:
    """Scrape academicpositions.com search results."""
    search_urls = [
        "https://academicpositions.com/jobs/position/post-doc/field/artificial-intelligence",
        "https://academicpositions.com/jobs/position/post-doc/field/computer-science",
        "https://academicpositions.com/jobs/position/post-doc/field/neuroscience",
    ]
    all_jobs = []
    for url in search_urls:
        try:
            resp = _safe_get(url)
            if resp is None:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            # Each job listing is in an article or li with class containing "job"
            cards = soup.select("article.job-ad, li.job-ad, div.job-listing, [class*='job-ad']")
            if not cards:
                # Fallback: look for any link that looks like a job
                cards = soup.select("h2 a, h3 a")
            for card in cards[:30]:
                if card.name in ("a",):
                    title = card.get_text(strip=True)
                    href = card.get("href", "")
                else:
                    link_el = card.select_one("a[href]")
                    if not link_el:
                        continue
                    title = link_el.get_text(strip=True)
                    href = link_el.get("href", "")
                if not href.startswith("http"):
                    href = "https://academicpositions.com" + href
                desc_el = card.select_one("p, .description, .summary")
                desc = desc_el.get_text(strip=True)[:1000] if desc_el else ""
                inst_el = card.select_one(".institution, .employer, .university")
                institution = inst_el.get_text(strip=True) if inst_el else ""
                all_jobs.append(Job(
                    title=title,
                    institution=institution,
                    url=href,
                    description=desc,
                    source="AcademicPositions",
                ))
        except Exception as e:
            logger.warning(f"AcademicPositions scrape error for {url}: {e}")
        time.sleep(2)
    return _dedupe(all_jobs)


# ──────────────────────────────────────────
# Source 5: Nature Careers RSS
# ──────────────────────────────────────────

def fetch_nature_careers() -> list[Job]:
    """Nature Careers has an RSS feed for postdoc computing jobs."""
    feeds = [
        "https://www.nature.com/naturecareers/jobs/rss?discipline=computing&position=postdoc",
        "https://www.nature.com/naturecareers/jobs/rss?discipline=neuroscience&position=postdoc",
    ]
    all_jobs = []
    for url in feeds:
        jobs = _parse_rss(url, "NatureCareers")
        all_jobs.extend(jobs)
        time.sleep(1)
    return _dedupe(all_jobs)


# ──────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────

def _is_postdoc(title: str) -> bool:
    title_lower = title.lower()
    return any(kw in title_lower for kw in [
        "postdoc", "post-doc", "post doc", "postdoctoral", "research fellow",
        "research associate", "researcher"
    ])


def _dedupe(jobs: list[Job]) -> list[Job]:
    seen = set()
    out = []
    for j in jobs:
        if j.url not in seen and j.url:
            seen.add(j.url)
            out.append(j)
    return out


def fetch_all() -> list[Job]:
    """Fetch from all sources and deduplicate."""
    all_jobs: list[Job] = []
    sources = [
        ("Academic Jobs Online", fetch_academic_jobs_online),
        ("jobs.ac.uk", fetch_jobs_ac_uk),
        ("EURAXESS", fetch_euraxess),
        ("Academic Positions", fetch_academic_positions),
        ("Nature Careers", fetch_nature_careers),
    ]
    for name, fn in sources:
        logger.info(f"Fetching from {name}...")
        try:
            jobs = fn()
            logger.info(f"  → {len(jobs)} listings found")
            all_jobs.extend(jobs)
        except Exception as e:
            logger.error(f"  → Error: {e}")

    return _dedupe(all_jobs)
