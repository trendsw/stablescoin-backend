import httpx
import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse, parse_qs, unquote

from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential
from dateutil import parser as date_parser
import trafilatura

from ingestion.sources import load_sources
from playwright.async_api import async_playwright
from api.routes.articles import generate_slug

# -------------------------
# Logging
# -------------------------
logger = logging.getLogger(__name__)


# -------------------------
# HTTP fetch (server-safe)
# -------------------------
@retry(stop=stop_after_attempt(2))
def fetch_html(url: str, timeout: int = 50) -> str:
    headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Referer": "https://www.google.com/",
    }
    # headers = {
    #     "User-Agent": "Mozilla/5.0 (compatible; NewsCrawler/1.0)"
    # }
    with httpx.Client(
        headers=headers,
        follow_redirects=True,
        timeout=timeout
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text
    
async def fetch_html_browser(url: str) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        )

        page = await context.new_page()

        #  Block heavy resources (huge speed win)
        await page.route(
            "**/*",
            lambda route, request: (
                route.abort()
                if request.resource_type in {"image", "font", "media"}
                else route.continue_()
            ),
        )

        #  Load DOM only
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        #  Ensure <a> tags exist (very fast)
        try:
            await page.wait_for_selector("a", timeout=5000)
        except:
            pass

        html = await page.content()
        await browser.close()
        return html    

def discover_article_urls(html: str, base_url: str, patterns: list[str]) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    domain = urlparse(base_url).netloc
    # print("domain===>", domain)
    urls: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].split("#")[0]
        # print("href===>", href)
        url = urljoin(base_url, href)
        # print("url===>", url)
        parsed = urlparse(url)
        # print("parsed===>", parsed)
        # print("parsed netloc===>", parsed.netloc)
        if parsed.netloc != domain:
            continue

        path = parsed.path
        # print("paths=======>", path)
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
# def normalize_date(raw_date: str | None) -> datetime | None:
#     if not raw_date:
#         return None

#     raw = raw_date.lower().strip()
#     now = datetime.utcnow()

#     match = re.search(r"(\d+)\s*(minute|min|hour|day|week|month)s?\s*ago", raw)
#     if match:
#         value = int(match.group(1))
#         unit = match.group(2)

#         if unit.startswith("min"):
#             return now - timedelta(minutes=value)
#         if unit.startswith("hour"):
#             return now - timedelta(hours=value)
#         if unit.startswith("day"):
#             return now - timedelta(days=value)
#         if unit.startswith("week"):
#             return now - timedelta(weeks=value)
#         if unit.startswith("month"):
#             return now - timedelta(days=value * 30)

#     try:
#         return date_parser.parse(raw, fuzzy=True)
#     except Exception:
#         return None

def normalize_date(raw_date: str | None) -> datetime | None:
    if not raw_date:
        return None

    raw = raw_date.lower().strip()
    now = datetime.utcnow().replace(microsecond=0)

    # Relative time
    match = re.search(
        r"(\d+)\s*(second|sec|minute|min|hour|day|week|month|year)s?\s*ago",
        raw
    )

    if match:
        value = int(match.group(1))
        unit = match.group(2)

        if unit.startswith(("sec", "second")):
            return now - timedelta(seconds=value)
        if unit.startswith(("min", "minute")):
            return now - timedelta(minutes=value)
        if unit.startswith("hour"):
            return now - timedelta(hours=value)
        if unit.startswith("day"):
            return now - timedelta(days=value)
        if unit.startswith("week"):
            return now - timedelta(weeks=value)
        if unit.startswith("month"):
            return now - timedelta(days=value * 30)
        if unit.startswith("year"):
            return now - timedelta(days=value * 365)

    # Absolute date
    try:
        # IMPORTANT: inject time if missing
        dt = date_parser.parse(raw, fuzzy=True, default=now)
        return dt.replace(microsecond=0)
    except Exception:
        return None
    
def unwrap_next_image(url: str) -> str:
    if "_next/image" not in url:
        return url

    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    real = params.get("url")
    if real:
        return unquote(real[0])

    return url
def normalize_image_url(url: str, base_url: str) -> str:
    url = url.strip()

    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        url = urljoin(base_url, url)

    # Unwrap Next.js / Nuxt / Vercel proxy images
    url = unwrap_next_image(url)

    # CoinTelegraph CDN unwrap
    if "images.cointelegraph.com" in url and "https://" in url:
        url = url[url.rfind("https://"):]

    return url

def parse_srcset(srcset: str) -> list[str]:
    items = []
    for part in srcset.split(","):
        parts = part.strip().split()
        if len(parts) == 2 and parts[1].endswith("w"):
            try:
                width = int(parts[1][:-1])
                items.append((width, parts[0]))
            except ValueError:
                continue
    # largest width first
    items.sort(reverse=True)
    return [url for _, url in items]


def extract_image_from_imgs(
    html: str,
    base_url: str,
    image_patterns: list[str],
    parent_classes: list[str] | None = None,
) -> str | None:

    soup = BeautifulSoup(html, "lxml")

    # -------------------------
    # 1️⃣ Parent selector priority
    # -------------------------
    if parent_classes:
        for selector in parent_classes:

            # allow tag selectors like "figure"
            if selector.isalpha():
                parent = soup.find(selector)
            else:
                parent = soup.select_one(f".{selector}")

            if not parent:
                continue

            img = parent.find("img")
            if not img:
                continue

            src = (
                img.get("data-src")
                or img.get("data-lazy-src")
                or img.get("data-original")
                or img.get("src")
            )
            if not src:
                continue

            src = normalize_image_url(src, base_url)

            if not image_patterns or any(p in src for p in image_patterns):
                return src

    # -------------------------
    # 2️⃣ Fallback (unchanged)
    # -------------------------
    for img in soup.find_all("img"):
        src = (
            img.get("data-src")
            or img.get("data-lazy-src")
            or img.get("data-original")
            or img.get("src")
        )
        if not src:
            continue

        src = normalize_image_url(src, base_url)

        if not image_patterns or any(p in src for p in image_patterns):
            return src

    return None

async def fetch_coindesk_main(url: str) -> str | None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page()

        # Block unnecessary resources
        async def block_resources(route):
            if route.request.resource_type in ["image", "stylesheet", "font", "media"]:
                await route.abort()
            else:
                await route.continue_()
        await page.route("**/*", block_resources)

        await page.goto(url, timeout=20000)
        await page.wait_for_selector("main", timeout=10000)

        html = await page.content()
        await browser.close()

    soup = BeautifulSoup(html, "lxml")
    main_tag = soup.find("main")
    return str(main_tag) if main_tag else None

async def extract_article(url: str) -> dict | None:
    
    if "coindesk.com" in url:
        main_html = await fetch_coindesk_main(url)
        if not main_html:
            return None
        downloaded = f"<html><body>{main_html}</body></html>"
    else:
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


# @retry(
#     stop=stop_after_attempt(3),
#     wait=wait_exponential(min=1, max=10),
#     reraise=True,
# )
async def scrape_all_sources() -> list[dict]:
    sources = load_sources()
    all_articles: list[dict] = []

    for source in sources:
        logger.info("Scraping source: %s", source["name"])

        try:
            strategy = source.get("fetch_strategy", "httpx")

            if strategy == "trafilatura":
                html = trafilatura.fetch_url(source["url"])
            else:
                if source["name"] in ["CoinDesk", "cryptotimes"]:
                    html = await fetch_html_browser(source["url"])
                else:
                    html = fetch_html(source["url"])
            if not html:
                logger.warning(
                    "No HTML returned",
                    source=source["name"],
                    url=source["url"],
                )
                continue

            article_urls = discover_article_urls(
                html,
                source["url"],
                source["article_url_patterns"],
            )

        except Exception as e:
            logger.error(
                "Source scrape failed",
                source=source["name"],
                url=source["url"],
                error=str(e),
                exc_info=True,
            )
            continue

        # ---- article loop ----
        for url in article_urls:
            try:
                article = await extract_article(url)
                if not article:
                    continue
                if source["name"] == "CoinDesk":
                    article_html = await fetch_html_browser(url)
                else:
                    article_html = fetch_html(url)
                # print("image_url_patterns", source.get("image_url_patterns", []))
                image_url = extract_image_from_imgs(
                    html=article_html,
                    base_url=url,
                    image_patterns=source.get("image_url_patterns", []),
                    parent_classes=source.get("image_parent_classes"),  # ⭐ NEW
                )
                # print("parent_classes", source.get("image_parent_classes"))
                print("image_url===>", image_url)
                article["name"] = source["name"]
                article["country"] = source["country"]
                article["credibility_score"] = 0
                article["image_url"] = image_url
                
                all_articles.append(article)

            except Exception as e:
                logger.warning(
                    "Article extraction failed",
                    source=source["name"],
                    url=url,
                    error=str(e),
                )
                continue
    logger.info(f"scrape_completed, article_count={len(all_articles)}")
    return all_articles
