import asyncio
from core.logging import log
from ingestion.scraper import scrape_region_sources
from ingestion.persist import save_region_articles
async def run_region_pipeline_async():
 
    articles = await scrape_region_sources()
    if not articles:
        log.info("pipeline_no_articles")
        return

    article_ids = save_region_articles(articles)
    print("regional_article ids===>", article_ids)
    log.info("regional_articles_saved", count=len(article_ids))

    
    


def run_region_pipeline():
    """
    Synchronous entry point for schedulers / workers.
    Safely executes async pipeline.
    """
    try:
        asyncio.run(run_region_pipeline_async())
    except RuntimeError as e:
        # Handles case where an event loop already exists (rare but possible)
        log.warning("event_loop_exists_fallback", error=str(e))
        loop = asyncio.get_event_loop()
        loop.run_until_complete(run_region_pipeline_async())