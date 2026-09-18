# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/) as closely
as a CLI toolkit can. A **patch** release means fixes — it does not promise
that every flag and default is frozen, and where a default changes in one the
release notes say so at the top.

## [Unreleased]

## [0.1.0] — 2026-09-18

First release. Reads **andieswim.com** (Andie Swim) — collection listings,
keyword lookups, and single products with their full size/colour table.

### Added

- **Three local engines** (Playwright, Selenium, pyppeteer) plus
  `scraper_api_client.py` for the 2Captcha Scraping Browser API. All three
  local engines produce byte-identical output on the same collection
  (verified, modulo `scraped_at`) and agree on exit codes and run status.
- **Three modes.** `--mode listing` (default) reads a collection, one row per
  product; `--mode search` reads Shopify's predictive search; `--mode
  product` reads one product as **one row per variant**, with its own sku,
  size, colour, price and availability.
- **34-column output** in JSON and CSV, a `<out>.meta.json` sidecar per run,
  and the family's exit-code contract (`0` ok · `1` crash · `2` usage ·
  `3` blocked · `4` no products · `5` remote API error · `6` partial).
- **200 markets** via `--locale`, with the market recorded on every row.
- `diff_runs.py` for comparing two runs, which refuses to compare runs whose
  modes it cannot line up.

### Measured, and why the shape of this repo is what it is

- **Nothing on the read path is gated.** 2026-09-18, from a datacenter
  address: every route answered HTTP 200 with a browser User-Agent, with
  `curl/8.5.0`, with `python-urllib`, with a crawler UA, and with **no
  User-Agent header at all**. Twenty rapid requests: twenty 200s.
- **The rendered pages carry none of the data.** A collection page's HTML
  holds 5 `/products/` links in 793 KB — all from recommendation widgets —
  and `?page=2` returns the same five; the grid is painted after load by a
  React component. A product page publishes one JSON-LD block and its
  `@type` is `BreadcrumbList`. So the engines read the store's own JSON
  endpoints, which are ungated and richer than any tile.
- **The catalogue is reachable in full.** Walking `/products.json` at
  `limit=250`: 250 + 250 + 250 + 22 = **772 distinct handles**, page 5 empty.
  The store's own `sitemap_products_1.xml` lists 753 product URLs and every
  one of them is in those 772 — a strict superset with zero misses.
- **One collection, fully:** `one-pieces`, 180 rows, `complete`. `title`,
  `price`, `currency`, `image_url`, `handle` and `product_type` at 100%;
  `base_sku` at 91.7%; 81 of 180 reduced (20–75%); 63 products with every
  size available, 116 with some, 1 with none — a split that moves with stock
  (64 / 115 / 1 the same evening), so read it as "most products are partly
  available" rather than as a constant.

### The captcha on this site

Shopify's **storefront-forms hCaptcha**
(`ce_storefront_forms_captcha_hcaptcha.v1.5.3.iife.js`, sitekey
`f06e6c50-85a8-45c8-87d0-21a2b65856fe`) ships on every page the store serves
and is bound to **form submits** — newsletter, contact, account creation. No
listing, product page or JSON route renders one, so a scrape never meets it.
`recaptcha-v3-token` and `g-recaptcha-response` appear in the same bundle as
field names it checks for; no reCAPTCHA is loaded. Nothing else is present.

That is a statement about what the page carries, not about what can be
solved — 2Captcha solves hCaptcha with `HCaptchaTaskProxyless`. This repo
simply has no occasion to call it.

Both `hcaptcha` and `cf-turnstile` are therefore deliberately **absent** from
the bot-challenge marker set: each fires on pages the store plainly serves,
and a marker that matches every good page is worse than no marker.

### Traps handled, each with the measurement behind it

- **`products_count` is not a product count.** The collection index reports
  472 for a collection the storefront serves 180 of, and 3089 for one it
  serves 322 of, against 772 published products in the whole store. It is
  recorded as `catalog_count` with that warning and planned from by nothing.
- **A misspelt collection handle returns HTTP 200 and an empty list**; only
  the HTML route 404s. Every listing run checks the handle against the
  store's own index (830 collections) and reports `unknown_collection`
  rather than `empty`.
- **Prices are set per market, not converted.** One variant: 112.00 USD ·
  195.00 CAD · 110.00 GBP · 175.00 AUD · 130.00 EUR · 21600 JPY. A
  cross-market gap is pricing policy, not arbitrage.
- **An HTML page on this store is timing-dependent.** No HTTP redirect exists
  anywhere, but the theme's client-side geolocation app rewrites the location
  to the visitor's own market after load: `/collections/all` read at
  `domcontentloaded` says USD, and after a full load has become
  `/en-fi/collections/all` and says EUR. This made three engines disagree
  about the currency on one URL. Currency is now read from a JSON document
  instead, and all three agree.
- **Options are not positional.** `option1`/`option2` are Color and Size on
  622 of 665 products, and the store also ships `Rate`, `Length`,
  `Quantity`, `SPF`, `Pack Size`, `Strength` and `Product Size`. They are
  read by the product's own option NAME.
- **`/products/{h}.js` prices in integer cents** while every other route uses
  a decimal string; which one a payload is is detected from the payload, not
  the URL, because a `--dump-html` replay arrives without one.
- **A zero `compare_at_price` means absent, not free.** Predictive search
  writes `"0.00"` for a product that is not on sale.
- **`--sort` does not exist**, and that is a measurement: the JSON endpoint
  ignores `sort_by`. Nothing is capped either, so ordering decides
  `position` and nothing else.

### Not in the output, with the reason

- **`rating` / `review_count`** — the store uses Okendo, whose stars are
  `display:none` in the collection grid and absent from every JSON route
  read here. One third-party request per product would be needed: 180 for
  one collection.
- **`lowest_price_30d`** — the EU Omnibus disclosure a sibling repo needs is
  not published on this store, on any market, including the EU ones.

### Tests and CI

- 528 offline checks in `smoke_test.py`, with fixtures cut from real captures
  and each verified to parse to identical values to its untrimmed original.
  The verification caught two real trimming mistakes while being written.
- `tests.yml` — offline only, on Python 3.9 and 3.12, plus a Docker build,
  a per-engine venv matrix, and a committed-credential scan.
- `canary.yml` — a real 3-page run every morning, **with no credentials**,
  because the listing path needs none and a canary that can pass without one
  should never be gated on one. It runs at `--limit 50` so three pages
  really is three pages: at the default 250 most collections fit in one
  request and pagination would never be exercised.

[Unreleased]: https://github.com/2scraper/andieswim-scraper/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/2scraper/andieswim-scraper/releases/tag/v0.1.0
