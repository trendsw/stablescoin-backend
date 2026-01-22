import httpx
import logging
import re
from datetime import datetime, timedelta, timezone
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

MIN_CONTENT_LENGTH = 200
JST = timezone(timedelta(hours=9))

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


def normalize_date(raw_date: str | None) -> datetime | None:
    if not raw_date:
        return None

    raw = raw_date.lower().strip()
    now = datetime.now(JST).replace(microsecond=0)

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
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
        else:
            dt = dt.astimezone(JST)
            
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

    # 1️⃣ Handle protocol-relative URLs
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        url = urljoin(base_url, url)

    # 2️⃣ Unwrap Next.js / Nuxt / Vercel images
    parsed = urlparse(url)
    if "/_next/image" in parsed.path:
        qs = parse_qs(parsed.query)
        if "url" in qs:
            url = unquote(qs["url"][0])

    # 3️⃣ CoinTelegraph CDN unwrap (optional)
    if "images.cointelegraph.com" in url and "https://" in url:
        url = url[url.rfind("https://"):]

    # --- unwrap Decrypt proxy ---
    if "img.decrypt.co" in url and "/plain/" in url:
        url = url.split("/plain/", 1)[1]
        url = unquote(url)

    # remove @webp
    if "@webp" in url:
        url = url.split("@webp", 1)[0]
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

def is_valid_image_url(
    url: str,
    allowed_extensions: list[str] | None,
) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()

    # If extensions are configured → enforce them
    if allowed_extensions:
        for ext in allowed_extensions:
            if path.endswith("." + ext):
                return True

        # No extension → ACCEPT (important)
        if "." not in path.rsplit("/", 1)[-1]:
            return True

        # Has extension but not allowed → reject
        return False

    # No extension rules → accept everything
    return True

def extract_image_from_imgs(
    html: str,
    base_url: str,
    image_patterns: list[str],
    parent_classes: list[str] | None = None,
    image_extensions: list[str] | None = None,
) -> str | None:
    
    soup = BeautifulSoup(html, "lxml")
    parents = []

    # Collect parent elements
    if parent_classes:
        for cls in parent_classes:
            found = soup.select(f".{cls}")
            if found:
                parents.extend(found)

    # Fallback to entire document
    if not parents:
        parents = [soup]

    candidate_images = []

    for parent in parents:
        for img in parent.find_all("img"):
            src = (
                img.get("data-src")
                or img.get("data-lazy-src")
                or img.get("data-original")
                or img.get("src")
            )
            if not src:
                continue

            src = normalize_image_url(src, base_url)

            if not is_valid_image_url(
                src,
                image_extensions,
            ):
                continue

            # Skip SVGs or logos
            if src.lower().endswith(".svg") or "/themes/decrypt-media/" in src:
                continue

            # Must match image_patterns
            if image_patterns and not any(p in src for p in image_patterns):
                continue

            # Try to get image width/height from attributes
            width = img.get("width")
            height = img.get("height")
            size = 0
            try:
                size = int(width) * int(height)
            except (TypeError, ValueError):
                # fallback to 0 if not available
                size = 0

            # Check srcset for higher resolution
            srcset = img.get("srcset")
            if srcset:
                # Pick the largest width in srcset
                matches = re.findall(r"(\S+)\s+(\d+)x", srcset)
                for m_url, m_w in matches:
                    try:
                        m_w = int(m_w)
                        if m_w > size:
                            candidate_images.append((m_w, normalize_image_url(m_url, base_url)))
                    except:
                        continue

            candidate_images.append((size, src))

    # Return the image with the largest size
    if candidate_images:
        # sort by size descending
        candidate_images.sort(key=lambda x: x[0], reverse=True)
        return candidate_images[0][1]

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


def is_recent(publish_date, days: int = 2) -> bool:
    if not publish_date:
        return None
    
    if publish_date.tzinfo is None:
        publish_date = publish_date.replace(tzinfo=timezone.utc)
    
    now = datetime.now(timezone.utc)
    return publish_date >= (now-timedelta(days=days))

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

    if not text or len(text.strip()) < MIN_CONTENT_LENGTH:
        return None

    publish_date = normalize_date(metadata.date if metadata else None)
    
    if not is_recent(publish_date, days=10):
       return None 

    return {
        "title": metadata.title if metadata else None,
        "content": text.strip(),
        "publish_date": publish_date.isoformat() if publish_date else None,
        "url": metadata.url if metadata and metadata.url else url,
    }

def is_url_restricted(url:str, source: dict) -> bool:
    restrictions = source.get("url_restriction")
    if not restrictions:
        return False
    
    return any(restricted in url for restricted in restrictions)




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
                if is_url_restricted(url, source):
                    continue
                
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
                    parent_classes=source.get("image_parent_classes"),
                    image_extensions=source.get("image_extensions"),
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
