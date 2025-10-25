"""Client helpers for interacting with Shopee's public JSON endpoints."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List, Optional

import requests

LOGGER = logging.getLogger(__name__)


@dataclass
class ShopeeItem:
    """Minimal representation of a Shopee product."""

    item_id: int
    shop_id: int
    name: str
    url: str


class ShopeeAPIError(RuntimeError):
    """Raised when the Shopee API returns an unexpected payload."""


class ShopeeClient:
    """Lightweight wrapper around a :class:`requests.Session` for Shopee."""

    BASE_URL = "https://shopee.com.my"

    def __init__(
        self,
        *,
        delay: float = 1.0,
        max_retries: int = 3,
        proxies: Optional[Dict[str, str]] = None,
        timeout: float = 10.0,
        use_system_proxy: bool = False,
    ) -> None:
        """Create a new client.

        Parameters
        ----------
        delay:
            Optional delay (in seconds) injected between network calls to avoid
            hammering the API. Defaults to one second.
        max_retries:
            Number of times a request will be retried when Shopee responds with
            transient failures. Defaults to three attempts.
        proxies:
            Optional dictionary of HTTP/HTTPS proxies passed to
            :meth:`requests.Session.request`.
        timeout:
            Timeout in seconds for individual HTTP requests.
        use_system_proxy:
            When ``False`` the underlying :class:`requests.Session` ignores
            proxy settings inherited from the execution environment. This is
            helpful when running behind a corporate proxy that blocks Shopee's
            API. Defaults to ``False``.
        """

        self.delay = delay
        self.max_retries = max_retries
        self.proxies = proxies
        self.timeout = timeout

        self._session = requests.Session()
        if not use_system_proxy:
            self._session.trust_env = False

        self._session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 "
                    "Safari/537.36"
                ),
                "Accept": "application/json",
                "Referer": self.BASE_URL,
            }
        )

    def _request(self, method: str, path: str, **kwargs) -> Dict:
        url = f"{self.BASE_URL}{path}"
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self._session.request(
                    method,
                    url,
                    timeout=self.timeout,
                    proxies=self.proxies,
                    **kwargs,
                )
                if response.status_code >= 400:
                    LOGGER.warning(
                        "Shopee API %s %s failed with status %s", method, path, response.status_code
                    )
                    response.raise_for_status()
                data = response.json()
                return data
            except (requests.RequestException, ValueError) as exc:
                LOGGER.warning(
                    "Attempt %s/%s for %s %s failed: %s", attempt, self.max_retries, method, path, exc
                )
                if attempt >= self.max_retries:
                    raise
                time.sleep(self.delay)
        raise ShopeeAPIError(f"Failed to call Shopee API at {path}")

    def fetch_popular_items(
        self,
        *,
        category_id: int,
        limit: int = 60,
        offset: int = 0,
    ) -> List[ShopeeItem]:
        """Return a slice of the most popular items for a category."""

        params = {
            "by": "sales",
            "order": "desc",
            "page_type": "search",
            "version": 2,
            "scenario": "PAGE_CATEGORY",
            "keyword": "",
            "newest": offset,
            "limit": limit,
            "categoryids": str(category_id),
        }
        payload = self._request("GET", "/api/v4/search/search_items", params=params)
        items_data = payload.get("items") or []
        items: List[ShopeeItem] = []
        for entry in items_data:
            basic = entry.get("item_basic") or {}
            item_id = basic.get("itemid")
            shop_id = basic.get("shopid")
            name = basic.get("name")
            if item_id is None or shop_id is None or not name:
                continue
            url = f"{self.BASE_URL}/{basic.get('name', '').replace(' ', '-')}-i.{shop_id}.{item_id}"
            items.append(ShopeeItem(item_id=item_id, shop_id=shop_id, name=name, url=url))
        LOGGER.info("Fetched %d popular items (offset=%d, limit=%d)", len(items), offset, limit)
        time.sleep(self.delay)
        return items

    def iter_reviews(
        self,
        *,
        shop_id: int,
        item_id: int,
        max_pages: int = 20,
        page_size: int = 59,
    ) -> Iterator[Dict]:
        """Yield review dictionaries for a given product."""

        for page in range(max_pages):
            offset = page * page_size
            params = {
                "itemid": item_id,
                "shopid": shop_id,
                "offset": offset,
                "limit": page_size,
                "type": 0,
                "filter": 0,
                "flag": 1,
            }
            payload = self._request("GET", "/api/v2/item/get_ratings", params=params)
            data = payload.get("data") or {}
            ratings = data.get("ratings") or []
            if not ratings:
                LOGGER.info(
                    "No more ratings for item %s/%s after page %s", shop_id, item_id, page
                )
                break
            for rating in ratings:
                yield rating
            if len(ratings) < page_size:
                LOGGER.info(
                    "Reached last ratings page for item %s/%s (page %s)", shop_id, item_id, page
                )
                break
            time.sleep(self.delay)

    def iter_popular_reviews(
        self,
        *,
        category_id: int,
        max_items: int,
        max_review_pages: int = 20,
        page_size: int = 59,
    ) -> Iterator[Dict]:
        """Iterate over review payloads for the most popular products."""

        processed = 0
        offset = 0
        limit = min(60, max_items)
        while processed < max_items:
            remaining = max_items - processed
            batch_limit = min(limit, remaining)
            items = self.fetch_popular_items(category_id=category_id, limit=batch_limit, offset=offset)
            if not items:
                LOGGER.info("No more popular items returned by Shopee (offset=%d)", offset)
                break
            for item in items:
                for review in self.iter_reviews(
                    shop_id=item.shop_id,
                    item_id=item.item_id,
                    max_pages=max_review_pages,
                    page_size=page_size,
                ):
                    review["item_info"] = {
                        "item_id": item.item_id,
                        "shop_id": item.shop_id,
                        "name": item.name,
                        "url": item.url,
                    }
                    yield review
                processed += 1
                if processed >= max_items:
                    break
            offset += len(items)
            if len(items) < batch_limit:
                break

