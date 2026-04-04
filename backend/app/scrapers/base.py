"""
Shared HTTP client and retry logic for all scrapers.
"""
import asyncio
import logging

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import settings

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "application/json, text/html, */*",
}


def build_client(timeout: float = 30.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers=HEADERS,
        timeout=timeout,
        follow_redirects=True,
    )


@retry(
    stop=stop_after_attempt(settings.SCRAPER_MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    reraise=True,
)
async def fetch_json(client: httpx.AsyncClient, url: str, **kwargs) -> dict | list:
    await asyncio.sleep(settings.SCRAPER_DELAY_SECONDS)
    response = await client.get(url, **kwargs)
    response.raise_for_status()
    return response.json()


@retry(
    stop=stop_after_attempt(settings.SCRAPER_MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    reraise=True,
)
async def fetch_html(client: httpx.AsyncClient, url: str, **kwargs) -> str:
    await asyncio.sleep(settings.SCRAPER_DELAY_SECONDS)
    response = await client.get(url, **kwargs)
    response.raise_for_status()
    return response.text
