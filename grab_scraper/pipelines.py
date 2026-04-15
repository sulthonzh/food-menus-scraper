"""Pipelines for validation, cleaning, and dedup."""

import logging
import re

from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem

logger = logging.getLogger(__name__)


class ValidationPipeline:

    required_fields = ["outlet_name", "menu_name"]

    def process_item(self, item, spider=None):
        adapter = ItemAdapter(item)
        for field in self.required_fields:
            value = adapter.get(field)
            if not value or not str(value).strip():
                raise DropItem(f"Missing required field '{field}' in item: {dict(adapter)}")
        return item


class DataCleaningPipeline:

    PROMO_PCT_PATTERN = re.compile(r"(\d+)%")
    PROMO_NOMINAL_PATTERN = re.compile(r"Rp([\d.,]+)")

    def process_item(self, item, spider=None):
        adapter = ItemAdapter(item)

        for field in ["outlet_name", "category_name", "menu_name", "menu_description"]:
            val = adapter.get(field)
            if val:
                adapter[field] = str(val).strip()

        adapter["original_price"] = self._parse_price(adapter.get("original_price"))

        promo_price = adapter.get("promo_price")
        adapter["promo_price"] = self._parse_price(promo_price) if promo_price else None

        promo_text = adapter.get("promo_percentage") or ""
        pct_match = self.PROMO_PCT_PATTERN.search(str(promo_text))
        adapter["promo_percentage"] = f"{pct_match.group(1)}%" if pct_match else None

        promo_nom = adapter.get("promo_nominal") or ""
        nom_match = self.PROMO_NOMINAL_PATTERN.search(str(promo_nom))
        adapter["promo_nominal"] = f"Rp{nom_match.group(1)}" if nom_match else None

        if not adapter.get("promo_price"):
            adapter["promo_nominal"] = None
            adapter["promo_percentage"] = None

        return item

    def _parse_price(self, value):
        """Parse price string to clean format like 'Rp25.000'."""
        if not value:
            return None
        cleaned = str(value).strip()
        if not cleaned:
            return None
        return cleaned


class DuplicateFilterPipeline:

    def __init__(self):
        self.seen = set()

    def process_item(self, item, spider=None):
        adapter = ItemAdapter(item)

        key = (
            adapter.get("outlet_name", ""),
            adapter.get("category_name", ""),
            adapter.get("menu_name", ""),
        )

        if key in self.seen:
            raise DropItem(f"Duplicate item: {key}")

        self.seen.add(key)
        return item
