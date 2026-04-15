import json
import os
import scrapy
from urllib.parse import urlencode
from grab_scraper.items import GrabMenuItem


COOKIES_RAW = os.environ.get("GRAB_COOKIES", "")
X_GFC_SESSION = os.environ.get("GRAB_X_GFC_SESSION", "")
X_HYDRA_JWT = os.environ.get("GRAB_X_HYDRA_JWT", "")
X_APP_VERSION = os.environ.get("GRAB_X_APP_VERSION", "rnU80FF3gt8ojhFqnw9X4")

CITY_LOCATIONS = [
    ("Central Jakarta", "-6.1825,106.8347"),
    ("South Jakarta", "-6.2615,106.8106"),
    ("North Jakarta", "-6.1544,106.9061"),
    ("West Jakarta", "-6.1674,106.7914"),
    ("East Jakarta", "-6.2250,106.8970"),
    ("Bekasi", "-6.2349,106.9896"),
    ("Tangerang", "-6.1783,106.6319"),
    ("Depok", "-6.4025,106.7942"),
    ("Bogor", "-6.5971,106.8060"),
    ("Malang", "-7.9412,112.6515"),
    ("Surabaya", "-7.2575,112.7521"),
    ("Bandung", "-6.9175,107.6191"),
    ("Semarang", "-6.9666,110.4196"),
    ("Medan", "3.5952,98.6722"),
    ("Makassar", "-5.1477,119.4327"),
    ("Yogyakarta", "-7.7956,110.3695"),
    ("Denpasar", "-8.6705,115.2126"),
    ("Palembang", "-2.9761,104.7754"),
]

PORTAL_BASE = "https://portal.grab.com/foodweb/guest/v2"
MERCHANT_API_BASE = "https://food.grab.com/proxy/foodweb/v2/order/merchants"
PAGE_SIZE = 32
MAX_OFFSET = 500


class GrabDirectApiSpider(scrapy.Spider):
    name = "grab_direct_api"
    custom_settings = {
        "CONCURRENT_REQUESTS": 2,
        "DOWNLOAD_DELAY": 2,
        "ROBOTSTXT_OBEY": False,
        "DOWNLOAD_TIMEOUT": 30,
        "FEEDS": {
            "output/%(name)s_%(time)s.csv": {
                "format": "csv",
                "fields": [
                    "outlet_name", "category_name", "menu_name", "menu_description",
                    "original_price", "promo_price", "promo_nominal",
                    "promo_percentage", "availability", "menu_url",
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
                ],
            }
        },
    }

    def __init__(self, merchant_ids=None, locations=None, latlng=None,
                 ids_file=None, max_merchants=0, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.latlng = latlng
        self.max_merchants = max_merchants
        self.seen_merchant_ids = set()

        if ids_file:
            with open(ids_file) as f:
                self.merchant_ids = [line.strip() for line in f if line.strip()]
        elif merchant_ids:
            self.merchant_ids = [m.strip() for m in merchant_ids.split(",") if m.strip()]
        else:
            self.merchant_ids = []

        if locations:
            loc_names = [l.strip() for l in locations.split(",")]
            self.locations = [(n, c) for n, c in CITY_LOCATIONS if n in loc_names]
        else:
            self.locations = CITY_LOCATIONS

    def _build_headers(self, for_portal=False):
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "id",
            "x-country-code": "ID",
            "x-gfc-country": "ID",
            "user-agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0"
            ),
            "sec-ch-ua": '"Microsoft Edge";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "referer": "https://food.grab.com/id/id/",
        }
        if for_portal:
            headers["origin"] = "https://food.grab.com"
            headers["sec-fetch-site"] = "same-site"
        if X_GFC_SESSION:
            headers["x-gfc-session"] = X_GFC_SESSION
        if X_HYDRA_JWT:
            headers["x-hydra-jwt"] = X_HYDRA_JWT
        if X_APP_VERSION:
            headers["x-grab-web-app-version"] = X_APP_VERSION
        return headers

    def _build_cookies(self):
        if not COOKIES_RAW:
            return {}
        cookies = {}
        for pair in COOKIES_RAW.split(";"):
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                cookies[k.strip()] = v.strip()
        return cookies

    async def start(self):
        cookies = self._build_cookies()

        if not cookies:
            self.logger.error("No cookies provided! Set GRAB_COOKIES env var.")
            return

        if self.merchant_ids:
            headers = self._build_headers()
            for mid in self.merchant_ids[:self.max_merchants or len(self.merchant_ids)]:
                latlng = self.latlng or "-6.1825,106.8347"
                url = f"{MERCHANT_API_BASE}/{mid}?latlng={latlng}"
                self.seen_merchant_ids.add(mid)
                yield scrapy.Request(
                    url, headers=headers, cookies=cookies,
                    callback=self.parse_merchant,
                    meta={"merchant_id": mid, "latitude": "", "longitude": ""},
                    dont_filter=True,
                )
        else:
            for name, latlng in self.locations:
                lat, lng = latlng.split(",")

                # Discovery method 1: Recommended merchants (GET)
                rec_params = urlencode({
                    "latitude": lat.strip(),
                    "longitude": lng.strip(),
                    "mode": "",
                    "offset": 0,
                    "countryCode": "ID",
                })
                rec_url = f"{PORTAL_BASE}/recommended/merchants?{rec_params}"
                yield scrapy.Request(
                    rec_url,
                    headers=self._build_headers(for_portal=True),
                    cookies=cookies,
                    callback=self.parse_recommended,
                    meta={"location_name": name, "latlng": latlng},
                    dont_filter=True,
                )

                # Discovery method 2: Search merchants (POST)
                search_body = json.dumps({
                    "latlng": f"{lat.strip()},{lng.strip()}",
                    "keyword": "",
                    "offset": 0,
                    "pageSize": PAGE_SIZE,
                    "countryCode": "ID",
                })
                search_headers = self._build_headers(for_portal=True)
                search_headers["content-type"] = "application/json;charset=UTF-8"
                yield scrapy.Request(
                    f"{PORTAL_BASE}/search",
                    method="POST",
                    body=search_body,
                    headers=search_headers,
                    cookies=cookies,
                    callback=self.parse_search,
                    meta={"location_name": name, "latlng": latlng, "search_offset": 0},
                    dont_filter=True,
                )

    def _extract_merchant_meta(self, m, source="recommended"):
        meta = {"merchant_id": m.get("id", "")}
        latlng = m.get("latlng") or {}
        meta["latitude"] = latlng.get("latitude", "")
        meta["longitude"] = latlng.get("longitude", "")

        distance = m.get("distanceInKm")
        if distance is None:
            distance = (m.get("merchantBrief") or {}).get("distanceInKm")
        meta["distance_km"] = distance

        if source == "recommended":
            md = m.get("merchantData") or {}
            meta["cuisine"] = md.get("cuisine", "")
            meta["rating"] = md.get("rating")
            meta["vote_count"] = md.get("vote_count")
            meta["estimated_delivery_time"] = md.get("estimated_delivery_time")
            meta["price_tag"] = md.get("priceTag")
            meta["merchant_photo"] = md.get("photo_href") or md.get("photo_small_href", "")
            hours = md.get("service_hours") or {}
            meta["is_open"] = hours.get("open")
            meta["delivery_options"] = ""
            meta["chain_name"] = ""
            meta["branch_name"] = ""
            meta["delivery_fee"] = ""
            meta["business_type"] = ""
        else:
            mb = m.get("merchantBrief") or {}
            cuisines = mb.get("cuisine") or []
            meta["cuisine"] = ", ".join(cuisines) if isinstance(cuisines, list) else str(cuisines)
            meta["rating"] = mb.get("rating")
            meta["vote_count"] = mb.get("vote_count")
            meta["estimated_delivery_time"] = m.get("estimatedDeliveryTime")
            meta["price_tag"] = mb.get("priceTag")
            meta["merchant_photo"] = mb.get("photoHref") or mb.get("smallPhotoHref", "")
            hours = mb.get("openHours") or {}
            meta["is_open"] = hours.get("open")
            meta["delivery_options"] = mb.get("deliverOptions", "")
            meta["chain_name"] = m.get("chainName", "")
            meta["branch_name"] = m.get("branchName", "")
            fee = m.get("estimatedDeliveryFee") or {}
            meta["delivery_fee"] = fee.get("priceDisplay", "")
            meta["business_type"] = m.get("businessType", "")

        return meta

    def _enqueue_merchant(self, mid, latlng, headers, cookies, merchant_meta=None):
        if mid in self.seen_merchant_ids:
            return None
        self.seen_merchant_ids.add(mid)
        url = f"{MERCHANT_API_BASE}/{mid}?latlng={latlng}"
        request_meta = {"merchant_id": mid}
        if merchant_meta:
            request_meta.update(merchant_meta)
        return scrapy.Request(
            url, headers=headers, cookies=cookies,
            callback=self.parse_merchant,
            meta=request_meta,
            dont_filter=True,
        )

    def parse_recommended(self, response):
        meta = response.meta
        location_name = meta["location_name"]
        latlng = meta["latlng"]

        try:
            data = json.loads(response.text)
        except json.JSONDecodeError:
            self.logger.warning(
                "Recommended: failed to parse for %s (status %s)",
                location_name, response.status,
            )
            return

        headers = self._build_headers()
        cookies = self._build_cookies()
        count = 0

        groups = data.get("recommendedMerchantGroups", [])
        for group in groups:
            for m in group.get("recommendedMerchants", []):
                mid = m.get("id", "")
                if not mid:
                    continue
                merchant_meta = self._extract_merchant_meta(m, source="recommended")
                req = self._enqueue_merchant(mid, latlng, headers, cookies, merchant_meta=merchant_meta)
                if req:
                    count += 1
                    yield req

        self.logger.info(
            "Recommended %s: %d new merchants (total seen: %d)",
            location_name, count, len(self.seen_merchant_ids),
        )

    def parse_search(self, response):
        meta = response.meta
        location_name = meta["location_name"]
        latlng = meta["latlng"]
        current_offset = meta.get("search_offset", 0)

        try:
            data = json.loads(response.text)
        except json.JSONDecodeError:
            self.logger.warning(
                "Search: failed to parse for %s (status %s)",
                location_name, response.status,
            )
            return

        search_result = data.get("searchResult", {})
        merchants = search_result.get("searchMerchants", [])
        total_count = search_result.get("totalCount", 0)
        has_more = search_result.get("hasMore", False)

        headers = self._build_headers()
        cookies = self._build_cookies()
        count = 0

        for m in merchants:
            mid = m.get("id", "")
            if not mid:
                continue
            merchant_meta = self._extract_merchant_meta(m, source="search")
            req = self._enqueue_merchant(mid, latlng, headers, cookies, merchant_meta=merchant_meta)
            if req:
                count += 1
                yield req

        self.logger.info(
            "Search %s (offset %d): %d new merchants, total API=%d, hasMore=%s (total seen: %d)",
            location_name, current_offset, count, total_count, has_more,
            len(self.seen_merchant_ids),
        )

        next_offset = current_offset + len(merchants)
        if has_more and next_offset < MAX_OFFSET and next_offset < total_count:
            lat, lng = latlng.split(",")
            search_body = json.dumps({
                "latlng": f"{lat.strip()},{lng.strip()}",
                "keyword": "",
                "offset": next_offset,
                "pageSize": PAGE_SIZE,
                "countryCode": "ID",
            })
            search_headers = self._build_headers(for_portal=True)
            search_headers["content-type"] = "application/json;charset=UTF-8"
            yield scrapy.Request(
                f"{PORTAL_BASE}/search",
                method="POST",
                body=search_body,
                headers=search_headers,
                cookies=cookies,
                callback=self.parse_search,
                meta={
                    "location_name": location_name,
                    "latlng": latlng,
                    "search_offset": next_offset,
                },
                dont_filter=True,
            )

    def parse_merchant(self, response):
        mid = response.meta["merchant_id"]

        try:
            data = json.loads(response.text)
        except json.JSONDecodeError:
            self.logger.warning("Failed to parse merchant %s: %s", mid, response.status)
            return

        merchant = data.get("merchant") or {}
        merchant_name = merchant.get("name", "Unknown")
        menu = merchant.get("menu") or {}
        categories = menu.get("categories") or []

        merchant_latlng = merchant.get("latlng") or {}
        merchant_cuisine = merchant.get("cuisine", "")
        merchant_rating = merchant.get("rating")
        merchant_vote_count = merchant.get("voteCount")
        merchant_chain = merchant.get("chainName", "")
        merchant_branch = merchant.get("branchName", "")
        merchant_distance = merchant.get("distanceInKm")
        merchant_eta = merchant.get("ETA")
        merchant_photo = merchant.get("photoHref", "")
        merchant_integrated = merchant.get("isIntegrated", False)
        merchant_status = merchant.get("status", "")
        merchant_business = merchant.get("businessType", "")
        delivery_opts = merchant.get("deliveryOptions") or []
        hours = merchant.get("openingHours") or {}
        merchant_open = hours.get("open")
        est_fee = merchant.get("estimatedDeliveryFee") or {}
        merchant_fee = est_fee.get("priceDisplay", "")
        sof = merchant.get("sofConfiguration") or {}
        sof_fee_display = (sof.get("fixFeeForDisplay") or {}).get("amountDisplay", "")

        if not categories:
            self.logger.info("No menu categories for %s (%s)", merchant_name, mid)
            return

        seen_item_ids = set()
        total = 0

        for cat in categories:
            cat_name = cat.get("name", "Uncategorized")
            if cat_name in ("Pesanan Terakhirmu", "Untukmu"):
                continue

            for item in cat.get("items", []):
                item_id = item.get("ID", "")
                if item_id in seen_item_ids:
                    continue
                seen_item_ids.add(item_id)

                price_minor = item.get("priceInMinorUnit", 0)
                discounted_minor = item.get("discountedPriceInMin", price_minor)
                takeaway_minor = item.get("takeawayPriceInMin", 0)
                disc_takeaway_minor = item.get("discountedTakeawayPriceInMin", takeaway_minor)

                original_price = self._format_price(price_minor)
                promo_price = (
                    self._format_price(discounted_minor)
                    if discounted_minor != price_minor else None
                )

                promo_nominal = None
                promo_percentage = None
                if promo_price and price_minor > discounted_minor:
                    diff = price_minor - discounted_minor
                    promo_nominal = self._format_price(diff)
                    pct = round((diff / price_minor) * 100)
                    promo_percentage = f"{pct}%"

                availability = "Available" if item.get("available", True) else "Sold Out"
                description = item.get("description", "") or ""

                img_url = item.get("imgHref", "")
                if not img_url:
                    images = item.get("images") or []
                    img_url = images[0] if images else ""

                dietary = item.get("dietary") or []
                dietary_str = ", ".join(dietary) if dietary else ""

                top_seller = bool(item.get("topSeller"))

                takeaway_price = self._format_price(takeaway_minor) if takeaway_minor else None
                promo_takeaway = (
                    self._format_price(disc_takeaway_minor)
                    if disc_takeaway_minor and disc_takeaway_minor != takeaway_minor else None
                )

                total += 1
                yield GrabMenuItem(
                    outlet_name=merchant_name,
                    category_name=cat_name,
                    menu_name=item.get("name", ""),
                    menu_description=description,
                    original_price=original_price,
                    promo_price=promo_price,
                    promo_nominal=promo_nominal,
                    promo_percentage=promo_percentage,
                    availability=availability,
                    menu_url=(
                        f"https://food.grab.com/id/id/restaurant/"
                        f"{self._slugify(merchant_name)}/{mid}"
                    ),
                    merchant_id=mid,
                    item_id=item_id,
                    image_url=img_url,
                    dietary_tags=dietary_str,
                    is_top_seller=top_seller,
                    takeaway_price=takeaway_price,
                    promo_takeaway_price=promo_takeaway,
                    cuisine=response.meta.get("cuisine", ""),
                    rating=response.meta.get("rating"),
                    vote_count=response.meta.get("vote_count"),
                    distance_km=response.meta.get("distance_km") or merchant_distance,
                    estimated_delivery_time=response.meta.get("estimated_delivery_time"),
                    latitude=merchant_latlng.get("latitude", response.meta.get("latitude", "")),
                    longitude=merchant_latlng.get("longitude", response.meta.get("longitude", "")),
                    chain_name=response.meta.get("chain_name", "") or merchant_chain,
                    branch_name=response.meta.get("branch_name", "") or merchant_branch,
                    price_tag=response.meta.get("price_tag"),
                    is_open=response.meta.get("is_open") if response.meta.get("is_open") is not None else merchant_open,
                    delivery_fee=response.meta.get("delivery_fee", "") or merchant_fee,
                    merchant_photo=response.meta.get("merchant_photo", "") or merchant_photo,
                    delivery_options=", ".join(delivery_opts) if delivery_opts else response.meta.get("delivery_options", ""),
                    business_type=response.meta.get("business_type", "") or merchant_business,
                    service_fee=sof_fee_display,
                    merchant_cuisine=merchant_cuisine,
                    merchant_rating=merchant_rating,
                    merchant_vote_count=merchant_vote_count,
                    eta_minutes=merchant_eta,
                    is_integrated=merchant_integrated,
                    merchant_status=merchant_status,
                )

        self.logger.info("Extracted %d items from %s (%s)", total, merchant_name, mid)

    @staticmethod
    def _format_price(minor_units):
        if not minor_units:
            return "Rp0"
        major = minor_units / 100
        return f"Rp{major:,.0f}".replace(",", ".")

    @staticmethod
    def _slugify(name):
        return (
            name.lower()
            .replace(" ", "-")
            .replace("&", "dan")
            .replace("(", "")
            .replace(")", "")
            .replace(",", "")
            .replace("'", "")
            .replace(".", "")
        )
