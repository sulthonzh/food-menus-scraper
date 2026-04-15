"""Tests for Grab Food spider helpers."""

from scrapy.http import HtmlResponse, Request

from grab_scraper.spiders.grab_food import GrabFoodSpider


def make_response(url, body):
    request = Request(url=url)
    return HtmlResponse(url=url, body=body, encoding="utf-8", request=request)


class TestGrabFoodSpider:
    def setup_method(self):
        self.spider = GrabFoodSpider()

    def test_extract_listing_latlng_from_next_data(self):
        next_data = {
            "props": {
                "pageProps": {
                    "payload": {
                        "latlng": "-6.1767352,106.826504",
                    }
                }
            }
        }

        assert self.spider._extract_listing_latlng(next_data) == "-6.1767352,106.826504"

    def test_extract_restaurants_from_payloads(self):
        payloads = [
            {
                "data": {
                    "searchResult": {
                        "merchants": [
                            {
                                "id": "6-C7EYGBJDME3JRN",
                                "name": "Ayam Katsu Katsunami",
                                "latlng": "-6.17,106.82",
                                "merchantSlug": "ayam-katsu-katsunami-lokarasa-citraland-delivery",
                            },
                            {
                                "id": "6-C7EYGBJDME3JRN",
                                "name": "Duplicate",
                                "merchantSlug": "duplicate",
                            },
                        ]
                    }
                }
            }
        ]

        restaurants = self.spider._extract_restaurants_from_payloads(
            payloads,
            "https://food.grab.com/id/id/restaurants",
            "-6.1767352,106.826504",
        )

        assert restaurants == [
            {
                "id": "6-C7EYGBJDME3JRN",
                "slug": "ayam-katsu-katsunami-lokarasa-citraland-delivery",
                "name": "Ayam Katsu Katsunami",
                "latlng": "-6.17,106.82",
                "url": "https://food.grab.com/id/id/restaurant/ayam-katsu-katsunami-lokarasa-citraland-delivery/6-C7EYGBJDME3JRN",
            }
        ]

    def test_extract_restaurants_from_dom(self):
        response = make_response(
            "https://food.grab.com/id/id/restaurants",
            """
            <html>
                <body>
                    <a href="/id/id/restaurant/outlet-a/6-AAAA">Outlet A</a>
                    <a href="/id/id/restaurant/outlet-b/6-BBBB">Outlet B</a>
                </body>
            </html>
            """,
        )

        restaurants = self.spider._extract_restaurants_from_dom(response, "-6.1,106.8")

        assert [restaurant["id"] for restaurant in restaurants] == ["6-AAAA", "6-BBBB"]
        assert restaurants[0]["url"] == "https://food.grab.com/id/id/restaurant/outlet-a/6-AAAA"

    def test_parse_merchant_payload_builds_google_sheet_ready_item(self):
        payload = {
            "merchant": {
                "ID": "6-C7EYGBJDME3JRN",
                "name": "Ayam Katsu Katsunami",
                "menu": {
                    "categories": [
                        {
                            "name": "Katsu",
                            "available": True,
                            "items": [
                                {
                                    "ID": "ITEM-1",
                                    "name": "Katsu Original",
                                    "available": True,
                                    "description": "Chicken katsu with rice",
                                    "priceV2": {
                                        "amountInMinor": 5400000,
                                        "amountDisplay": "54.000",
                                    },
                                    "discountedPriceV2": {
                                        "amountInMinor": 3240000,
                                        "amountDisplay": "32.400",
                                    },
                                    "discountPercentage": "-40%",
                                }
                            ],
                        }
                    ]
                },
            }
        }

        items = self.spider._parse_merchant_payload(
            payload,
            "https://food.grab.com/id/id/restaurant/outlet-a/6-C7EYGBJDME3JRN",
        )

        assert items == [
            {
                "outlet_name": "Ayam Katsu Katsunami",
                "category_name": "Katsu",
                "menu_name": "Katsu Original",
                "menu_description": "Chicken katsu with rice",
                "original_price": "Rp54.000",
                "promo_price": "Rp32.400",
                "promo_nominal": "Rp21.600",
                "promo_percentage": "-40%",
                "availability": "Available",
                "menu_url": "https://food.grab.com/id/id/restaurant/outlet-a/6-C7EYGBJDME3JRN",
            }
        ]

    def test_build_menu_item_without_discount_omits_promo_fields(self):
        item = self.spider._build_menu_item(
            {
                "name": "Katsu Original",
                "description": "Chicken katsu with rice",
                "available": False,
                "priceV2": {
                    "amountDisplay": "54.000",
                },
                "discountedPriceV2": {
                    "amountDisplay": "54.000",
                },
            },
            "Ayam Katsu Katsunami",
            "Katsu",
            "https://food.grab.com/id/id/restaurant/outlet-a/6-C7EYGBJDME3JRN",
        )

        assert item is not None
        assert item["promo_price"] is None
        assert item["promo_nominal"] is None
        assert item["promo_percentage"] is None
        assert item["availability"] == "Sold Out"
