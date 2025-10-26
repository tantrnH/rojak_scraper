"""Command line interface for scraping Shopee "rojak" reviews."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from typing import Iterable, List, Sequence, Set

from .filters import classify_rojak
from .google_sheets import GoogleSheetsWriter, SheetConfig
from .shopee import ShopeeClient

LOGGER = logging.getLogger(__name__)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape Shopee rojak comments into Google Sheets")
    parser.add_argument("--credentials", required=True, help="Path to the Google service account JSON file")
    parser.add_argument("--sheet-title", default="Shopee Rojak Dataset", help="Name of the Google Sheet document")
    parser.add_argument(
        "--worksheet-title", default="Rojak Sentences", help="Worksheet title inside the Google Sheet"
    )
    parser.add_argument("--category-id", type=int, default=11000168, help="Shopee category ID to crawl")
    parser.add_argument("--max-products", type=int, default=40, help="How many popular products to inspect")
    parser.add_argument("--review-pages", type=int, default=20, help="How many pages of reviews per product to fetch")
    parser.add_argument("--page-size", type=int, default=59, help="Number of reviews requested per API page")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay in seconds between API calls")
    parser.add_argument("--max-retries", type=int, default=3, help="Maximum number of retries for failed requests")
    parser.add_argument("--batch-size", type=int, default=20, help="Number of rows to buffer before writing to Sheets")
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Enable continuous mode (loop indefinitely until interrupted)",
    )
    parser.add_argument(
        "--loop-sleep",
        type=float,
        default=1800.0,
        help="Seconds to sleep between loops when --continuous is supplied",
    )
    parser.add_argument(
        "--use-system-proxy",
        action="store_true",
        help="Allow requests to use proxy variables from the environment",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging output",
    )
    return parser.parse_args(argv)


def _normalise_comment(text: str) -> str:
    return " ".join(text.split())


def _extract_comment(review: dict) -> str:
    if not isinstance(review, dict):
        return ""
    comment = review.get("comment")
    if comment:
        return str(comment)
    extended = review.get("extended_text") or {}
    if isinstance(extended, dict):
        text = extended.get("text")
        if text:
            return str(text)
    return ""


def _iter_candidate_comments(client: ShopeeClient, *, category_id: int, max_products: int, review_pages: int, page_size: int):
    for review in client.iter_popular_reviews(
        category_id=category_id,
        max_items=max_products,
        max_review_pages=review_pages,
        page_size=page_size,
    ):
        comment = _extract_comment(review)
        if not comment:
            continue
        info = review.get("item_info") or {}
        review_id = review.get("reviewid") or review.get("cmtid") or ""
        rating = review.get("rating_star") or review.get("rating") or ""
        yield {
            "comment": comment,
            "normalised": _normalise_comment(comment),
            "item_name": info.get("name", ""),
            "item_url": info.get("url", ""),
            "review_id": str(review_id),
            "rating": str(rating),
        }


def _process_once(
    client: ShopeeClient,
    sheets: GoogleSheetsWriter,
    *,
    category_id: int,
    max_products: int,
    review_pages: int,
    page_size: int,
    batch_size: int,
    seen_comments: Set[str],
) -> int:
    buffer: List[Sequence[str]] = []
    new_rows = 0

    for candidate in _iter_candidate_comments(
        client,
        category_id=category_id,
        max_products=max_products,
        review_pages=review_pages,
        page_size=page_size,
    ):
        normalised = candidate["normalised"]
        if not normalised:
            continue
        key = normalised.lower()
        if key in seen_comments:
            continue
        decision = classify_rojak(normalised)
        if not decision.is_rojak:
            continue
        row = (
            candidate["item_name"],
            candidate["item_url"],
            candidate["review_id"],
            candidate["rating"],
            normalised,
        )
        buffer.append(row)
        seen_comments.add(key)
        new_rows += 1
        if len(buffer) >= batch_size:
            sheets.append_rows(buffer)
            buffer.clear()

    if buffer:
        sheets.append_rows(buffer)
        buffer.clear()

    return new_rows


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.verbose)

    config = SheetConfig(spreadsheet_title=args.sheet_title, worksheet_title=args.worksheet_title)
    sheets = GoogleSheetsWriter(args.credentials, config=config)
    seen_comments = sheets.fetch_existing_comments()
    LOGGER.info("Loaded %d existing comments from Google Sheets", len(seen_comments))

    client = ShopeeClient(
        delay=args.delay,
        max_retries=args.max_retries,
        use_system_proxy=args.use_system_proxy,
    )

    loop = 0
    while True:
        loop += 1
        LOGGER.info("Starting scraping loop %d", loop)
        new_rows = _process_once(
            client,
            sheets,
            category_id=args.category_id,
            max_products=args.max_products,
            review_pages=args.review_pages,
            page_size=args.page_size,
            batch_size=args.batch_size,
            seen_comments=seen_comments,
        )
        LOGGER.info("Loop %d captured %d new rojak comments", loop, new_rows)
        if not args.continuous:
            break
        LOGGER.info("Sleeping for %.0f seconds before the next loop", args.loop_sleep)
        time.sleep(args.loop_sleep)

    return 0


if __name__ == "__main__":
    sys.exit(main())

