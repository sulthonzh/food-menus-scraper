"""Tests for item pipelines."""

import pytest
from scrapy.exceptions import DropItem

from grab_scraper.items import GrabMenuItem
from grab_scraper.pipelines import (
    DataCleaningPipeline,
    DuplicateFilterPipeline,
    ValidationPipeline,
)


def _make_item(
    outlet_name="Test Outlet",
    category_name="Category A",
    menu_name="Test Menu",
    menu_description="A description",
    original_price="Rp25.000",
    promo_price=None,
    promo_nominal=None,
    promo_percentage=None,
    availability="Available",
):
    item = GrabMenuItem()
    item["outlet_name"] = outlet_name
    item["category_name"] = category_name
    item["menu_name"] = menu_name
    item["menu_description"] = menu_description
    item["original_price"] = original_price
    item["promo_price"] = promo_price
    item["promo_nominal"] = promo_nominal
    item["promo_percentage"] = promo_percentage
    item["availability"] = availability
    return item


class TestValidationPipeline:
    def setup_method(self):
        self.pipeline = ValidationPipeline()

    def test_valid_item_passes(self):
        item = _make_item()
        result = self.pipeline.process_item(item, None)
        assert result is item

    def test_missing_outlet_name_dropped(self):
        item = _make_item(outlet_name="")
        with pytest.raises(DropItem, match="outlet_name"):
            self.pipeline.process_item(item, None)

    def test_missing_menu_name_dropped(self):
        item = _make_item(menu_name="")
        with pytest.raises(DropItem, match="menu_name"):
            self.pipeline.process_item(item, None)

    def test_none_menu_name_dropped(self):
        item = _make_item()
        del item["menu_name"]
        with pytest.raises(DropItem):
            self.pipeline.process_item(item, None)


class TestDataCleaningPipeline:
    def setup_method(self):
        self.pipeline = DataCleaningPipeline()

    def test_strips_whitespace_from_text(self):
        item = _make_item(outlet_name="  Ayam Katsu  ", menu_name="  Katsu Original  ")
        result = self.pipeline.process_item(item, None)
        assert result["outlet_name"] == "Ayam Katsu"
        assert result["menu_name"] == "Katsu Original"

    def test_promo_percentage_parsed(self):
        item = _make_item(promo_price="Rp20.000", promo_percentage="20%")
        result = self.pipeline.process_item(item, None)
        assert result["promo_percentage"] == "20%"

    def test_promo_percentage_none_when_no_match(self):
        item = _make_item(promo_percentage="no discount")
        result = self.pipeline.process_item(item, None)
        assert result["promo_percentage"] is None

    def test_no_promo_clears_fields(self):
        item = _make_item(promo_price=None, promo_nominal="Rp5.000", promo_percentage="10%")
        result = self.pipeline.process_item(item, None)
        assert result["promo_nominal"] is None
        assert result["promo_percentage"] is None

    def test_original_price_kept(self):
        item = _make_item(original_price="Rp25.000")
        result = self.pipeline.process_item(item, None)
        assert result["original_price"] == "Rp25.000"


class TestDuplicateFilterPipeline:
    def setup_method(self):
        self.pipeline = DuplicateFilterPipeline()

    def test_first_item_passes(self):
        item = _make_item(menu_name="Katsu")
        result = self.pipeline.process_item(item, None)
        assert result is item

    def test_duplicate_dropped(self):
        item1 = _make_item(menu_name="Katsu")
        item2 = _make_item(menu_name="Katsu")
        self.pipeline.process_item(item1, None)
        with pytest.raises(DropItem, match="Duplicate"):
            self.pipeline.process_item(item2, None)

    def test_different_items_pass(self):
        item1 = _make_item(menu_name="Katsu")
        item2 = _make_item(menu_name="Spicy Katsu")
        self.pipeline.process_item(item1, None)
        result = self.pipeline.process_item(item2, None)
        assert result is item2

    def test_different_categories_not_duplicate(self):
        item1 = _make_item(category_name="A", menu_name="Katsu")
        item2 = _make_item(category_name="B", menu_name="Katsu")
        self.pipeline.process_item(item1, None)
        result = self.pipeline.process_item(item2, None)
        assert result is item2
