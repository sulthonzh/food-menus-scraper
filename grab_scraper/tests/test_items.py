"""Tests for GrabMenuItem and item processors."""

from grab_scraper.items import GrabMenuItem, clean_price, clean_text, normalize_availability


class TestCleanText:
    def test_strips_whitespace(self):
        assert clean_text("  hello  ") == "hello"

    def test_none_returns_none(self):
        assert clean_text(None) is None

    def test_empty_returns_none(self):
        assert clean_text("") is None

    def test_normal_text(self):
        assert clean_text("Ayam Katsu") == "Ayam Katsu"


class TestCleanPrice:
    def test_strips_price(self):
        assert clean_price(" Rp25.000 ") == "Rp25.000"

    def test_none_returns_none(self):
        assert clean_price(None) is None

    def test_plain_number(self):
        assert clean_price("25000") == "25000"


class TestNormalizeAvailability:
    def test_available_default(self):
        assert normalize_availability(None) == "Available"
        assert normalize_availability("") == "Available"

    def test_sold_out(self):
        assert normalize_availability("Sold Out") == "Sold Out"
        assert normalize_availability("sold out") == "Sold Out"

    def test_unavailable(self):
        assert normalize_availability("Unavailable") == "Sold Out"
        assert normalize_availability("unavailable") == "Sold Out"

    def test_habis(self):
        assert normalize_availability("Habis") == "Sold Out"

    def test_available_text(self):
        assert normalize_availability("Available") == "Available"
        assert normalize_availability("Tersedia") == "Available"


class TestGrabMenuItem:
    def test_create_item(self):
        item = GrabMenuItem()
        item["outlet_name"] = "Ayam Katsu Katsunami"
        item["category_name"] = "Ayam Katsu"
        item["menu_name"] = "Katsu Original"
        item["menu_description"] = "Chicken katsu with rice"
        item["original_price"] = "Rp25.000"
        item["promo_price"] = "Rp20.000"
        item["promo_nominal"] = None
        item["promo_percentage"] = None
        item["availability"] = "Available"

        assert item["outlet_name"] == "Ayam Katsu Katsunami"
        assert item["menu_name"] == "Katsu Original"
        assert item["availability"] == "Available"

    def test_item_fields(self):
        expected_fields = {
            "outlet_name", "category_name", "menu_name", "menu_description",
            "original_price", "promo_price", "promo_nominal", "promo_percentage",
            "availability", "menu_url",
            "merchant_id", "item_id", "image_url", "dietary_tags",
            "is_top_seller", "takeaway_price", "promo_takeaway_price",
            "cuisine", "rating", "vote_count",
            "distance_km", "estimated_delivery_time", "latitude",
            "longitude", "chain_name", "branch_name", "price_tag",
            "is_open", "delivery_fee", "merchant_photo",
            "delivery_options", "business_type",
            "service_fee", "merchant_cuisine", "merchant_rating",
            "merchant_vote_count", "eta_minutes", "is_integrated",
            "merchant_status",
        }
        assert set(GrabMenuItem.fields.keys()) == expected_fields
