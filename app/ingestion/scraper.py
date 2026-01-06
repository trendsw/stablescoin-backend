import httpx
import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential
from dateutil import parser as date_parser
import trafilatura

from ingestion.sources import load_sources


# -------------------------
# Logging
# -------------------------
logger = logging.getLogger(__name__)


# -------------------------
# HTTP fetch (server-safe)
# -------------------------
def fetch_html(url: str, timeout: int = 15) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; NewsCrawler/1.0)"
    }

    with httpx.Client(
        headers=headers,
        follow_redirects=True,
        timeout=timeout
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def discover_article_urls(html: str, base_url: str, patterns: list[str]) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    domain = urlparse(base_url).netloc
    urls: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].split("#")[0]
        url = urljoin(base_url, href)
        parsed = urlparse(url)

        if parsed.netloc != domain:
            continue

        path = parsed.path

        for pattern in patterns:
            # Regex pattern
            if pattern.startswith("^"):
                if re.search(pattern, path):
                    urls.add(url)
                    break
            # Simple substring
            elif pattern in path:
                urls.add(url)
                break

    logger.info("Discovered %d article URLs from %s", len(urls), base_url)
    return list(urls)

# -------------------------
# Normalize publish dates
# -------------------------
def normalize_date(raw_date: str | None) -> datetime | None:
    if not raw_date:
        return None

    raw = raw_date.lower().strip()
    now = datetime.utcnow()

    match = re.search(r"(\d+)\s*(minute|min|hour|day|week|month)s?\s*ago", raw)
    if match:
        value = int(match.group(1))
        unit = match.group(2)

        if unit.startswith("min"):
            return now - timedelta(minutes=value)
        if unit.startswith("hour"):
            return now - timedelta(hours=value)
        if unit.startswith("day"):
            return now - timedelta(days=value)
        if unit.startswith("week"):
            return now - timedelta(weeks=value)
        if unit.startswith("month"):
            return now - timedelta(days=value * 30)

    try:
        return date_parser.parse(raw, fuzzy=True)
    except Exception:
        return None


# -------------------------
# Extract article content
# -------------------------
def extract_article(url: str) -> dict | None:
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return None

    metadata = trafilatura.metadata.extract_metadata(downloaded)
    text = trafilatura.extract(
        downloaded,
        include_comments=False,
        include_tables=False
    )

    if not text:
        return None

    publish_date = normalize_date(metadata.date if metadata else None)

    return {
        "title": metadata.title if metadata else None,
        "content": text.strip(),
        "publish_date": publish_date.isoformat() if publish_date else None,
        "url": metadata.url if metadata and metadata.url else url,
    }


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=10),
    reraise=True,
)
async def scrape_all_sources() -> list[dict]:
    sources = load_sources()
    all_articles: list[dict] = []

    for source in sources:
        logger.info("Scraping source: %s", source["name"])
        strategy = source.get("fetch_strategy", "httpx")
        if strategy == "trafilatura":
            html = trafilatura.fetch_url(source["url"])
        else:
            html = fetch_html(source["url"])

        article_urls = discover_article_urls(
            html,
            source["url"],
            source["article_url_patterns"],
        )

        for url in article_urls:
            article = extract_article(url)
            if not article:
                continue
            article["name"] = source["name"]
            article["country"] = source["country"]
            article["credibility_score"] = 0  
            all_articles.append(article)

    return all_articles
