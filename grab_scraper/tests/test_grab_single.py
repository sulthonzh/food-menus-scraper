import json
from unittest.mock import patch

from scrapy.http import TextResponse, Request
from grab_scraper.spiders.grab_single import (
    GrabSingleMerchantSpider,
    _extract_merchant_id,
    _format_price,
    _parse_cookie_string,
)


class TestExtractMerchantId:
    def test_full_url(self):
        url = "https://food.grab.com/id/id/restaurant/ayam-katsu-katsunami-lokarasa-citraland-delivery/6-C7EYGBJDME3JRN"
        assert _extract_merchant_id(url) == "6-C7EYGBJDME3JRN"

    def test_trailing_slash(self):
        url = "https://food.grab.com/id/id/restaurant/slug/6-BBBB/"
        assert _extract_merchant_id(url) == "6-BBBB"

    def test_plain_id(self):
        url = "https://food.grab.com/id/id/restaurant/6-CZDYNRMVVB5DAX"
        assert _extract_merchant_id(url) == "6-CZDYNRMVVB5DAX"

    def test_no_path_returns_none(self):
        result = _extract_merchant_id("https://example.com/")
        assert result is None or result == ""

    def test_last_segment_as_fallback(self):
        result = _extract_merchant_id("https://example.com/no-id-here")
        assert result == "no-id-here"


class TestFormatPrice:
    def test_normal(self):
        assert _format_price(3500000) == "Rp35.000"

    def test_zero(self):
        assert _format_price(0) == "Rp0"

    def test_none(self):
        assert _format_price(None) == "Rp0"

    def test_small_amount(self):
        assert _format_price(800000) == "Rp8.000"


class TestParseCookieString:
    def test_single(self):
        assert _parse_cookie_string("foo=bar") == {"foo": "bar"}

    def test_multiple(self):
        raw = "a=1; b=2; c=3"
        assert _parse_cookie_string(raw) == {"a": "1", "b": "2", "c": "3"}

    def test_empty(self):
        assert _parse_cookie_string("") == {}


SAMPLE_PAYLOAD = {
    "merchant": {
        "name": "Ayam Katsu Test",
        "menu": {
            "categories": [
                {
                    "name": "Katsu",
                    "items": [
                        {
                            "ID": "ITEM-1",
                            "name": "Katsu Original",
                            "available": True,
                            "description": "Chicken katsu with rice",
                            "priceInMinorUnit": 3500000,
                            "discountedPriceInMin": 2800000,
                        },
                    ],
                },
                {
                    "name": "Minuman",
                    "items": [
                        {
                            "ID": "ITEM-2",
                            "name": "Es Teh",
                            "available": False,
                            "description": "",
                            "priceInMinorUnit": 800000,
                            "discountedPriceInMin": 800000,
                        },
                    ],
                },
                {
                    "name": "Pesanan Terakhirmu",
                    "items": [{"ID": "SKIP", "name": "skip"}],
                },
            ]
        },
    }
}


class TestGrabSingleMerchantSpider:
    def test_default_url(self):
        spider = GrabSingleMerchantSpider()
        assert spider.merchant_id == "6-C7EYGBJDME3JRN"

    def test_custom_url(self):
        spider = GrabSingleMerchantSpider(url="https://food.grab.com/id/id/restaurant/x/6-TEST")
        assert spider.merchant_id == "6-TEST"

    def test_parse_menu_data_extracts_fields(self):
        spider = GrabSingleMerchantSpider()
        items = list(spider._parse_menu_data(SAMPLE_PAYLOAD))

        assert len(items) == 2

        first = items[0]
        assert first["outlet_name"] == "Ayam Katsu Test"
        assert first["category_name"] == "Katsu"
        assert first["menu_name"] == "Katsu Original"
        assert first["menu_description"] == "Chicken katsu with rice"
        assert first["original_price"] == "Rp35.000"
        assert first["promo_price"] == "Rp28.000"
        assert first["promo_nominal"] == "Rp7.000"
        assert first["promo_percentage"] == "20%"
        assert first["availability"] == "Available"

        second = items[1]
        assert second["menu_name"] == "Es Teh"
        assert second["promo_price"] == ""
        assert second["availability"] == "Sold Out"

    def test_parse_merchant_callback_ok(self):
        spider = GrabSingleMerchantSpider()
        body = json.dumps(SAMPLE_PAYLOAD).encode()
        req = Request(url="https://portal.grab.com/foodweb/guest/v2/merchants/6-C7EYGBJDME3JRN")
        resp = TextResponse(url=req.url, body=body, encoding="utf-8", request=req)
        resp.meta["merchant_id"] = "6-C7EYGBJDME3JRN"

        items = list(spider.parse_merchant(resp))
        assert len(items) == 2
        assert items[0]["menu_name"] == "Katsu Original"

    def test_parse_merchant_non_200_returns_empty(self):
        spider = GrabSingleMerchantSpider()
        body = json.dumps(SAMPLE_PAYLOAD).encode()
        req = Request(url="https://portal.grab.com/foodweb/guest/v2/merchants/6-C7EYGBJDME3JRN")
        resp = TextResponse(url=req.url, body=body, encoding="utf-8", request=req, status=403)
        resp.meta["merchant_id"] = "6-C7EYGBJDME3JRN"

        items = list(spider.parse_merchant(resp))
        assert items == []

    def test_parse_merchant_no_merchant_key(self):
        spider = GrabSingleMerchantSpider()
        body = json.dumps({"error": "not found"}).encode()
        req = Request(url="https://portal.grab.com/foodweb/guest/v2/merchants/6-C7EYGBJDME3JRN")
        resp = TextResponse(url=req.url, body=body, encoding="utf-8", request=req)
        resp.meta["merchant_id"] = "6-C7EYGBJDME3JRN"

        items = list(spider.parse_merchant(resp))
        assert items == []

    def test_empty_menu(self):
        spider = GrabSingleMerchantSpider()
        items = list(spider._parse_menu_data(
            {"merchant": {"name": "Empty", "menu": {"categories": []}}}
        ))
        assert items == []

    def test_bad_json(self):
        spider = GrabSingleMerchantSpider()
        req = Request(url="https://portal.grab.com/foodweb/guest/v2/merchants/6-C7EYGBJDME3JRN")
        resp = TextResponse(url=req.url, body=b"not json", encoding="utf-8", request=req)
        resp.meta["merchant_id"] = "6-C7EYGBJDME3JRN"
        assert list(spider.parse_merchant(resp)) == []

    def test_dedup_by_item_id(self):
        spider = GrabSingleMerchantSpider()
        payload = {
            "merchant": {
                "name": "Dup",
                "menu": {
                    "categories": [
                        {
                            "name": "A",
                            "items": [
                                {"ID": "X1", "name": "Nasi", "priceInMinorUnit": 200000},
                                {"ID": "X1", "name": "Nasi", "priceInMinorUnit": 200000},
                            ],
                        },
                    ]
                },
            }
        }
        items = list(spider._parse_menu_data(payload))
        assert len(items) == 1

    def test_skips_personalized_categories(self):
        spider = GrabSingleMerchantSpider()
        payload = {
            "merchant": {
                "name": "Test",
                "menu": {
                    "categories": [
                        {"name": "Untukmu", "items": [{"ID": "U1", "name": "skip-me"}]},
                        {"name": "Real Food", "items": [{"ID": "R1", "name": "Nasi Goreng", "priceInMinorUnit": 250000}]},
                    ]
                },
            }
        }
        items = list(spider._parse_menu_data(payload))
        assert len(items) == 1
        assert items[0]["category_name"] == "Real Food"

    def test_build_api_headers_includes_grab_version(self):
        spider = GrabSingleMerchantSpider()
        headers = spider._build_api_headers()
        assert "x-grab-web-app-version" in headers
        assert headers["accept"] == "application/json, text/plain, */*"
        assert headers["x-country-code"] == "ID"

    @patch("grab_scraper.spiders.grab_single.ENV_GFC_SESSION", "sess-token")
    def test_build_api_headers_with_env_session(self):
        spider = GrabSingleMerchantSpider()
        headers = spider._build_api_headers()
        assert headers["x-gfc-session"] == "sess-token"

    @patch("grab_scraper.spiders.grab_single.ENV_HYDRA_JWT", "jwt-token")
    def test_build_api_headers_with_hydra_jwt(self):
        spider = GrabSingleMerchantSpider()
        headers = spider._build_api_headers()
        assert headers["x-hydra-jwt"] == "jwt-token"

    def test_invalid_url_raises(self):
        try:
            GrabSingleMerchantSpider(url="https://example.com/")
        except ValueError:
            pass
        else:
            last = _extract_merchant_id("https://example.com/")
            if last is None or last == "":
                assert False, "should raise ValueError for no merchant id"
