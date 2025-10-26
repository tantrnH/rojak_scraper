"""Utility helpers for writing results into Google Sheets."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Set

import gspread
from gspread.exceptions import SpreadsheetNotFound, WorksheetNotFound

LOGGER = logging.getLogger(__name__)


@dataclass
class SheetConfig:
    spreadsheet_title: str
    worksheet_title: str = "Rojak Sentences"
    header: Sequence[str] = (
        "Product Name",
        "Product URL",
        "Review ID",
        "Rating",
        "Comment",
    )


class GoogleSheetsWriter:
    """Thin wrapper around :mod:`gspread` for appending rows."""

    def __init__(self, credentials_path: str, config: SheetConfig | None = None) -> None:
        self.config = config or SheetConfig(spreadsheet_title="Shopee Rojak Dataset")
        self._client = gspread.service_account(filename=credentials_path)

        try:
            self._spreadsheet = self._client.open(self.config.spreadsheet_title)
            LOGGER.info("Opened existing spreadsheet '%s'", self.config.spreadsheet_title)
        except SpreadsheetNotFound:
            self._spreadsheet = self._client.create(self.config.spreadsheet_title)
            LOGGER.info("Created new spreadsheet '%s'", self.config.spreadsheet_title)

        try:
            self._worksheet = self._spreadsheet.worksheet(self.config.worksheet_title)
        except WorksheetNotFound:
            self._worksheet = self._spreadsheet.add_worksheet(
                title=self.config.worksheet_title, rows=1000, cols=len(self.config.header)
            )
            LOGGER.info("Created worksheet '%s'", self.config.worksheet_title)

        existing_header = self._worksheet.row_values(1)
        if existing_header != list(self.config.header):
            LOGGER.info("Updating worksheet header")
            self._worksheet.resize(rows=1, cols=len(self.config.header))
            self._worksheet.update("A1", [list(self.config.header)])

    def fetch_existing_comments(self) -> Set[str]:
        """Return the set of comments already stored in the sheet."""

        values = self._worksheet.col_values(len(self.config.header))
        if not values:
            return set()
        # Skip header row
        return {value.strip().lower() for value in values[1:] if value}

    def append_rows(self, rows: Iterable[Sequence[str]]) -> None:
        rows_list: List[Sequence[str]] = list(rows)
        if not rows_list:
            return
        self._worksheet.append_rows(rows_list, value_input_option="RAW")
        LOGGER.info("Appended %d rows to worksheet '%s'", len(rows_list), self.config.worksheet_title)

