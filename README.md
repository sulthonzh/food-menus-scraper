# Grab Food Menu Scraper

Scrapy spider to scrape menu data from a Grab Food restaurant page.

Target page: https://food.grab.com/id/id/restaurant/ayam-katsu-katsunami-lokarasa-citraland-delivery/6-C7EYGBJDME3JRN

## Approach

Grab's restaurant pages are Next.js apps that fetch menu data from an internal API on page load. The spider uses a two-step approach:

1. **Playwright (headless Chromium)** loads the restaurant page. During JS hydration, Grab's frontend calls `portal.grab.com/foodweb/guest/v2/merchants/{id}` — a guest-accessible endpoint that returns the full menu as JSON (categories, items, prices, promos, availability).

2. The spider **intercepts that API response** from the browser context, parses the JSON, and yields structured items. No manual cookie copying needed.

The merchant ID (`6-C7EYGBJDME3JRN`) is extracted from the Grab URL automatically.

**Fallback mode**: if `GRAB_COOKIES` env var is set, the spider skips the browser and hits the proxy API directly with those credentials. Useful for CI or when running headless without Playwright.

## Tools

- **Scrapy** — web scraping framework
- **Playwright** — headless browser for cookie/session bootstrapping
- **Python 3.10+**
- **uv** — package manager

## Challenges

1. **Guest API discovery** — Grab's authenticated proxy API (`/proxy/foodweb/v2/order/merchants/`) requires session tokens that expire quickly. Found that the guest API at `portal.grab.com/foodweb/guest/v2/merchants/` works without auth, but only from a browser context (WAF cookies required).
2. **Location cookie** — Grab's SSR renders the landing page instead of the restaurant page unless a `location` cookie is set. The spider injects this cookie before navigation.
3. **Prices in minor units** — API returns prices in cents (e.g. `3500000` = Rp35.000). The spider handles this conversion.
4. **Skip sections** — Grab includes personalized sections like "Pesanan Terakhirmu" (your last order) that aren't real menu categories. These are filtered out.
5. **Duplicate items** — some items appear in multiple categories. Deduplicated by item ID.

## Setup

```bash
uv sync
uv run playwright install chromium
```

## Run

```bash
uv run scrapy crawl grab_single
```

Output: `output/grab_single_<timestamp>.csv` with these 9 columns:

| Column | Description |
|--------|-------------|
| outlet_name | Restaurant name |
| category_name | Menu category |
| menu_name | Item name |
| menu_description | Item description |
| original_price | Price before promo (Rp) |
| promo_price | Price after promo (Rp) |
| promo_nominal | Discount amount (Rp) |
| promo_percentage | Discount percentage |
| availability | "Available" or "Sold Out" |

To scrape a different restaurant:

```bash
uv run scrapy crawl grab_single \
  -a url="https://food.grab.com/id/id/restaurant/some-place/6-XXXXXXXXX"
```

## Test

```bash
uv run pytest grab_scraper/tests/ -v
```

## Mobile App Scraping (ShopeeFood etc)

If data is only available inside a mobile app and there's no web version or public API, the approach would be:

1. **Traffic interception** — set up a proxy (mitmproxy / Charles Proxy) on the phone, use the app normally, and capture the API calls. Most apps talk to a backend API, and you can reverse-engineer the endpoints, headers, and auth tokens from the captured traffic.

2. **SSL pinning bypass** — if the app pins certificates (rejects proxy), use Frida or Objection to bypass it. This lets the proxy decrypt HTTPS traffic.

3. **Replay the API** — once you have the endpoints and auth mechanism, write a script to call them directly. Same approach as this Grab scraper — hit the API, parse JSON, no UI rendering needed.

4. **If no API is accessible** (e.g. fully offline/local data): use app automation tools like Appium to drive the app UI, take screenshots, and use OCR to extract data. This is slow and fragile though, so only as a last resort.

5. **Rate limiting & ethics** — mobile APIs often have stricter rate limits. Add delays, respect throttling, and don't hammer the endpoint. Also check if the data is available through an official partner API first.

## Files

```
grab_scraper/
├── items.py            # data model for menu items
├── middlewares.py       # retry, UA rotation
├── pipelines.py         # validation, cleaning, dedup
├── settings.py          # scrapy config
├── spiders/
│   ├── grab_single.py       # single merchant spider (this task)
│   ├── grab_direct_api.py   # multi-city scraper
│   └── grab_food.py         # old playwright approach (not used)
└── tests/
```
