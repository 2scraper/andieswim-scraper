#!/usr/bin/env python3
"""
smoke_test.py — the offline suite for andieswim-scraper.

One file of plain functions with inline fixtures. No pytest, no conftest, no
fixtures directory (CLAUDE.md §10); `tests/test_smoke.py` wraps this as a
single pytest test so `pytest` works as an entry point without a second copy
of the checks.

    python3 smoke_test.py            run everything
    python3 smoke_test.py -v         print every check as it passes

It must pass with NO engine library installed at all: every
`import playwright_scraper` / `selenium_scraper` / `puppeteer_scraper` is
guarded and the skip is RECORDED, because "skipped, engine absent" reads
identically to a real import error. CI installs each engine in its own venv
and fails if that engine's group reports a skip.

The fixtures
------------
Every one is cut from a real capture taken 2026-09-18 and trimmed to the
keys the parser reads. Each was verified to parse to IDENTICAL values to its
untrimmed original before being committed (§15 step 3) — the trimming script
asserts field-by-field equality on every row, not merely that the row count
matched. It caught two real trimming mistakes while being written: dropping
a product's later tags changed the `tags` column, and omitting
`published_at` from the product fixture nulled a column that is populated on
every real row. A fixture that "looks right" is not a fixture that parses
right.

    LISTING_US      /collections/one-pieces, 4 of its 180 products, chosen
                    so every state of the two columns that matter is present
                    exactly once: full price / reduced, all sizes available /
                    some / none.
    LISTING_GB      the SAME four products from /en-gb/, which is what makes
                    the cross-market checks a comparison rather than an
                    assertion about one number.
    LISTING_ODD     two accessories: one whose options are neither Color nor
                    Size in the usual positions, and one whose variants
                    genuinely disagree on price. Both are the shapes that
                    break a parser written against swimwear alone.
    PRODUCT_JS      /products/{handle}.js for a product with a sold-out size.
                    Prices in INTEGER CENTS, which is the unit trap, and
                    carries per-variant `available`, which `.json` does not.
    SEARCH          /search/suggest.json: one ordinary result and one
                    genuinely reduced one, so the "0.00 means absent"
                    sentinel is exercised in both directions.
    COLLECTIONS_INDEX  two entries of the store's 830, including the
                    `products_count` that is NOT a product count.

Nothing here is HTML, and that is the site rather than a shortcut: a
collection page serves no product grid and a product page publishes no
Product JSON-LD. See product_parser's module docstring for both counts.
"""

import argparse
import ast
import csv
import inspect
import io
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from dataclasses import asdict, fields

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

FAILURES = []
PASSED = 0
SKIPS = []
VERBOSE = False


def check(name, condition, detail=""):
    """Record a check. `detail` may be any value — it is coerced.

    Coerced rather than required to be a string because a check whose detail
    is a list is the common case ("got %s", sorted(missing)), and a suite
    that raises TypeError while REPORTING a failure hides the failure it was
    about to print.
    """
    global PASSED
    if condition:
        PASSED += 1
        if VERBOSE:
            print("  ok   %s" % (name,))
    else:
        FAILURES.append("%s%s" % (name, (" — %s" % (detail,)) if detail != "" else ""))
        print("  FAIL %s%s" % (name, (" — %s" % (detail,)) if detail != "" else ""))


def equal(name, got, want):
    check(name, got == want, "got %r, want %r" % (got, want))


def skip(group, why):
    SKIPS.append("%s: %s" % (group, why))
    print("  SKIP %s — %s" % (group, why))


# ---------------------------------------------------------------------------
# Fixtures — real captures, trimmed, each verified to parse identically
# ---------------------------------------------------------------------------

LISTING_URL = "https://andieswim.com/collections/one-pieces"
LISTING_URL_GB = "https://andieswim.com/en-gb/collections/one-pieces"
LISTING_URL_ODD = "https://andieswim.com/collections/all-accessories"
PRODUCT_URL = ("https://andieswim.com/products/"
               "the-amalfi-swim-dress-eco-nylon-poolside-paisley-classic")
SEARCH_URL = "https://andieswim.com/search?q=bikini"

LISTING_US = r'''
{
 "products": [
  {
   "id": 7022167785544,
   "title": "The Tulum One Piece - Botanical - Pine - Classic",
   "handle": "the-tulum-one-piece-botanical-pine-classic",
   "published_at": "2026-07-14T07:48:52-04:00",
   "vendor": "Andie",
   "product_type": "One Piece",
   "tags": [
    "andie::master => the-tulum-one-piece",
    "AS PF 2026",
    "badge:new",
    "bust-support:medium bust support",
    "category:swimwear",
    "class:Open Back",
    "color-family:green",
    "color:pine",
    "compression:low compression",
    "fabric:botanical jacquard",
    "leg-cut:medium leg cut",
    "pdp-tab:limited",
    "seat-coverage:medium coverage",
    "short-title:The Tulum One Piece",
    "size-chart:general-size-chart",
    "torso-length:classic"
   ],
   "options": [
    {
     "name": "Color",
     "position": 1,
     "values": [
      "PINE"
     ]
    },
    {
     "name": "Size",
     "position": 2,
     "values": [
      "XS",
      "S",
      "M",
      "L",
      "XL"
     ]
    }
   ],
   "images": [
    {
     "src": "https://cdn.shopify.com/s/files/1/0024/2289/8758/files/AO805-PINE_2630_v2.webp?v=1783697443"
    }
   ],
   "variants": [
    {
     "id": 40992092880968,
     "title": "PINE / XS",
     "option1": "PINE",
     "option2": "XS",
     "option3": null,
     "sku": "AO805-PINE-XS",
     "available": true,
     "price": "142.00",
     "compare_at_price": null
    },
    {
     "id": 40992092913736,
     "title": "PINE / S",
     "option1": "PINE",
     "option2": "S",
     "option3": null,
     "sku": "AO805-PINE-S",
     "available": true,
     "price": "142.00",
     "compare_at_price": null
    },
    {
     "id": 40992092946504,
     "title": "PINE / M",
     "option1": "PINE",
     "option2": "M",
     "option3": null,
     "sku": "AO805-PINE-M",
     "available": true,
     "price": "142.00",
     "compare_at_price": null
    },
    {
     "id": 40992092979272,
     "title": "PINE / L",
     "option1": "PINE",
     "option2": "L",
     "option3": null,
     "sku": "AO805-PINE-L",
     "available": true,
     "price": "142.00",
     "compare_at_price": null
    },
    {
     "id": 40992093012040,
     "title": "PINE / XL",
     "option1": "PINE",
     "option2": "XL",
     "option3": null,
     "sku": "AO805-PINE-XL",
     "available": true,
     "price": "142.00",
     "compare_at_price": null
    }
   ]
  },
  {
   "id": 6986747314248,
   "title": "The Amalfi One Piece - Eco Nylon - Sunset Paisley - Classic",
   "handle": "the-amalfi-one-piece-eco-nylon-sunset-paisley-classic",
   "published_at": "2026-05-05T07:34:05-04:00",
   "vendor": "Andie",
   "product_type": "One Piece",
   "tags": [
    "andie::master => the-amalfi-one-piece",
    "AS SU D2 2026",
    "Aug2026 Flash Sale",
    "badge:Final Sale",
    "bust-support:medium bust support",
    "category:swimwear",
    "color-family:orange",
    "color-family:prints",
    "color-family:red",
    "color:sunset paisley",
    "compression:medium compression",
    "fabric:eco nylon",
    "final-sale",
    "hide-free-returns",
    "leg-cut:medium leg cut",
    "no returns",
    "pdp-tab:limited",
    "seat-coverage:medium coverage",
    "short-title:The Amalfi One Piece",
    "size-chart:general-size-chart",
    "torso-length:classic"
   ],
   "options": [
    {
     "name": "Color",
     "position": 1,
     "values": [
      "SUNSET PAISLEY"
     ]
    },
    {
     "name": "Size",
     "position": 2,
     "values": [
      "XS",
      "S",
      "M",
      "L",
      "XL",
      "2X",
      "3X"
     ]
    }
   ],
   "images": [
    {
     "src": "https://cdn.shopify.com/s/files/1/0024/2289/8758/files/AO292-SSPL_547_v2-front.webp?v=1777045009"
    }
   ],
   "variants": [
    {
     "id": 40716029526088,
     "title": "SUNSET PAISLEY / XS",
     "option1": "SUNSET PAISLEY",
     "option2": "XS",
     "option3": null,
     "sku": "AO292-SSPL-XS",
     "available": true,
     "price": "80.00",
     "compare_at_price": "134.00"
    },
    {
     "id": 40716029558856,
     "title": "SUNSET PAISLEY / S",
     "option1": "SUNSET PAISLEY",
     "option2": "S",
     "option3": null,
     "sku": "AO292-SSPL-S",
     "available": true,
     "price": "80.00",
     "compare_at_price": "134.00"
    },
    {
     "id": 40716029591624,
     "title": "SUNSET PAISLEY / M",
     "option1": "SUNSET PAISLEY",
     "option2": "M",
     "option3": null,
     "sku": "AO292-SSPL-M",
     "available": true,
     "price": "80.00",
     "compare_at_price": "134.00"
    },
    {
     "id": 40716029624392,
     "title": "SUNSET PAISLEY / L",
     "option1": "SUNSET PAISLEY",
     "option2": "L",
     "option3": null,
     "sku": "AO292-SSPL-L",
     "available": true,
     "price": "80.00",
     "compare_at_price": "134.00"
    },
    {
     "id": 40716029657160,
     "title": "SUNSET PAISLEY / XL",
     "option1": "SUNSET PAISLEY",
     "option2": "XL",
     "option3": null,
     "sku": "AO292-SSPL-XL",
     "available": true,
     "price": "80.00",
     "compare_at_price": "134.00"
    },
    {
     "id": 40716029689928,
     "title": "SUNSET PAISLEY / 2X",
     "option1": "SUNSET PAISLEY",
     "option2": "2X",
     "option3": null,
     "sku": "AO292-SSPL-XXL",
     "available": false,
     "price": "80.00",
     "compare_at_price": "134.00"
    },
    {
     "id": 40716029722696,
     "title": "SUNSET PAISLEY / 3X",
     "option1": "SUNSET PAISLEY",
     "option2": "3X",
     "option3": null,
     "sku": "AO292-SSPL-XXXL",
     "available": true,
     "price": "80.00",
     "compare_at_price": "134.00"
    }
   ]
  },
  {
   "id": 6986746986568,
   "title": "The Amalfi Swim Dress - Eco Nylon - Poolside Paisley - Classic",
   "handle": "the-amalfi-swim-dress-eco-nylon-poolside-paisley-classic",
   "published_at": "2026-05-05T07:33:59-04:00",
   "vendor": "Andie",
   "product_type": "One Piece",
   "tags": [
    "andie::master => the-amalfi-swim-dress",
    "AS SU D2 2026",
    "badge:Final Sale",
    "bust-support:medium bust support",
    "category:swimwear",
    "color-family:blue",
    "color-family:green",
    "color-family:prints",
    "color:poolside paisley",
    "compression:medium compression",
    "fabric:eco nylon",
    "final-sale",
    "hide-free-returns",
    "leg-cut:low leg cut",
    "no returns",
    "pdp-tab:limited",
    "seat-coverage:full coverage",
    "short-title:The Amalfi Swim Dress",
    "size-chart:general-size-chart",
    "torso-length:classic"
   ],
   "options": [
    {
     "name": "Color",
     "position": 1,
     "values": [
      "POOLSIDE PAISLEY"
     ]
    },
    {
     "name": "Size",
     "position": 2,
     "values": [
      "XS",
      "S",
      "M",
      "L",
      "XL",
      "2X",
      "3X"
     ]
    }
   ],
   "images": [
    {
     "src": "https://cdn.shopify.com/s/files/1/0024/2289/8758/files/AO259-POPL_2496-front.webp?v=1777046266"
    }
   ],
   "variants": [
    {
     "id": 40716028248136,
     "title": "POOLSIDE PAISLEY / XS",
     "option1": "POOLSIDE PAISLEY",
     "option2": "XS",
     "option3": null,
     "sku": "AO259-POPL-XS",
     "available": true,
     "price": "83.00",
     "compare_at_price": "138.00"
    },
    {
     "id": 40716028280904,
     "title": "POOLSIDE PAISLEY / S",
     "option1": "POOLSIDE PAISLEY",
     "option2": "S",
     "option3": null,
     "sku": "AO259-POPL-S",
     "available": true,
     "price": "83.00",
     "compare_at_price": "138.00"
    },
    {
     "id": 40716028313672,
     "title": "POOLSIDE PAISLEY / M",
     "option1": "POOLSIDE PAISLEY",
     "option2": "M",
     "option3": null,
     "sku": "AO259-POPL-M",
     "available": true,
     "price": "83.00",
     "compare_at_price": "138.00"
    },
    {
     "id": 40716028346440,
     "title": "POOLSIDE PAISLEY / L",
     "option1": "POOLSIDE PAISLEY",
     "option2": "L",
     "option3": null,
     "sku": "AO259-POPL-L",
     "available": true,
     "price": "83.00",
     "compare_at_price": "138.00"
    },
    {
     "id": 40716028379208,
     "title": "POOLSIDE PAISLEY / XL",
     "option1": "POOLSIDE PAISLEY",
     "option2": "XL",
     "option3": null,
     "sku": "AO259-POPL-XL",
     "available": true,
     "price": "83.00",
     "compare_at_price": "138.00"
    },
    {
     "id": 40716028411976,
     "title": "POOLSIDE PAISLEY / 2X",
     "option1": "POOLSIDE PAISLEY",
     "option2": "2X",
     "option3": null,
     "sku": "AO259-POPL-XXL",
     "available": false,
     "price": "83.00",
     "compare_at_price": "138.00"
    },
    {
     "id": 40716028444744,
     "title": "POOLSIDE PAISLEY / 3X",
     "option1": "POOLSIDE PAISLEY",
     "option2": "3X",
     "option3": null,
     "sku": "AO259-POPL-XXXL",
     "available": true,
     "price": "83.00",
     "compare_at_price": "138.00"
    }
   ]
  },
  {
   "id": 6981699174472,
   "title": "The Malibu One Piece - Paisley - Oasis - Classic",
   "handle": "the-malibu-one-piece-paisley-oasis-classic",
   "published_at": "2026-02-19T08:04:02-05:00",
   "vendor": "Andie",
   "product_type": "One Piece",
   "tags": [
    "andie::master => the-malibu-one-piece",
    "AS SP D2 2026",
    "badge:Final Sale",
    "bust-support:maximum bust support",
    "category:swimwear",
    "class:high neck",
    "color-family:blue",
    "color-family:green",
    "color:oasis",
    "compression:low compression",
    "fabric:paisley",
    "final-sale",
    "hide-free-returns",
    "leg-cut:medium leg cut",
    "no returns",
    "pdp-tab:limited",
    "seat-coverage:medium coverage",
    "short-title:The Malibu One Piece",
    "size-chart:general-size-chart",
    "torso-length:classic"
   ],
   "options": [
    {
     "name": "Color",
     "position": 1,
     "values": [
      "OASIS"
     ]
    },
    {
     "name": "Size",
     "position": 2,
     "values": [
      "XS",
      "S",
      "M",
      "L",
      "XL",
      "2X",
      "3X"
     ]
    }
   ],
   "images": [
    {
     "src": "https://cdn.shopify.com/s/files/1/0024/2289/8758/files/AO695-OAS_4137-front_d520d575-4fb5-475c-a2a6-f7d495c155f3.jpg?v=1771255035"
    }
   ],
   "variants": [
    {
     "id": 40648117583944,
     "title": "OASIS / XS",
     "option1": "OASIS",
     "option2": "XS",
     "option3": null,
     "sku": "AO695-OAS-XS",
     "available": false,
     "price": "92.00",
     "compare_at_price": "154.00"
    },
    {
     "id": 40648117616712,
     "title": "OASIS / S",
     "option1": "OASIS",
     "option2": "S",
     "option3": null,
     "sku": "AO695-OAS-S",
     "available": false,
     "price": "92.00",
     "compare_at_price": "154.00"
    },
    {
     "id": 40648117649480,
     "title": "OASIS / M",
     "option1": "OASIS",
     "option2": "M",
     "option3": null,
     "sku": "AO695-OAS-M",
     "available": false,
     "price": "92.00",
     "compare_at_price": "154.00"
    },
    {
     "id": 40648117682248,
     "title": "OASIS / L",
     "option1": "OASIS",
     "option2": "L",
     "option3": null,
     "sku": "AO695-OAS-L",
     "available": false,
     "price": "92.00",
     "compare_at_price": "154.00"
    },
    {
     "id": 40648117715016,
     "title": "OASIS / XL",
     "option1": "OASIS",
     "option2": "XL",
     "option3": null,
     "sku": "AO695-OAS-XL",
     "available": false,
     "price": "92.00",
     "compare_at_price": "154.00"
    },
    {
     "id": 40648117747784,
     "title": "OASIS / 2X",
     "option1": "OASIS",
     "option2": "2X",
     "option3": null,
     "sku": "AO695-OAS-XXL",
     "available": false,
     "price": "92.00",
     "compare_at_price": "154.00"
    },
    {
     "id": 40648181841992,
     "title": "OASIS / 3X",
     "option1": "OASIS",
     "option2": "3X",
     "option3": null,
     "sku": "AO695-OAS-XXXL",
     "available": false,
     "price": "92.00",
     "compare_at_price": "154.00"
    }
   ]
  }
 ]
}
'''

LISTING_GB = r'''
{
 "products": [
  {
   "id": 7022167785544,
   "title": "The Tulum One Piece - Botanical - Pine - Classic",
   "handle": "the-tulum-one-piece-botanical-pine-classic",
   "published_at": "2026-07-14T07:48:52-04:00",
   "vendor": "Andie",
   "product_type": "One Piece",
   "tags": [
    "andie::master => the-tulum-one-piece",
    "AS PF 2026",
    "badge:new",
    "bust-support:medium bust support",
    "category:swimwear",
    "class:Open Back",
    "color-family:green",
    "color:pine",
    "compression:low compression",
    "fabric:botanical jacquard",
    "leg-cut:medium leg cut",
    "pdp-tab:limited",
    "seat-coverage:medium coverage",
    "short-title:The Tulum One Piece",
    "size-chart:general-size-chart",
    "torso-length:classic"
   ],
   "options": [
    {
     "name": "Color",
     "position": 1,
     "values": [
      "PINE"
     ]
    },
    {
     "name": "Size",
     "position": 2,
     "values": [
      "XS",
      "S",
      "M",
      "L",
      "XL"
     ]
    }
   ],
   "images": [
    {
     "src": "https://cdn.shopify.com/s/files/1/0024/2289/8758/files/AO805-PINE_2630_v2.webp?v=1783697443"
    }
   ],
   "variants": [
    {
     "id": 40992092880968,
     "title": "PINE / XS",
     "option1": "PINE",
     "option2": "XS",
     "option3": null,
     "sku": "AO805-PINE-XS",
     "available": true,
     "price": "140.00",
     "compare_at_price": null
    },
    {
     "id": 40992092913736,
     "title": "PINE / S",
     "option1": "PINE",
     "option2": "S",
     "option3": null,
     "sku": "AO805-PINE-S",
     "available": true,
     "price": "140.00",
     "compare_at_price": null
    },
    {
     "id": 40992092946504,
     "title": "PINE / M",
     "option1": "PINE",
     "option2": "M",
     "option3": null,
     "sku": "AO805-PINE-M",
     "available": true,
     "price": "140.00",
     "compare_at_price": null
    },
    {
     "id": 40992092979272,
     "title": "PINE / L",
     "option1": "PINE",
     "option2": "L",
     "option3": null,
     "sku": "AO805-PINE-L",
     "available": true,
     "price": "140.00",
     "compare_at_price": null
    },
    {
     "id": 40992093012040,
     "title": "PINE / XL",
     "option1": "PINE",
     "option2": "XL",
     "option3": null,
     "sku": "AO805-PINE-XL",
     "available": true,
     "price": "140.00",
     "compare_at_price": null
    }
   ]
  },
  {
   "id": 6986747314248,
   "title": "The Amalfi One Piece - Eco Nylon - Sunset Paisley - Classic",
   "handle": "the-amalfi-one-piece-eco-nylon-sunset-paisley-classic",
   "published_at": "2026-05-05T07:34:05-04:00",
   "vendor": "Andie",
   "product_type": "One Piece",
   "tags": [
    "andie::master => the-amalfi-one-piece",
    "AS SU D2 2026",
    "Aug2026 Flash Sale",
    "badge:Final Sale",
    "bust-support:medium bust support",
    "category:swimwear",
    "color-family:orange",
    "color-family:prints",
    "color-family:red",
    "color:sunset paisley",
    "compression:medium compression",
    "fabric:eco nylon",
    "final-sale",
    "hide-free-returns",
    "leg-cut:medium leg cut",
    "no returns",
    "pdp-tab:limited",
    "seat-coverage:medium coverage",
    "short-title:The Amalfi One Piece",
    "size-chart:general-size-chart",
    "torso-length:classic"
   ],
   "options": [
    {
     "name": "Color",
     "position": 1,
     "values": [
      "SUNSET PAISLEY"
     ]
    },
    {
     "name": "Size",
     "position": 2,
     "values": [
      "XS",
      "S",
      "M",
      "L",
      "XL",
      "2X",
      "3X"
     ]
    }
   ],
   "images": [
    {
     "src": "https://cdn.shopify.com/s/files/1/0024/2289/8758/files/AO292-SSPL_547_v2-front.webp?v=1777045009"
    }
   ],
   "variants": [
    {
     "id": 40716029526088,
     "title": "SUNSET PAISLEY / XS",
     "option1": "SUNSET PAISLEY",
     "option2": "XS",
     "option3": null,
     "sku": "AO292-SSPL-XS",
     "available": true,
     "price": "77.00",
     "compare_at_price": "130.00"
    },
    {
     "id": 40716029558856,
     "title": "SUNSET PAISLEY / S",
     "option1": "SUNSET PAISLEY",
     "option2": "S",
     "option3": null,
     "sku": "AO292-SSPL-S",
     "available": true,
     "price": "77.00",
     "compare_at_price": "130.00"
    },
    {
     "id": 40716029591624,
     "title": "SUNSET PAISLEY / M",
     "option1": "SUNSET PAISLEY",
     "option2": "M",
     "option3": null,
     "sku": "AO292-SSPL-M",
     "available": true,
     "price": "77.00",
     "compare_at_price": "130.00"
    },
    {
     "id": 40716029624392,
     "title": "SUNSET PAISLEY / L",
     "option1": "SUNSET PAISLEY",
     "option2": "L",
     "option3": null,
     "sku": "AO292-SSPL-L",
     "available": true,
     "price": "77.00",
     "compare_at_price": "130.00"
    },
    {
     "id": 40716029657160,
     "title": "SUNSET PAISLEY / XL",
     "option1": "SUNSET PAISLEY",
     "option2": "XL",
     "option3": null,
     "sku": "AO292-SSPL-XL",
     "available": true,
     "price": "77.00",
     "compare_at_price": "130.00"
    },
    {
     "id": 40716029689928,
     "title": "SUNSET PAISLEY / 2X",
     "option1": "SUNSET PAISLEY",
     "option2": "2X",
     "option3": null,
     "sku": "AO292-SSPL-XXL",
     "available": false,
     "price": "77.00",
     "compare_at_price": "130.00"
    },
    {
     "id": 40716029722696,
     "title": "SUNSET PAISLEY / 3X",
     "option1": "SUNSET PAISLEY",
     "option2": "3X",
     "option3": null,
     "sku": "AO292-SSPL-XXXL",
     "available": true,
     "price": "77.00",
     "compare_at_price": "130.00"
    }
   ]
  },
  {
   "id": 6986746986568,
   "title": "The Amalfi Swim Dress - Eco Nylon - Poolside Paisley - Classic",
   "handle": "the-amalfi-swim-dress-eco-nylon-poolside-paisley-classic",
   "published_at": "2026-05-05T07:33:59-04:00",
   "vendor": "Andie",
   "product_type": "One Piece",
   "tags": [
    "andie::master => the-amalfi-swim-dress",
    "AS SU D2 2026",
    "badge:Final Sale",
    "bust-support:medium bust support",
    "category:swimwear",
    "color-family:blue",
    "color-family:green",
    "color-family:prints",
    "color:poolside paisley",
    "compression:medium compression",
    "fabric:eco nylon",
    "final-sale",
    "hide-free-returns",
    "leg-cut:low leg cut",
    "no returns",
    "pdp-tab:limited",
    "seat-coverage:full coverage",
    "short-title:The Amalfi Swim Dress",
    "size-chart:general-size-chart",
    "torso-length:classic"
   ],
   "options": [
    {
     "name": "Color",
     "position": 1,
     "values": [
      "POOLSIDE PAISLEY"
     ]
    },
    {
     "name": "Size",
     "position": 2,
     "values": [
      "XS",
      "S",
      "M",
      "L",
      "XL",
      "2X",
      "3X"
     ]
    }
   ],
   "images": [
    {
     "src": "https://cdn.shopify.com/s/files/1/0024/2289/8758/files/AO259-POPL_2496-front.webp?v=1777046266"
    }
   ],
   "variants": [
    {
     "id": 40716028248136,
     "title": "POOLSIDE PAISLEY / XS",
     "option1": "POOLSIDE PAISLEY",
     "option2": "XS",
     "option3": null,
     "sku": "AO259-POPL-XS",
     "available": true,
     "price": "80.00",
     "compare_at_price": "135.00"
    },
    {
     "id": 40716028280904,
     "title": "POOLSIDE PAISLEY / S",
     "option1": "POOLSIDE PAISLEY",
     "option2": "S",
     "option3": null,
     "sku": "AO259-POPL-S",
     "available": true,
     "price": "80.00",
     "compare_at_price": "135.00"
    },
    {
     "id": 40716028313672,
     "title": "POOLSIDE PAISLEY / M",
     "option1": "POOLSIDE PAISLEY",
     "option2": "M",
     "option3": null,
     "sku": "AO259-POPL-M",
     "available": true,
     "price": "80.00",
     "compare_at_price": "135.00"
    },
    {
     "id": 40716028346440,
     "title": "POOLSIDE PAISLEY / L",
     "option1": "POOLSIDE PAISLEY",
     "option2": "L",
     "option3": null,
     "sku": "AO259-POPL-L",
     "available": true,
     "price": "80.00",
     "compare_at_price": "135.00"
    },
    {
     "id": 40716028379208,
     "title": "POOLSIDE PAISLEY / XL",
     "option1": "POOLSIDE PAISLEY",
     "option2": "XL",
     "option3": null,
     "sku": "AO259-POPL-XL",
     "available": true,
     "price": "80.00",
     "compare_at_price": "135.00"
    },
    {
     "id": 40716028411976,
     "title": "POOLSIDE PAISLEY / 2X",
     "option1": "POOLSIDE PAISLEY",
     "option2": "2X",
     "option3": null,
     "sku": "AO259-POPL-XXL",
     "available": false,
     "price": "80.00",
     "compare_at_price": "135.00"
    },
    {
     "id": 40716028444744,
     "title": "POOLSIDE PAISLEY / 3X",
     "option1": "POOLSIDE PAISLEY",
     "option2": "3X",
     "option3": null,
     "sku": "AO259-POPL-XXXL",
     "available": true,
     "price": "80.00",
     "compare_at_price": "135.00"
    }
   ]
  },
  {
   "id": 6981699174472,
   "title": "The Malibu One Piece - Paisley - Oasis - Classic",
   "handle": "the-malibu-one-piece-paisley-oasis-classic",
   "published_at": "2026-02-19T08:04:02-05:00",
   "vendor": "Andie",
   "product_type": "One Piece",
   "tags": [
    "andie::master => the-malibu-one-piece",
    "AS SP D2 2026",
    "badge:Final Sale",
    "bust-support:maximum bust support",
    "category:swimwear",
    "class:high neck",
    "color-family:blue",
    "color-family:green",
    "color:oasis",
    "compression:low compression",
    "fabric:paisley",
    "final-sale",
    "hide-free-returns",
    "leg-cut:medium leg cut",
    "no returns",
    "pdp-tab:limited",
    "seat-coverage:medium coverage",
    "short-title:The Malibu One Piece",
    "size-chart:general-size-chart",
    "torso-length:classic"
   ],
   "options": [
    {
     "name": "Color",
     "position": 1,
     "values": [
      "OASIS"
     ]
    },
    {
     "name": "Size",
     "position": 2,
     "values": [
      "XS",
      "S",
      "M",
      "L",
      "XL",
      "2X",
      "3X"
     ]
    }
   ],
   "images": [
    {
     "src": "https://cdn.shopify.com/s/files/1/0024/2289/8758/files/AO695-OAS_4137-front_d520d575-4fb5-475c-a2a6-f7d495c155f3.jpg?v=1771255035"
    }
   ],
   "variants": [
    {
     "id": 40648117583944,
     "title": "OASIS / XS",
     "option1": "OASIS",
     "option2": "XS",
     "option3": null,
     "sku": "AO695-OAS-XS",
     "available": false,
     "price": "89.00",
     "compare_at_price": "150.00"
    },
    {
     "id": 40648117616712,
     "title": "OASIS / S",
     "option1": "OASIS",
     "option2": "S",
     "option3": null,
     "sku": "AO695-OAS-S",
     "available": false,
     "price": "89.00",
     "compare_at_price": "150.00"
    },
    {
     "id": 40648117649480,
     "title": "OASIS / M",
     "option1": "OASIS",
     "option2": "M",
     "option3": null,
     "sku": "AO695-OAS-M",
     "available": false,
     "price": "89.00",
     "compare_at_price": "150.00"
    },
    {
     "id": 40648117682248,
     "title": "OASIS / L",
     "option1": "OASIS",
     "option2": "L",
     "option3": null,
     "sku": "AO695-OAS-L",
     "available": false,
     "price": "89.00",
     "compare_at_price": "150.00"
    },
    {
     "id": 40648117715016,
     "title": "OASIS / XL",
     "option1": "OASIS",
     "option2": "XL",
     "option3": null,
     "sku": "AO695-OAS-XL",
     "available": false,
     "price": "89.00",
     "compare_at_price": "150.00"
    },
    {
     "id": 40648117747784,
     "title": "OASIS / 2X",
     "option1": "OASIS",
     "option2": "2X",
     "option3": null,
     "sku": "AO695-OAS-XXL",
     "available": false,
     "price": "89.00",
     "compare_at_price": "150.00"
    },
    {
     "id": 40648181841992,
     "title": "OASIS / 3X",
     "option1": "OASIS",
     "option2": "3X",
     "option3": null,
     "sku": "AO695-OAS-XXXL",
     "available": false,
     "price": "89.00",
     "compare_at_price": "150.00"
    }
   ]
  }
 ]
}
'''

LISTING_ODD = r'''
{
 "products": [
  {
   "id": 4615163314248,
   "title": "PLAY Everyday Lotion",
   "handle": "supergoop-everyday-lotion",
   "published_at": "2026-07-01T16:59:52-04:00",
   "vendor": "Supergoop",
   "product_type": "Sunscreen",
   "tags": [
    "3p",
    "category:accessories",
    "class:sunscreen",
    "final-sale",
    "hide-free-returns",
    "no returns",
    "short-title:PLAY Everyday Lotion"
   ],
   "options": [
    {
     "name": "Color",
     "position": 1,
     "values": [
      "ORIGINAL"
     ]
    },
    {
     "name": "Size",
     "position": 2,
     "values": [
      "5.5 FL OZ",
      "2.4 FL OZ"
     ]
    },
    {
     "name": "Strength",
     "position": 3,
     "values": [
      "SPF30",
      "SPF50"
     ]
    }
   ],
   "images": [
    {
     "src": "https://cdn.shopify.com/s/files/1/0024/2289/8758/products/Supergoop_PLAY-Everyday-Lotion-SPF-30_Sunscreen-removebg-preview.png?v=1762441545"
    }
   ],
   "variants": [
    {
     "id": 40249308151880,
     "title": "ORIGINAL / 5.5 FL OZ / SPF30",
     "option1": "ORIGINAL",
     "option2": "5.5 FL OZ",
     "option3": "SPF30",
     "sku": "TA003-OS",
     "available": false,
     "price": "36.00",
     "compare_at_price": null
    },
    {
     "id": 40249434669128,
     "title": "ORIGINAL / 5.5 FL OZ / SPF50",
     "option1": "ORIGINAL",
     "option2": "5.5 FL OZ",
     "option3": "SPF50",
     "sku": "TA004-OS",
     "available": true,
     "price": "36.00",
     "compare_at_price": null
    },
    {
     "id": 40249430179912,
     "title": "ORIGINAL / 2.4 FL OZ / SPF30",
     "option1": "ORIGINAL",
     "option2": "2.4 FL OZ",
     "option3": "SPF30",
     "sku": "TA025-OS",
     "available": false,
     "price": "24.00",
     "compare_at_price": null
    },
    {
     "id": 40249434701896,
     "title": "ORIGINAL / 2.4 FL OZ / SPF50",
     "option1": "ORIGINAL",
     "option2": "2.4 FL OZ",
     "option3": "SPF50",
     "sku": "TA026-OS",
     "available": true,
     "price": "24.00",
     "compare_at_price": null
    }
   ]
  },
  {
   "id": 6989494714440,
   "title": "Daily Invisible Gel SPF 40 Sunscreen",
   "handle": "daily-invisible-gel-spf-40-sunscreen",
   "published_at": "2025-12-05T09:07:24-05:00",
   "vendor": "Bask Suncare",
   "product_type": "Sunscreen",
   "tags": [
    "3p",
    "Bask Suncare",
    "category:accessories",
    "class:sunscreen",
    "hide-free-returns",
    "no returns",
    "Shopify Collective",
    "short-title:Daily Invisible Gel SPF 40 Sunscreen",
    "spo-cs-disabled",
    "spo-default",
    "spo-disabled",
    "spo-notify-me-disabled"
   ],
   "options": [
    {
     "name": "Product Size",
     "position": 1,
     "values": [
      "1.7 oz (50mL)",
      ".67 oz (20mL)"
     ]
    },
    {
     "name": "Pack Size",
     "position": 2,
     "values": [
      "Individual",
      "Two-Pack"
     ]
    }
   ],
   "images": [
    {
     "src": "https://cdn.shopify.com/s/files/1/0024/2289/8758/files/dig-1_5e7a92af-87ad-427c-a7ae-717ac778a538.png?v=1762514415"
    }
   ],
   "variants": [
    {
     "id": 40770551251016,
     "title": "1.7 oz (50mL) / Individual",
     "option1": "1.7 oz (50mL)",
     "option2": "Individual",
     "option3": null,
     "sku": "FF-IG-SPF40",
     "available": true,
     "price": "28.00",
     "compare_at_price": null
    },
    {
     "id": 40770551283784,
     "title": "1.7 oz (50mL) / Two-Pack",
     "option1": "1.7 oz (50mL)",
     "option2": "Two-Pack",
     "option3": null,
     "sku": "FF-IG-SPF40x2",
     "available": true,
     "price": "48.00",
     "compare_at_price": "56.00"
    },
    {
     "id": 41146428391496,
     "title": ".67 oz (20mL) / Individual",
     "option1": ".67 oz (20mL)",
     "option2": "Individual",
     "option3": null,
     "sku": "sku-53402498498925",
     "available": true,
     "price": "14.00",
     "compare_at_price": null
    },
    {
     "id": 41146428424264,
     "title": ".67 oz (20mL) / Two-Pack",
     "option1": ".67 oz (20mL)",
     "option2": "Two-Pack",
     "option3": null,
     "sku": "sku-53402498531693",
     "available": true,
     "price": "25.20",
     "compare_at_price": "28.00"
    }
   ]
  }
 ]
}
'''

PRODUCT_JS = r'''
{
 "id": 6986746986568,
 "title": "The Amalfi Swim Dress - Eco Nylon - Poolside Paisley - Classic",
 "handle": "the-amalfi-swim-dress-eco-nylon-poolside-paisley-classic",
 "vendor": "Andie",
 "type": "One Piece",
 "tags": [
  "andie::master => the-amalfi-swim-dress",
  "AS SU D2 2026",
  "badge:Final Sale",
  "bust-support:medium bust support",
  "category:swimwear",
  "color-family:blue",
  "color-family:green",
  "color-family:prints",
  "color:poolside paisley",
  "compression:medium compression",
  "fabric:eco nylon",
  "final-sale",
  "hide-free-returns",
  "leg-cut:low leg cut",
  "no returns",
  "pdp-tab:limited",
  "seat-coverage:full coverage",
  "short-title:The Amalfi Swim Dress",
  "size-chart:general-size-chart",
  "torso-length:classic"
 ],
 "price": 8300,
 "price_min": 8300,
 "price_max": 8300,
 "available": true,
 "options": [
  {
   "name": "Color",
   "position": 1,
   "values": [
    "POOLSIDE PAISLEY"
   ]
  },
  {
   "name": "Size",
   "position": 2,
   "values": [
    "XS",
    "S",
    "M",
    "L",
    "XL",
    "2X",
    "3X"
   ]
  }
 ],
 "featured_image": "//cdn.shopify.com/s/files/1/0024/2289/8758/files/AO259-POPL_2496-front.webp?v=1777046266",
 "description": "<p>The Amalfi, but make it a dress. Our iconic swim silhouette transformed into a chic dress with tried and true fit: scoop neck, built-in bikini, adjustable straps, under-bust shaping, and removable soft cups for the support only Andie delivers.</p>",
 "published_at": "2026-05-05T07:33:59-04:00",
 "variants": [
  {
   "id": 40716028248136,
   "title": "POOLSIDE PAISLEY / XS",
   "option1": "POOLSIDE PAISLEY",
   "option2": "XS",
   "option3": null,
   "sku": "AO259-POPL-XS",
   "available": true,
   "price": 8300,
   "compare_at_price": 13800,
   "featured_image": null
  },
  {
   "id": 40716028280904,
   "title": "POOLSIDE PAISLEY / S",
   "option1": "POOLSIDE PAISLEY",
   "option2": "S",
   "option3": null,
   "sku": "AO259-POPL-S",
   "available": true,
   "price": 8300,
   "compare_at_price": 13800,
   "featured_image": null
  },
  {
   "id": 40716028313672,
   "title": "POOLSIDE PAISLEY / M",
   "option1": "POOLSIDE PAISLEY",
   "option2": "M",
   "option3": null,
   "sku": "AO259-POPL-M",
   "available": true,
   "price": 8300,
   "compare_at_price": 13800,
   "featured_image": null
  },
  {
   "id": 40716028346440,
   "title": "POOLSIDE PAISLEY / L",
   "option1": "POOLSIDE PAISLEY",
   "option2": "L",
   "option3": null,
   "sku": "AO259-POPL-L",
   "available": true,
   "price": 8300,
   "compare_at_price": 13800,
   "featured_image": null
  },
  {
   "id": 40716028379208,
   "title": "POOLSIDE PAISLEY / XL",
   "option1": "POOLSIDE PAISLEY",
   "option2": "XL",
   "option3": null,
   "sku": "AO259-POPL-XL",
   "available": true,
   "price": 8300,
   "compare_at_price": 13800,
   "featured_image": null
  },
  {
   "id": 40716028411976,
   "title": "POOLSIDE PAISLEY / 2X",
   "option1": "POOLSIDE PAISLEY",
   "option2": "2X",
   "option3": null,
   "sku": "AO259-POPL-XXL",
   "available": false,
   "price": 8300,
   "compare_at_price": 13800,
   "featured_image": null
  },
  {
   "id": 40716028444744,
   "title": "POOLSIDE PAISLEY / 3X",
   "option1": "POOLSIDE PAISLEY",
   "option2": "3X",
   "option3": null,
   "sku": "AO259-POPL-XXXL",
   "available": true,
   "price": 8300,
   "compare_at_price": 13800,
   "featured_image": null
  }
 ]
}
'''

SEARCH = r'''
{
 "resources": {
  "results": {
   "products": [
    {
     "id": 4251431239750,
     "title": "The Valencia Bikini Top - Flat - Black",
     "handle": "the-valencia-top-flat-black",
     "url": "/products/the-valencia-top-flat-black?_pos=1&_psq=bikini&_psid=e21b1673e&_ss=e",
     "price": "62.00",
     "price_min": "62.00",
     "price_max": "62.00",
     "compare_at_price_min": "0.00",
     "compare_at_price_max": "0.00",
     "available": true,
     "vendor": "Andie",
     "type": "Bikini Top",
     "tags": [
      "andie::colorspace => essentials",
      "andie::master => the-valencia-top",
      "badge:core",
      "Black",
      "bust-support:medium bust support",
      "category:swimwear",
      "color-family:black",
      "color:Black",
      "compression:medium compression",
      "CORE",
      "Cortina",
      "fabric-family:smooth",
      "fabric:flat",
      "klaviyo-bis:true",
      "Maisonette",
      "medium bust support",
      "occasion:multipurpose",
      "occasion:pregnancy and nursing",
      "pdp-tab:core",
      "short-title:The Valencia Bikini Top",
      "size-chart:general-size-chart",
      "YGroup_valencia"
     ],
     "image": "https://cdn.shopify.com/s/files/1/0024/2289/8758/files/AT227-BLK-_-AB404-BLK_0007.jpg?v=1759441272",
     "variants": []
    },
    {
     "id": 6960341418056,
     "title": "The Maui Bikini Top - Eco Nylon - Mod Geo",
     "handle": "the-maui-bikini-top-eco-nylon-modern-print",
     "url": "/products/the-maui-bikini-top-eco-nylon-modern-print?_pos=6&_psq=bikini&_psid=e21b1673e&_ss=e",
     "price": "29.00",
     "price_min": "29.00",
     "price_max": "29.00",
     "compare_at_price_min": "72.00",
     "compare_at_price_max": "72.00",
     "available": true,
     "vendor": "Andie",
     "type": "Bikini Top",
     "tags": [
      "20_Dollar_Day",
      "andie::master => the-maui-top",
      "badge:Final Sale",
      "bust-support:maximum bust support",
      "category:swimwear",
      "class:Scoop Neck",
      "color-family:prints",
      "color:mod geo",
      "compression:medium compression",
      "fabric:eco nylon",
      "final-sale",
      "hide-free-returns",
      "no returns",
      "nosto-category:two pieces - backend",
      "occasion:active",
      "occasion:chasing toddlers",
      "occasion:girls trip",
      "occasion:honeymoon",
      "occasion:lounging",
      "pdp-tab:limited",
      "push-style",
      "short-title:The Maui Bikini Top",
      "size-chart:general-size-chart",
      "Summer 1.5 2025"
     ],
     "image": "https://cdn.shopify.com/s/files/1/0024/2289/8758/files/Maui_ModGeo_Front.jpg?v=1762446933",
     "variants": []
    }
   ]
  }
 }
}
'''

COLLECTIONS_INDEX = r'''
{
 "collections": [
  {
   "handle": "one-pieces",
   "id": 270871035976,
   "title": "One Pieces",
   "products_count": 472
  },
  {
   "handle": "bikinis",
   "id": 270871003208,
   "title": "Bikinis",
   "products_count": 237
  }
 ]
}
'''


# The three HTML fixtures. Nothing this repo depends on comes out of markup —
# see the module docstring — so these exist only to pin the CLASSIFIER, which
# has to survive a page arriving where a payload was expected.

# The store's own 404 template. `layout--404` sits ~280 KB into the document
# (this theme's <head> is enormous), which is why the classifier searches the
# whole text rather than a prefix: a 20 KB window never reached it and the
# check silently never fired. Verified to classify identically to the full
# 635 KB capture.
NOT_FOUND_HTML = '<html><head><title>404 Not Found</title><link href="https://andieswim.com/cdn/shop/t/1107/assets/main.css"><script src="https://cdn.shopify.com/x.js"></script></head><body class="layout layout--404 loading"><h1>Page not found</h1></body></html>'

# A page the store plainly served, carrying Shopify's storefront-forms
# hCaptcha bundle and its real sitekey — verbatim from the capture. Present
# on EVERY page the store serves, which is exactly why `hcaptcha` is not in
# the marker set (§18).
SERVED_PAGE_HTML = '<html><head><title>One Pieces</title><script src="https://cdn.shopify.com/shopifycloud/x.js"></script><link href="https://cdn.shopify.com/s/files/y.css"><script src="https://cdn.shopify.com/z.js"></script></head><body><script>/* Shopify storefront forms captcha, verbatim shape: */g=\'f06e6c50-85a8-45c8-87d0-21a2b65856fe\',I=\'https://cdn.shopify.com/shopifycloud/storefront-forms-hcaptcha/ce_storefront_forms_captcha_hcaptcha.v1.5.3.iife.js\'</script><div react-component="VisualNavProductListPage"></div></body></html>'

# Chromium's own network-error page. §18's inverted case: it carries the
# site's HOSTNAME in its <title>, so a title check calls it a real page, and
# it references none of the store's assets, which is what actually answers.
CHROMIUM_ERROR_HTML = '<html><head><title>www.andieswim.com</title></head><body><div id="main-frame-error"><span jscontent="heading.msg">www.andieswim.com refused to connect.</span><div class="error-code">ERR_PROXY_CONNECTION_FAILED</div></div></body></html>'

# A Cloudflare challenge. Built rather than captured, because this store has
# never served one — which is the point: the signal has to exist before it
# happens rather than after.
CHALLENGE_HTML = '<html><head><title>Just a moment...</title><script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script></head><body><div id="cf-please-wait">Checking your browser</div><script src="/cdn-cgi/challenge-platform/h/b/orchestrate/chl_page/v1"></script></body></html>'


# ---------------------------------------------------------------------------
# The parser, against the real payloads
# ---------------------------------------------------------------------------

def _rows(text=None, url=None, **kw):
    from product_parser import parse_products
    return parse_products(text or LISTING_US, url or LISTING_URL, **kw)


def check_listing_parses():
    rows = _rows()
    equal("listing: four rows", len(rows), 4)
    r = rows[0]
    equal("listing: sku is the product id", r.sku, "7022167785544")
    equal("listing: handle", r.handle,
          "the-tulum-one-piece-botanical-pine-classic")
    equal("listing: title", r.title,
          "The Tulum One Piece - Botanical - Pine - Classic")
    equal("listing: price", r.price, 142.0)
    equal("listing: brand", r.brand, "Andie")
    equal("listing: product_type", r.product_type, "One Piece")
    equal("listing: base_sku", r.base_sku, "AO805")
    equal("listing: price_source", r.price_source, "products_json")
    equal("listing: locale defaults to the bare market", r.locale, "en-us")
    equal("listing: url is rebuilt from the handle", r.url,
          "https://andieswim.com/products/"
          "the-tulum-one-piece-botanical-pine-classic")
    # VALUES, not coverage (§10): a column can be 100% populated and wrong.
    check("listing: every row has a distinct sku",
          len({x.sku for x in rows}) == len(rows),
          [x.sku for x in rows])
    check("listing: every row is priced",
          all(x.price is not None for x in rows),
          [(x.handle, x.price) for x in rows])


def check_a_was_price_below_the_price_is_not_a_discount():
    """§4: `discount_pct` is None — never 0 and never negative.

    Shopify lets a merchant leave a stale `compare_at_price` UNDER the
    current price. Read as a was-price that publishes a negative discount on
    a product that is not on sale, and the canary pins that no row carries an
    `original_price` at or below its `price`.
    """
    from product_parser import discount_pct
    equal("discount: 83 from 138 is 40%", discount_pct(83.0, 138.0), 40)
    equal("discount: equal prices are not a discount",
          discount_pct(100.0, 100.0), None)
    equal("discount: a was-price BELOW the price is not a discount",
          discount_pct(100.0, 80.0), None)
    equal("discount: a zero was-price is not a discount",
          discount_pct(100.0, 0.0), None)
    equal("discount: no was-price at all", discount_pct(100.0, None), None)
    for r in _rows():
        check("row %s: original_price is above its price" % (r.handle[:24],),
              r.original_price is None or r.price is None
              or r.original_price > r.price,
              (r.price, r.original_price))


def check_a_zero_compare_at_is_absent_not_free():
    """§21's "zero is not a rating", in price form.

    `/search/suggest.json` writes `compare_at_price_min: "0.00"` for a
    product that is NOT on sale — measured 8 of 10 results on one query,
    against two genuinely reduced ones carrying 72.00 and 52.00. Written
    through, a was-price of zero claims the product used to be free.
    """
    rows = _rows(SEARCH, SEARCH_URL, mode="search")
    equal("search: two rows", len(rows), 2)
    plain, sale = rows
    equal("search: an unreduced row has NO original_price",
          plain.original_price, None)
    check("search: an unreduced row's discount is None",
          plain.discount_pct is None, plain.discount_pct)
    check("search: a genuinely reduced row keeps its was-price",
          sale.original_price is not None and sale.original_price > sale.price,
          (sale.price, sale.original_price))
    check("search: no row carries a zero was-price",
          not any(r.original_price == 0 for r in rows))
    equal("search: provenance says which endpoint priced it",
          plain.price_source, "search_json")


def check_the_search_payload_prices_at_the_product_level():
    """`/search/suggest.json` ships `variants: []` on EVERY result.

    Measured 10 of 10. A parser that reads prices only out of `variants`
    returns ten rows with a null price and looks healthy, which is why the
    product-level fallback exists and why this check asserts the VALUE.
    """
    payload = json.loads(SEARCH)
    for p in payload["resources"]["results"]["products"]:
        equal("search fixture: %s ships no variants" % (p["handle"][:24],),
              p["variants"], [])
    rows = _rows(SEARCH, SEARCH_URL, mode="search")
    check("search: every row is priced anyway",
          all(r.price is not None for r in rows),
          [(r.handle, r.price) for r in rows])


def check_options_are_read_by_name_not_by_position():
    """The trap that only a non-swimwear product shows.

    `option1`/`option2` are Color and Size on 622 of 665 products measured,
    and the store also ships `Rate`, `Length`, `Quantity`, `SPF`,
    `Pack Size`, `Strength` and `Product Size`. Reading `option2` as "the
    size" writes another attribute into the size column, silently, on exactly
    the rows nobody checks.
    """
    from product_parser import option_value
    odd = json.loads(LISTING_ODD)["products"][0]
    names = [o["name"] for o in odd["options"]]
    check("fixture really has unusual options", len(names) == 3, names)
    v = odd["variants"][0]
    for i, name in enumerate(names, start=1):
        equal("option %r reads from option%d" % (name, i),
              option_value(odd, v, name), v["option%d" % i])
    equal("an option the product does not have is None",
          option_value(odd, v, "Torso Length"), None)
    equal("option lookup is case-insensitive",
          option_value(odd, v, names[0].lower()), v["option1"])


def check_price_varies_is_written_only_when_it_does():
    """0 of 180 one-pieces vary; 13 of 85 accessories do.

    A `price_max` on every row would be noise; a missing one where the
    variants genuinely disagree publishes one variant's figure as the
    product's.
    """
    for r in _rows():
        equal("swimwear %s: price does not vary" % (r.handle[:22],),
              r.price_varies, False)
        equal("swimwear %s: no price_max" % (r.handle[:22],), r.price_max, None)
    odd = _rows(LISTING_ODD, LISTING_URL_ODD)
    varying = [r for r in odd if r.price_varies]
    check("an accessory in the fixture DOES vary", varying,
          [(r.handle, r.price, r.price_max) for r in odd])
    for r in varying:
        check("a varying row carries price_max above price (%s)"
              % (r.handle[:24],),
              r.price_max is not None and r.price_max > r.price,
              (r.price, r.price_max))
        check("and `price` is the MINIMUM, which is what a tile shows (%s)"
              % (r.handle[:24],), r.price < r.price_max)


def check_stock_is_mixed_and_none_is_not_false():
    """§20: a column never seen taking its other value is not verified.

    The fixture is chosen so all three states are present: every size
    available, some, and none. 63 / 116 / 1 of 180 measured.
    """
    rows = {r.handle: r for r in _rows()}
    states = sorted((r.variants_available, r.variants_total)
                    for r in rows.values())
    check("the fixture covers full, partial and zero availability",
          any(a == t for a, t in states)
          and any(0 < a < t for a, t in states)
          and any(a == 0 for a, t in states), states)
    for r in rows.values():
        if r.variants_available == 0:
            equal("a product with no available size is out of stock",
                  r.in_stock, False)
        else:
            equal("a product with an available size is in stock",
                  r.in_stock, True)


def check_unknown_availability_is_none_not_false():
    """`/products/{h}.json` omits `available` entirely.

    A product read from it must not claim to be out of stock: None means NOT
    STATED (§8). This is also why `product_endpoint()` returns `.js`.
    """
    from product_parser import parse_product_detail
    doc = json.dumps({"product": {
        "id": 1, "title": "T", "handle": "t", "vendor": "Andie",
        "product_type": "One Piece", "tags": [], "options": [{"name": "Size"}],
        "variants": [{"id": 9, "title": "S", "option1": "S", "sku": "X-S",
                      "price": "10.00", "compare_at_price": ""}]}})
    rows = parse_product_detail(doc, PRODUCT_URL)
    equal("a .json product yields its variant", len(rows), 1)
    equal("availability it does not state is None, not False",
          rows[0].in_stock, None)
    equal("an empty-string compare_at is absent, not 0.0",
          rows[0].original_price, None)


def check_the_js_endpoint_prices_in_cents():
    """The unit trap, and it is detected from the PAYLOAD, not the URL.

    `.js` prices in integer cents and everything else in a decimal string.
    Reading one as the other is a factor of 100 in every price — and a
    `--dump-html` replay arrives with no URL to decide from.
    """
    from product_parser import parse_product_detail, payload_is_cents
    raw = json.loads(PRODUCT_JS)
    check("the fixture really is in cents",
          isinstance(raw["variants"][0]["price"], int)
          and raw["variants"][0]["price"] > 1000,
          raw["variants"][0]["price"])
    check("payload_is_cents says so", payload_is_cents(raw))
    check("a {'product': …} document is NOT cents",
          not payload_is_cents({"product": {"handle": "x", "variants": []}}))
    rows = parse_product_detail(PRODUCT_JS, PRODUCT_URL)
    equal("product: one row per variant", len(rows), 7)
    equal("product: cents became major units", rows[0].price, 83.0)
    equal("product: the was-price too", rows[0].original_price, 138.0)
    equal("product: discount", rows[0].discount_pct, 40)
    equal("product: price_source names the endpoint",
          rows[0].price_source, "product_js")


def check_a_product_row_is_a_variant_with_its_own_sku():
    rows = parse_detail()
    equal("product: sku is the variant's own", rows[0].sku, "AO259-POPL-XS")
    equal("product: size read by option name", rows[0].size, "XS")
    equal("product: colour read by option name",
          rows[0].color, "POOLSIDE PAISLEY")
    equal("product: the product id is kept alongside",
          rows[0].product_id, "6986746986568")
    check("product: variant skus are unique",
          len({r.sku for r in rows}) == len(rows), [r.sku for r in rows])
    sold = [r for r in rows if r.in_stock is False]
    equal("product: exactly one size is sold out", len(sold), 1)
    equal("product: and it is the one the store says", sold[0].size, "2X")
    # The SKU suffix and the option value disagree here, which is why the
    # size is read from the option rather than sliced off the sku.
    equal("product: its sku suffix says XXL while its size says 2X",
          sold[0].sku, "AO259-POPL-XXL")


def parse_detail():
    from product_parser import parse_product_detail
    return parse_product_detail(PRODUCT_JS, PRODUCT_URL)


def check_each_parser_refuses_the_others_payload():
    """§20, both directions, on the document's own evidence.

    A listing parser handed a product document would emit one row whose
    `position` is 1 and whose page arithmetic was invented, and the run would
    look complete.
    """
    from product_parser import parse_products, parse_product_detail
    try:
        parse_products(PRODUCT_JS, PRODUCT_URL)
        check("listing parser refuses a product payload", False, "no raise")
    except ValueError as e:
        check("listing parser refuses a product payload",
              "single-product" in str(e), str(e))
    try:
        parse_product_detail(LISTING_US, LISTING_URL)
        check("product parser refuses a listing payload", False, "no raise")
    except ValueError as e:
        check("product parser refuses a listing payload",
              "listing payload" in str(e), str(e))


def check_an_empty_listing_is_not_a_missing_one():
    """The trap that costs a run its meaning.

    `/collections/does-not-exist/products.json` answers HTTP 200 with
    `{"products": []}` — only the HTML route 404s. So "no rows" alone cannot
    say whether the collection is empty or the handle was mistyped, and the
    engines check the store's own index before reporting either.
    """
    from product_parser import (parse_collections_index, catalog_count_for,
                                collection_is_published, detect_page_state)
    index = parse_collections_index(COLLECTIONS_INDEX)
    equal("index parses", sorted(index), ["bikinis", "one-pieces"])
    equal("a published handle is known",
          collection_is_published(index, "one-pieces"), True)
    equal("an unknown handle is reported as unknown",
          collection_is_published(index, "does-not-exist"), False)
    equal("an EMPTY index answers None, not False — unknown is not absent",
          collection_is_published({}, "one-pieces"), None)
    equal("the store's own count is carried",
          catalog_count_for(index, "one-pieces"), 472)
    equal("and it is absent for a handle the index does not have",
          catalog_count_for(index, "nope"), None)
    equal("an empty listing payload is `empty`, never `blocked`",
          detect_page_state('{"products": []}', 200, "")[0], "empty")


def check_catalog_count_is_never_planned_from():
    """`products_count` counts something other than what the store serves.

    472 against 180 for one-pieces, 3089 against 322 for all-swimwear, and
    772 published products in the whole store — so 3089 cannot be a count of
    anything a visitor can reach. Planning against it would mark every run
    partial forever.

    Pinned as a CONSUMER check rather than a value check: nothing in the
    engines may read it except to report it.
    """
    import page_flow
    import inspect
    src = inspect.getsource(page_flow)
    check("page_flow states that the count is not planned from",
          "products_count" in src and "not used" in src.lower()
          or "NOT a count" in src or "not a count" in src.lower(),
          "the reason must live beside the code that ignores it")
    equal("an unknown total plans exactly what was asked for",
          page_flow.plan_from_total(5, None), 5)
    for name in ("playwright_scraper", "puppeteer_scraper", "selenium_scraper"):
        try:
            mod = __import__(name)
        except ImportError as e:
            skip(name, "engine library absent (%s)" % (e.name or e,))
            continue
        src = inspect.getsource(mod)
        check("%s never plans from catalog_count" % (name,),
              "pages_to_plan(args.pages, args.catalog_count" not in src
              and "plan_from_total(args.pages, args.catalog_count" not in src)


def check_cross_market_rows_join_on_the_id():
    """§20: join on the id, never on a label — and say what actually differs.

    Unlike the sibling repos, this store is English everywhere, so titles are
    byte-identical across markets and only the money moves. That is worth
    pinning: it is what makes a cross-market comparison trivial here and
    fiddly there.
    """
    us = {r.sku: r for r in _rows()}
    gb = {r.sku: r for r in _rows(LISTING_GB, LISTING_URL_GB)}
    equal("the same product ids on both markets", sorted(us), sorted(gb))
    for sku in us:
        equal("title is identical across markets (%s)" % (sku[-4:],),
              us[sku].title, gb[sku].title)
        equal("base_sku is identical across markets (%s)" % (sku[-4:],),
              us[sku].base_sku, gb[sku].base_sku)
    equal("locale is carried on the row", gb[list(gb)[0]].locale, "en-gb")
    check("the price really differs between markets",
          any(us[s].price != gb[s].price for s in us),
          [(s, us[s].price, gb[s].price) for s in us])
    check("a GB row's url carries the market prefix",
          all("/en-gb/products/" in r.url for r in gb.values()))
    check("a US row's url carries no prefix",
          all("/en-" not in r.url for r in us.values()))


def check_currency_is_never_guessed_from_the_market():
    """§4/§8. The listing endpoint publishes NO currency field at all.

    So a row's currency is whatever the caller resolved from a document the
    store served, and None when nothing did — never a code derived from the
    `en-gb` in the path, which would be a table this repo invented.
    """
    from product_parser import payload_currency, is_currency_code
    for r in _rows():
        equal("listing row with no resolved currency is null (%s)"
              % (r.handle[:20],), r.currency, None)
    for r in _rows(currency="USD"):
        equal("and carries what was resolved (%s)" % (r.handle[:20],),
              r.currency, "USD")
    equal("payload_currency reads price_currency",
          payload_currency({"product": {"handle": "x", "variants": [
              {"price": "1.00", "price_currency": "GBP"}]}}), "GBP")
    equal("a document that states none answers None",
          payload_currency(json.loads(PRODUCT_JS)), None)
    check("ISO codes are an allowlist, never a bare [A-Z]{3}",
          is_currency_code("GBP") and not is_currency_code("XXL")
          and not is_currency_code("SPF"))


def check_page_and_position_are_threaded_through():
    """§18: `position` restarts at 1 on every page, so the PAIR is the key."""
    p1 = _rows(page=1)
    p2 = _rows(page=2)
    equal("page 1 rows say page 1", sorted({r.page for r in p1}), [1])
    equal("page 2 rows say page 2", sorted({r.page for r in p2}), [2])
    equal("position restarts", [r.position for r in p2], [1, 2, 3, 4])
    pairs = [(r.page, r.position) for r in p1 + p2]
    equal("page+position is unique across the merged run",
          len(set(pairs)), len(pairs))


def check_url_building_and_pagination():
    from product_parser import (listing_endpoint, page_url, product_endpoint,
                                search_endpoint, collections_index_endpoint,
                                page_number_from_url, is_endpoint_url)
    equal("listing endpoint for page 1",
          listing_endpoint(LISTING_URL, 1),
          "https://andieswim.com/collections/one-pieces/products.json"
          "?limit=250&page=1")
    equal("page 3 is an ADDRESS, not a chain",
          page_url(LISTING_URL, 3),
          "https://andieswim.com/collections/one-pieces/products.json"
          "?limit=250&page=3")
    equal("the market prefix is preserved",
          listing_endpoint(LISTING_URL_GB, 2),
          "https://andieswim.com/en-gb/collections/one-pieces/products.json"
          "?limit=250&page=2")
    equal("limit is clamped to what Shopify serves",
          listing_endpoint(LISTING_URL, 1, 9999),
          "https://andieswim.com/collections/one-pieces/products.json"
          "?limit=250&page=1")
    equal("a product reads .js, for its availability",
          product_endpoint(PRODUCT_URL),
          "https://andieswim.com/products/"
          "the-amalfi-swim-dress-eco-nylon-poolside-paisley-classic.js")
    check("search asks the suggest endpoint",
          search_endpoint("bikini top").startswith(
              "https://andieswim.com/search/suggest.json?"))
    check("search carries the market", "/en-gb/search/suggest.json"
          in search_endpoint("x", market="en-gb"))
    equal("page number round-trips",
          page_number_from_url(page_url(LISTING_URL, 7)), 7)
    check("the collections index is an endpoint too",
          is_endpoint_url(collections_index_endpoint()))
    for u, want in ((LISTING_URL, False),
                    (listing_endpoint(LISTING_URL, 1), True),
                    (product_endpoint(PRODUCT_URL), True),
                    (PRODUCT_URL, False)):
        equal("is_endpoint_url(%s)" % (u[-28:],), is_endpoint_url(u), want)


def check_a_sort_by_is_reported_as_not_applied():
    """The endpoint ignores `sort_by`, so a run must not claim it applied one.

    §8: never present a guess as a fact. And note the REASON this is only a
    report rather than a refusal — nothing is capped on this store, so the
    ordering changes `position` and not which rows are in the file.
    """
    from product_parser import (parse_listing, listing_sort_is_applied,
                                sort_from_url, SITE_DEFAULT_SORT)
    plain = LISTING_URL
    sorted_url = LISTING_URL + "?sort_by=price-ascending"
    equal("a plain URL asks for no ordering", sort_from_url(plain), None)
    equal("a sorted URL's request is read back",
          sort_from_url(sorted_url), "price-ascending")
    check("a plain URL's ordering IS what was applied",
          listing_sort_is_applied(plain))
    check("a sort_by is reported as NOT applied",
          not listing_sort_is_applied(sorted_url))
    lp = parse_listing(LISTING_US, sorted_url)
    equal("the listing says so", lp.sort_applied, False)
    equal("and the rows record the ordering that really produced them",
          sorted({r.sort for r in lp.rows}), [SITE_DEFAULT_SORT])
    # The endpoint drops it rather than forwarding it, so the sidecar cannot
    # report an ordering the fetch never sent.
    from product_parser import listing_endpoint
    check("the built endpoint carries no sort_by",
          "sort_by" not in listing_endpoint(sorted_url, 1))


def check_supported_urls_are_refused_with_a_true_reason():
    """§5: refuse WITH the reason. "is not an andieswim.com site" about a host
    that plainly is one sends the reader hunting a typo they did not make."""
    from product_parser import is_supported_url
    for url in (LISTING_URL, LISTING_URL_GB, PRODUCT_URL, SEARCH_URL,
                "https://www.andieswim.com/collections/bikinis",
                "https://andieswim.com/collections/all"):
        ok, why = is_supported_url(url)
        check("supported: %s" % (url[-34:],), ok, why)
    for url, must_say in (
            ("https://example.com/collections/x", "not an andieswim.com host"),
            ("https://andieswim.com/pages/about", "not a collection"),
            ("ftp://andieswim.com/collections/x", "not an http(s) URL"),
            ("https://andieswim.com/collections/account", "account route"),
    ):
        ok, why = is_supported_url(url)
        check("refused: %s" % (url[-30:],), not ok, why)
        check("  and the reason names it: %r" % (must_say,),
              must_say in why, why)


def check_path_shapes():
    from product_parser import (collection_from_url, handle_from_url,
                                market_from_url, locale_from_url,
                                mode_for_url, is_product_url,
                                is_collection_url, is_search_url,
                                market_is_well_formed)
    equal("collection handle", collection_from_url(LISTING_URL), "one-pieces")
    equal("collection handle under a market",
          collection_from_url(LISTING_URL_GB), "one-pieces")
    equal("product handle", handle_from_url(PRODUCT_URL),
          "the-amalfi-swim-dress-eco-nylon-poolside-paisley-classic")
    equal("a handle survives the .js suffix",
          handle_from_url("https://andieswim.com/products/x-y.js"), "x-y")
    equal("market from a prefixed URL",
          market_from_url(LISTING_URL_GB), "en-gb")
    equal("the bare path has no prefix", market_from_url(LISTING_URL), None)
    equal("but its locale is still a market, not null",
          locale_from_url(LISTING_URL), "en-us")
    equal("mode for a collection", mode_for_url(LISTING_URL), "listing")
    equal("mode for a product", mode_for_url(PRODUCT_URL), "product")
    equal("mode for a search", mode_for_url(SEARCH_URL), "search")
    check("a product URL is not a collection URL",
          is_product_url(PRODUCT_URL) and not is_collection_url(PRODUCT_URL))
    check("a search URL is only a search URL",
          is_search_url(SEARCH_URL) and not is_collection_url(SEARCH_URL))
    check("market shape is validated, not enumerated",
          market_is_well_formed("en-gb") and market_is_well_formed("en-zw")
          and not market_is_well_formed("de-de")
          and not market_is_well_formed("engb"))


def check_money_parsing():
    from product_parser import _money, _cents, _was_price
    equal("a decimal string", _money("112.00"), 112.0)
    equal("a zero-decimal currency's whole number", _money("21600"), 21600.0)
    equal("an empty string is absent, not an error", _money(""), None)
    equal("an explicit null is absent", _money(None), None)
    equal("nonsense is absent, not zero", _money("n/a"), None)
    equal("cents become major units", _cents(11200), 112.0)
    equal("a zero was-price is absent", _was_price("0.00"), None)
    equal("a real was-price survives", _was_price("72.00"), 72.0)


def check_a_handle_less_entry_is_dropped_not_guessed():
    """A row whose `url` points at the collection is the §4 failure that makes
    every row look right and point at the wrong page."""
    from product_parser import parse_products
    doc = json.dumps({"products": [
        {"id": 1, "title": "No handle", "variants": [{"price": "1.00"}]},
        {"id": 2, "title": "Fine", "handle": "fine", "options": [],
         "variants": [{"id": 3, "sku": "F", "price": "2.00",
                       "compare_at_price": None, "available": True}]}]})
    rows = parse_products(doc, LISTING_URL)
    equal("the handle-less entry is dropped", len(rows), 1)
    equal("and the good one keeps its own address", rows[0].url,
          "https://andieswim.com/products/fine")


def check_image_urls_in_every_shape_the_store_ships():
    from product_parser import _image_url
    equal("products.json: images[].src",
          _image_url({"images": [{"src": "https://cdn/x.jpg"}]}),
          "https://cdn/x.jpg")
    equal("a protocol-relative URL is made absolute",
          _image_url({"images": [{"src": "//cdn/x.jpg"}]}),
          "https://cdn/x.jpg")
    equal(".js: featured_image as a bare string",
          _image_url({"featured_image": "//cdn/y.jpg"}), "https://cdn/y.jpg")
    equal("suggest.json: image as a string",
          _image_url({"image": "https://cdn/z.jpg"}), "https://cdn/z.jpg")
    equal("nothing at all is None", _image_url({}), None)
    for r in _rows():
        check("listing row %s carries an image" % (r.handle[:20],),
              (r.image_url or "").startswith("https://"), r.image_url)


def check_base_sku_is_none_when_the_variants_disagree():
    """52 of 665 products have no single style code, and inventing one would
    make unrelated products look related in a diff."""
    from product_parser import base_sku
    equal("agreeing variants give the style code",
          base_sku({"variants": [{"sku": "AO805-PINE-XS"},
                                 {"sku": "AO805-PINE-S"}]}), "AO805")
    equal("disagreeing variants give None",
          base_sku({"variants": [{"sku": "AO805-PINE-XS"},
                                 {"sku": "AT227-BLK-S"}]}), None)
    equal("no skus at all give None", base_sku({"variants": []}), None)


def check_load_payload_refuses_rather_than_returning_empty():
    """§8: a function returning `[]` on error is this codebase's most common
    historical bug class — the caller cannot tell "no products" from "we were
    handed a challenge page"."""
    from product_parser import load_payload, payload_is_listing
    equal("an HTML document is not a payload",
          load_payload("<html><body>nope</body></html>"), None)
    equal("empty text is not a payload", load_payload(""), None)
    equal("a bare string is not a payload", load_payload("hello"), None)
    check("but an empty listing IS a payload — empty, not broken",
          payload_is_listing('{"products": []}'))
    # Chromium's JSON viewer wraps the payload in a <pre>, and a --dump-html
    # replay goes back through here.
    wrapped = "<html><body><pre>" + LISTING_US + "</pre></body></html>"
    got = load_payload(wrapped)
    check("a viewer-wrapped replay is recovered",
          isinstance(got, dict) and len(got.get("products", [])) == 4)


def check_page_states_on_real_payloads():
    from product_parser import detect_page_state
    equal("a listing payload is content",
          detect_page_state(LISTING_US, 200, "")[0], "content")
    equal("a product payload is content",
          detect_page_state(PRODUCT_JS, 200, "")[0], "content")
    equal("a search payload is content",
          detect_page_state(SEARCH, 200, "")[0], "content")
    equal("an empty listing is empty, not blocked",
          detect_page_state('{"products": []}', 200, "")[0], "empty")
    equal("the store's 404 template is not_found",
          detect_page_state(NOT_FOUND_HTML, None, "")[0], "not_found")
    equal("a 404 status agrees", detect_page_state("", 404, "")[0], "not_found")
    equal("an empty body on a JSON route is not_found",
          detect_page_state("", None,
                            "https://andieswim.com/products/x.json")[0],
          "not_found")
    equal("a 403 is blocked", detect_page_state("<html/>", 403, "")[0],
          "blocked")
    equal("a Cloudflare challenge is a captcha",
          detect_page_state(CHALLENGE_HTML, 403, "")[0], "captcha")
    equal("and it names the vendor",
          detect_page_state(CHALLENGE_HTML, 403, "")[1], "cloudflare")
    equal("a 503 is retryable, not blocked",
          detect_page_state("<html/>", 503, "")[0], "unknown")
    # §18's inverted case: Chromium's own error page carries the site's
    # HOSTNAME in its title and none of its assets, so a title check calls it
    # a real page.
    equal("Chromium's own error page is not a served page",
          detect_page_state(CHROMIUM_ERROR_HTML, None, "")[0], "blocked")


def check_the_positive_payload_signal_is_checked_before_any_heuristic():
    """§17's classification-order trap.

    A sibling repo checked "does this page reference the site's own assets at
    least twice?" BEFORE the site's own unambiguous positive signal, and a
    minimal real page therefore came back blocked — exit 3 for a correct
    answer. Here the unambiguous signal is that the text IS one of the
    store's payloads, and nothing but the store serves one.
    """
    from product_parser import detect_page_state
    # A payload with no asset references anywhere in it.
    bare = json.dumps({"products": [{"id": 1, "handle": "x", "title": "X",
                                     "options": [],
                                     "variants": [{"id": 2, "sku": "S",
                                                   "price": "1.00",
                                                   "compare_at_price": None,
                                                   "available": True}]}]})
    check("the payload names the asset host zero times",
          "cdn.shopify.com" not in bare)
    equal("and it still classifies as content",
          detect_page_state(bare, 200, "")[0], "content")


def check_markers_do_not_match_a_page_the_store_serves():
    """§18: count every candidate on a page you KNOW is good, first.

    Two are deliberately absent from the marker set and both would have
    fired on every successful run:

      cf-turnstile   2Captcha's own auto-solve extension injects
                     `data-ts-input="cf-turnstile-response"` into every page
                     it loads, so it fires on GOOD pages and, measured on two
                     sibling repos, MISSES real challenges.
      hcaptcha       this store ships Shopify's storefront-forms hCaptcha
                     bundle on every page it serves, bound to form submits.
                     One occurrence on five of five served pages.
    """
    from product_parser import BOT_CHALLENGE_MARKERS, detect_bot_challenge
    markers = [m for m, _ in BOT_CHALLENGE_MARKERS]
    check("cf-turnstile is NOT a marker", "cf-turnstile" not in markers,
          markers)
    check("hcaptcha is NOT a marker",
          not any("hcaptcha" in m.lower() for m in markers), markers)
    check("challenges.cloudflare.com IS",
          "challenges.cloudflare.com" in markers, markers)
    for name, text in (("LISTING_US", LISTING_US), ("PRODUCT_JS", PRODUCT_JS),
                       ("SEARCH", SEARCH), ("SERVED_PAGE", SERVED_PAGE_HTML)):
        for marker in markers:
            check("%s carries no %r" % (name, marker),
                  marker.lower() not in text.lower())
        equal("%s is not a challenge" % (name,),
              detect_bot_challenge(text), None)
    equal("a real challenge still matches",
          detect_bot_challenge(CHALLENGE_HTML), "cloudflare")


def check_the_shopify_form_captcha_is_present_and_deliberately_ignored():
    """§18: "no challenge rendered" is not "no captcha configured".

    The store DOES ship a captcha — Shopify's storefront-forms hCaptcha, with
    a real sitekey — and this repo must not claim otherwise. What it claims
    is narrower and true: it is bound to form submits and no read path
    renders one.
    """
    check("the served-page fixture really carries the Shopify bundle",
          "ce_storefront_forms_captcha_hcaptcha" in SERVED_PAGE_HTML)
    check("...with its sitekey",
          "f06e6c50-85a8-45c8-87d0-21a2b65856fe" in SERVED_PAGE_HTML)
    check("...and it is still not classified as a challenge",
          __import__("product_parser").detect_bot_challenge(
              SERVED_PAGE_HTML) is None)


def check_a_marker_survives_both_encodings():
    """§20: an edge can entity-escape the punctuation in its own refusal URL,
    so a literal marker matches a browser's DOM and silently misses the same
    page read by an HTTP client."""
    from product_parser import detect_bot_challenge
    plain = '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js">'
    escaped = plain.replace(":", "&#58;").replace("/", "&#47;").replace(".", "&#46;")
    equal("plain spelling matches", detect_bot_challenge(plain), "cloudflare")
    equal("entity-escaped spelling matches too",
          detect_bot_challenge(escaped), "cloudflare")


def check_positive_asset_detection():
    from product_parser import references_own_assets, looks_like_a_served_page
    check("a served page references the store's own assets",
          references_own_assets(SERVED_PAGE_HTML) >= 2,
          references_own_assets(SERVED_PAGE_HTML))
    check("and is recognised as served", looks_like_a_served_page(SERVED_PAGE_HTML))
    check("Chromium's error page references none",
          references_own_assets(CHROMIUM_ERROR_HTML) == 0)
    check("and is not recognised as served",
          not looks_like_a_served_page(CHROMIUM_ERROR_HTML))
    check("even though it carries the site's own hostname in its title",
          "andieswim.com" in CHROMIUM_ERROR_HTML)


def check_product_link_count_reads_handles_too():
    """§20's broken-parser signal has to work on a JSON document, which
    contains no anchors at all."""
    from product_parser import product_link_count
    equal("a listing payload names its four handles",
          product_link_count(LISTING_US), 4)
    equal("markup with hrefs is counted too",
          product_link_count('<a href="/products/a">x</a>'
                             '<a href="/products/b">y</a>'), 2)
    equal("an empty payload names none", product_link_count('{"products": []}'), 0)


def check_a_broken_parser_is_not_reported_as_an_empty_collection():
    """§20: a payload the store SERVED that names N products and parses to
    zero is OUR bug, and saying "0 products" sends the reader to check the
    URL instead of the parser."""
    import page_flow
    from product_parser import parse_products, product_link_count
    # The shape a future key rename would take: entries are there, but the
    # top-level key the parser reads is gone.
    broken = json.dumps({"items": json.loads(LISTING_US)["products"]})
    rows = parse_products(broken, LISTING_URL)
    equal("a renamed key parses to nothing", rows, [])
    links = product_link_count(broken)
    check("but the document plainly names products", links >= 2, links)
    check("and that is reported as a parse failure, not an empty collection",
          page_flow.looks_like_a_parse_failure("content", len(rows), links))
    check("while a genuinely empty listing is NOT a parse failure",
          not page_flow.looks_like_a_parse_failure("empty", 0, 0))


def check_state_policy():
    import page_flow

    equal("policy: content is parsed", page_flow.should_parse("content"), True)
    equal("policy: content is not retried", page_flow.should_retry("content"), False)

    # An empty page is an ANSWER. It must not be retried and must not be
    # reported as blocked.
    equal("policy: empty is parsed", page_flow.should_parse("empty"), True)
    equal("policy: empty is not retried", page_flow.should_retry("empty"), False)
    equal("policy: empty is not blocked", page_flow.counts_as_blocked("empty"), False)

    # A refusal offers nothing to solve, so it must not spend money.
    equal("policy: blocked never pays a solver",
          page_flow.should_solve("blocked"), False)
    equal("policy: blocked is blocked", page_flow.counts_as_blocked("blocked"), True)

    # A rendered widget IS a test, and is the one state that pays.
    equal("policy: a captcha may be solved", page_flow.should_solve("captcha"), True)

    equal("policy: unknown waits rather than spending",
          (page_flow.should_retry("unknown"), page_flow.should_solve("unknown")),
          (True, False))
    # An unrecognised state must fall back to the cautious one rather than
    # raising, so a new state name cannot crash a run mid-flight.
    equal("policy: an unknown state name falls back to 'unknown'",
          page_flow.should_solve("something-new"), False)


def check_pagination_addressability_is_asked_per_url():
    """§18: ask PER URL, not per site.

    A sibling repo has one page kind that paginates by address and one that
    does not, and a `page_url()` used unconditionally there reported a
    COMPLETE run holding page 1. This store has the same split, so the same
    question has to be asked:

      a collection  ?page=N is a different slice — verified by walking the
                    whole catalogue: 250 + 250 + 250 + 22 = 772 distinct
                    handles, no repeats, page 5 empty.
      a search      ONE response. Shopify caps predictive search at 10
                    results and publishes no page 2 at all.
      a product     ONE document.
    """
    import page_flow
    check("pagination: a collection listing is addressable",
          page_flow.pagination_is_addressable(LISTING_URL))
    check("pagination: and so is one under a market prefix",
          page_flow.pagination_is_addressable(LISTING_URL_GB))
    check("pagination: a SEARCH is not — it is one capped response",
          not page_flow.pagination_is_addressable(SEARCH_URL))
    check("pagination: a PRODUCT is not — it is one document",
          not page_flow.pagination_is_addressable(PRODUCT_URL))


def check_pagination_is_planned_from_the_sites_own_number():
    import page_flow
    equal("plan: clamped to what the site says exists",
          page_flow.pages_to_plan(50, 12), 12)
    equal("plan: a smaller request is honoured", page_flow.pages_to_plan(3, 12), 3)
    # An unknown count is not a zero: where page 1 stated nothing, the run
    # discovers the end from the data (§7 layer 3).
    equal("plan: unknown means the request stands",
          page_flow.pages_to_plan(5, None), 5)
    equal("plan: never less than one page", page_flow.pages_to_plan(0, 12), 1)
    equal("plan: from a result COUNT rather than a page count",
          page_flow.plan_from_total(50, 280, 24), 12)


def check_policy_constants_have_a_consumer():
    """§17: a policy constant nothing reads is the same defect as dead code.

    `RETRY_ON_BLOCKED` carried a paragraph of measured justification in a
    sibling repo and NO engine consulted it, so setting it False changed
    nothing while the prose read like enforcement.
    """
    import page_flow
    sources = {}
    for name in ("playwright_scraper", "puppeteer_scraper", "selenium_scraper"):
        path = os.path.join(HERE, name + ".py")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                sources[name] = f.read()
    check("policy: the engines are readable", len(sources) == 3, sorted(sources))

    for const in ("RETRY_ON_BLOCKED", "BLOCK_RETRIES_WITHOUT_POOL",
                  "SOLVES_PER_PAGE"):
        readers = [n for n, s in sources.items() if const in s]
        check("policy: %s is read by an engine" % const, readers, "no consumer")


def check_row_schema():
    from output_writer import Product, ROW_CLASS_BY_MODE, UNIQUE_BY_SKU_MODES
    names = [f.name for f in fields(Product)]
    equal("the family prefix is byte-identical and in order (§9)",
          names[:5], ["source", "scraped_at", "url", "sku", "title"])

    # The commerce columns this site DOES have. This is a shop, so the
    # family's price fields are present rather than dropped — including the
    # discount pair, which a sibling repo correctly drops because its site
    # has no discount chain. Here 81 of 180 one-pieces and 150 of 150 sale
    # items carry a `compare_at_price`, so both columns earn their place.
    for present in ("brand", "price", "currency", "in_stock", "image_url",
                    "category", "price_source", "original_price",
                    "discount_pct"):
        check("the commerce column %r is present" % present, present in names)

    # And the ones measured ABSENT, each with the measurement in
    # output_writer's docstring. §9 says removing a column needs the
    # measurement written down; this pins that they stay removed until
    # someone re-measures.
    #
    #   rating / review_count  the store uses Okendo, whose stars are
    #                          `display:none` in the collection grid and
    #                          absent from every JSON route this repo reads.
    #                          One extra third-party request PER PRODUCT
    #                          would be needed — 180 for one collection — so
    #                          the column is not free and is not present.
    #   lowest_price_30d       the EU Omnibus disclosure a sibling repo needs.
    #                          Not published anywhere on this store, on any
    #                          market, including the EU ones.
    for gone in ("lowest_price_30d", "rating", "review_count", "ean", "gtin",
                 "sub_collection", "special_edition", "variant_of"):
        check("the column %r is absent, not null-forever" % gone,
              gone not in names,
              "if this is back, output_writer's measurement should be too")

    # Site-specific columns go at the END of the row (§9), after the family's.
    equal("site-specific columns come last",
          names[15:], ["locale", "product_id", "handle", "base_sku",
                       "product_type", "original_price", "discount_pct",
                       "price_max", "price_varies", "variants_total",
                       "variants_available", "tags", "published_at",
                       "collection", "sort", "variant_id", "variant_title",
                       "color", "size"])
    equal("and the family block ends where it always does",
          names[:16], ["source", "scraped_at", "url", "sku", "title", "brand",
                       "price", "currency", "in_stock", "image_url",
                       "category", "price_source", "page", "position", "mode",
                       "locale"])

    equal("every mode maps to a row class",
          sorted(ROW_CLASS_BY_MODE), ["listing", "product", "search"])
    equal("every mode is one row per sku",
          sorted(UNIQUE_BY_SKU_MODES), ["listing", "product", "search"])
    equal("all three modes share one class",
          len({c for c in ROW_CLASS_BY_MODE.values()}), 1)


def check_csv_and_json_writers():
    from output_writer import Product, write_csv, write_json
    import product_parser as P
    rows = P.parse_listing(LISTING_US, LISTING_URL).rows
    check("the fixture produced rows to write", len(rows) > 0, len(rows))
    with tempfile.TemporaryDirectory() as tmp:
        csv_path = os.path.join(tmp, "out.csv")
        write_csv(rows, csv_path, row_cls=Product)
        with open(csv_path, encoding="utf-8") as f:
            reader = list(csv.reader(f))
        equal("CSV header matches the dataclass, in order",
              reader[0], [f.name for f in fields(Product)])
        equal("CSV holds every row", len(reader) - 1, len(rows))
        check("no Python list repr leaked into the CSV",
              not any(cell.startswith("[") for row in reader[1:] for cell in row))

        empty_csv = os.path.join(tmp, "empty.csv")
        write_csv([], empty_csv, row_cls=Product)
        with open(empty_csv, encoding="utf-8") as f:
            header = list(csv.reader(f))
        equal("an EMPTY csv still carries its header", len(header), 1)
        equal("...and it is the right one", header[0],
              [f.name for f in fields(Product)])

        json_path = os.path.join(tmp, "out.json")
        write_json(rows, json_path)
        loaded = json.load(open(json_path, encoding="utf-8"))
        equal("JSON holds every row", len(loaded), len(rows))
        equal("JSON keys are the dataclass fields, in order",
              list(loaded[0].keys()), [f.name for f in fields(Product)])
        equal("JSON and CSV agree on the column ORDER",
              list(loaded[0].keys()), reader[0])


def check_exit_codes():
    import output_writer as O
    equal("0 ok / 1 crash / 2 usage / 3 blocked / 4 empty / 5 api / 6 partial",
          (O.EXIT_BLOCKED, O.EXIT_NO_PRODUCTS, O.EXIT_API_ERROR, O.EXIT_PARTIAL),
          (3, 4, 5, 6))
    check("page_cap_reached is a COMPLETE stop reason",
          "page_cap_reached" in O.COMPLETE_STOP_REASONS)
    check("single_page_mode is complete by construction",
          "single_page_mode" in O.COMPLETE_STOP_REASONS)
    check("no_new_products is complete",
          "no_new_products" in O.COMPLETE_STOP_REASONS)


def check_a_run_that_finds_nothing_writes_nothing():
    """Never replace last night's good output with []."""
    from output_writer import save
    with tempfile.TemporaryDirectory() as tmp:
        prefix = os.path.join(tmp, "out")
        with open(prefix + ".json", "w", encoding="utf-8") as f:
            f.write('[{"sku": "yesterday"}]')
        code = save([], prefix, "json", allow_empty=False)
        equal("an empty run exits 4", code, 4)
        equal("...and leaves the previous good file alone",
              open(prefix + ".json", encoding="utf-8").read(),
              '[{"sku": "yesterday"}]')
        code = save([], prefix, "json", allow_empty=True)
        equal("--allow-empty WRITES the empty file...", 
              json.load(open(prefix + ".json", encoding="utf-8")), [])
        # ...and still reports exit 4. Pinned deliberately (§10: pin a known
        # behaviour rather than half-guarding it): "zero businesses" is true
        # whether or not the file was written, and a caller that wanted the
        # file still wants to know the result was empty.
        equal("...and still reports exit 4, because it IS empty", code, 4)


def check_page_and_position_are_unique_across_pages():
    """One line, and the column is worthless without it: `position` restarts
    at 1 on every page."""
    import product_parser as P
    page1 = P.parse_listing(LISTING_US, LISTING_URL, page=1).rows
    page2 = P.parse_listing(LISTING_US, LISTING_URL, page=2).rows
    pairs = [(r.page, r.position) for r in page1 + page2]
    equal("page+position is unique across a multi-page run",
          len(set(pairs)), len(pairs))
    equal("page 2's rows really say page 2",
          sorted({r.page for r in page2}), [2])


def check_sidecar_shape():
    from output_writer import run_meta
    meta = run_meta(status="complete", stop_reason="no_new_products",
                    pages_requested=3, pages_completed=2, pages_failed=[],
                    products=180, mode="listing", source="andieswim.com",
                    start_url="https://andieswim.com/collections/one-pieces",
                    final_url=("https://andieswim.com/collections/one-pieces"
                               "/products.json?limit=250&page=2"),
                    extra={"total_results": None, "pages_available": None,
                           "page_size": 250, "locale": "en-us",
                           "currency": "USD",
                           "currency_source": "price_currency",
                           "collection": "one-pieces",
                           "catalog_count": 472,
                           "catalog_count_note": "not a count of products the "
                                                 "storefront serves",
                           "sort_applied": "collection-default",
                           "capped_by_site": False})
    for key in ("status", "stop_reason", "pages_requested", "pages_completed",
                "pages_failed", "mode", "source"):
        check("the sidecar records %r" % key, key in meta)
    equal("...and the market the prices belong to", meta["locale"], "en-us")
    equal("...and the currency they are in", meta["currency"], "USD")
    equal("...and where that currency was read from",
          meta["currency_source"], "price_currency")
    equal("...and the collection that was walked",
          meta["collection"], "one-pieces")
    equal("pages_failed is a LIST of numbers, not a count",
          isinstance(meta["pages_failed"], list), True)

    # The site's own count is carried and it is carried WITH ITS WARNING.
    # 472 against the 180 the storefront serves; a reader who fetches the
    # collection index themselves will see the gap and deserves to be told,
    # in the artefact, that the larger number is not a target this run
    # missed (§21: record the site's own arithmetic beside "complete").
    equal("the sidecar carries the store's own count", meta["catalog_count"], 472)
    check("...and the warning travels with it",
          "not a count" in (meta.get("catalog_count_note") or ""),
          meta.get("catalog_count_note"))

    # `total_results` is present and NULL, which is different from absent:
    # this store states no count anywhere, and None means UNKNOWN. Treating a
    # missing count as zero would cap every run after page 1 at no pages.
    check("total_results is present and null, not zero",
          "total_results" in meta and meta["total_results"] is None,
          meta.get("total_results"))

    # `capped_by_site` is False on a LISTING, and the value is the finding:
    # this store imposes no page cap, so a listing run that reached the end
    # really does hold the whole collection. It is True only for --mode
    # search, which Shopify caps at 10 results.
    equal("capped_by_site is False for a listing",
          meta.get("capped_by_site"), False)


# ---------------------------------------------------------------------------
# The engines — the five checks CLAUDE.md §17 says to steal
# ---------------------------------------------------------------------------

ENGINES = ("playwright_scraper", "selenium_scraper", "puppeteer_scraper")
DRIVER_IMPORTS = {
    "playwright_scraper": "playwright",
    "selenium_scraper": "selenium",
    "puppeteer_scraper": "pyppeteer",
}


def _import_engine(name):
    try:
        return __import__(name)
    except ImportError as e:
        skip(name, "engine library absent (%s)" % e)
        return None


def check_engines_import_their_driver_at_module_level():
    """For the guarded imports above to MEAN anything.

    A sibling repo imported `launch`/`connect` inside the launch path, so the
    module imported cleanly with no pyppeteer installed: the group never
    skipped, and the CI job that exists to fail on unexpected skips could not
    have caught a broken import. It also let CI run against a stub version
    for a while without anything noticing. This drifts back silently, so it
    is asserted with an `ast` walk rather than trusted.
    """
    for module, driver in DRIVER_IMPORTS.items():
        path = os.path.join(HERE, module + ".py")
        if not os.path.exists(path):
            check("%s exists" % module, False)
            continue
        tree = ast.parse(open(path, encoding="utf-8").read())
        top_level = set()
        for node in tree.body:          # module level ONLY
            if isinstance(node, ast.Import):
                top_level.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                top_level.add(node.module.split(".")[0])
        check("%s imports %s at MODULE level" % (module, driver),
              driver in top_level,
              "top-level imports: %s" % sorted(top_level))


def check_shared_calls_bind_against_the_real_signature():
    """§17's check #1, and the one that earns its keep.

    A sibling repo shipped `classify(html, url=…)` in two of three engines
    against a callee taking `status` second, and BOTH crashed on their first
    fetch — invisible to import, --help, compileall, the undefined-name walk
    and 400+ green assertions, because none of those calls a function the way
    a live run does.

    This walks every engine's AST for calls into the shared modules and binds
    each one against the callee's real signature.
    """
    import page_flow
    import product_parser
    import output_writer
    targets = {"page_flow": page_flow, "product_parser": product_parser,
               "output_writer": output_writer}
    bound = 0
    for module in ENGINES + ("scraper_api_client",):
        path = os.path.join(HERE, module + ".py")
        if not os.path.exists(path):
            continue
        source = open(path, encoding="utf-8").read()
        tree = ast.parse(source)
        # Which shared names this file imported directly (`from x import y`).
        direct = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in targets:
                for alias in node.names:
                    direct[alias.asname or alias.name] = (
                        targets[node.module], alias.name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            owner = attr = None
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if func.value.id in targets:
                    owner, attr = targets[func.value.id], func.attr
            elif isinstance(func, ast.Name) and func.id in direct:
                owner, attr = direct[func.id]
            if owner is None:
                continue
            # A name that is NOT THERE is the loudest possible failure and
            # this check used to swallow it: `getattr(..., None)` returned
            # None, `not callable(None)` was true, and the call was skipped.
            # In a sibling repo (bbb-scraper, CLAUDE.md §22), three calls
            # into a page_flow API that did not exist there --
            # comparable(), next_page_selector(), next_page_candidates(),
            # all of them tokopedia-scraper's, all arriving with copied
            # code -- sat in two engines under a green run of this very
            # function. Absent is not "nothing to bind".
            if not hasattr(owner, attr):
                check("%s.%s exists (called from %s:%d)"
                      % (getattr(owner, "__name__", owner), attr,
                         module + ".py", node.lineno),
                      False,
                      "the engine calls a name the shared module does not "
                      "define; a live run reaches this as AttributeError")
                continue
            callee = getattr(owner, attr)
            if not callable(callee) or inspect.isclass(callee):
                continue
            try:
                signature = inspect.signature(callee)
            except (TypeError, ValueError):
                continue
            positional = [inspect.Parameter.empty] * len(node.args)
            keywords = {}
            for kw in node.keywords:
                if kw.arg is None:          # **kwargs — cannot be checked here
                    keywords = None
                    break
                keywords[kw.arg] = inspect.Parameter.empty
            if keywords is None:
                continue
            try:
                signature.bind(*positional, **keywords)
                bound += 1
            except TypeError as e:
                check("%s:%d %s.%s(...) binds against its real signature"
                      % (module, node.lineno, owner.__name__, attr),
                      False, "%s; signature is %s" % (e, signature))
    check("every shared-module call in every engine binds (%d checked)" % bound,
          bound > 40, "only %d calls were checked — is the walk finding them?"
          % bound)


def _argparse_flags(module_name):
    """Every --flag a module's parser defines, without running the CLI."""
    path = os.path.join(HERE, module_name + ".py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    # Only calls on the argparse parser itself. A browser's option object
    # also has `add_argument`, and counting Chrome's own switches
    # (`--no-sandbox`, `--window-size=…`) as CLI flags made this check
    # compare nonsense.
    parsers = {"p"}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr in ("add_argument_group",
                                             "add_mutually_exclusive_group")):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    parsers.add(target.id)
    flags = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in parsers):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                        and arg.value.startswith("--"):
                    flags.add(arg.value)
    return flags


# The family's flag contract (CLAUDE.md §9), plus this repo's own additions.
CONTRACT_FLAGS = {
    "--url", "--pages", "--category", "--format", "--out", "--delay",
    "--retries", "--retry-delay", "--concurrency", "--proxy", "--proxy-file",
    "--proxy-rotate", "--proxy-shuffle", "--proxy-block-retries",
    "--twocaptcha-key", "--captcha-api", "--solve-captcha", "--min-score",
    "--cdp-endpoint", "--allow-empty", "--dump-html",
}
# The five flags CLAUDE.md §9 omitted for months while nearly every repo in
# the family shipped them, plus this site's own additions.
#
# `--fingerprint`, `--fp-tags`, `--fp-country` and `--mode` are in 17 of the
# 18 repos counted; `--locale` is in 16. Re-derive rather than trusting this
# comment (§13):
#
#   grep -ohE '"--[a-z0-9-]+"' */playwright_scraper.py | sort | uniq -c | sort -rn
FAMILY_FLAGS = {"--fingerprint", "--fp-tags", "--fp-country", "--locale",
                "--mode"}

# Site-specific, and each one earns its place:
#   --query   builds a /search URL without hand-assembling one
#   --limit   products per request; Shopify caps it at 250 and ignores more
#
# `--sort` is deliberately NOT here — see check_banned_and_removed_flags for
# the measurement, and note that its absence is asserted rather than merely
# omitted, because the sibling repo this code came from ships one.
SITE_FLAGS = {"--query", "--limit"}


def check_engine_flag_sets():
    """§17's check #2: against the contract AND against each other, both ways.

    A missing flag fails; so does closing a difference the README documents.
    """
    sets = {}
    for module in ENGINES:
        if not os.path.exists(os.path.join(HERE, module + ".py")):
            continue
        sets[module] = _argparse_flags(module)
    for module, flags in sets.items():
        missing = (CONTRACT_FLAGS | FAMILY_FLAGS | SITE_FLAGS) - flags
        check("%s defines every contract flag" % module, not missing,
              "missing %s" % sorted(missing))
    # The ONE documented difference: pyppeteer downloads its own Chromium
    # and could not launch it on the development machine, so it needs a way
    # to point at another one. Its twins have no equivalent because they do
    # not ship a browser. Listed here so that closing the difference — or
    # growing a second one — fails the build (§17).
    DOCUMENTED_DIFFERENCES = {"puppeteer_scraper": {"--chromium-path"}}
    names = sorted(sets)
    for i in range(len(names) - 1):
        a, b = names[i], names[i + 1]
        only_a = sets[a] - sets[b] - DOCUMENTED_DIFFERENCES.get(a, set())
        only_b = sets[b] - sets[a] - DOCUMENTED_DIFFERENCES.get(b, set())
        check("%s and %s define the same flags" % (a, b),
              not only_a and not only_b,
              "only in %s: %s; only in %s: %s"
              % (a, sorted(only_a), b, sorted(only_b)))


# `--sort` joins the banned list, and it is the interesting entry.
#
# It is not banned in the family — a sibling repo needs one, because that
# site CAPS a result set and the ordering decides which rows land inside the
# cap. Here the JSON endpoint takes no `sort_by` and ignores one that is
# passed (verified 2026-09-18: the response is the same with and without),
# and nothing is capped, so ordering decides `position` and nothing else.
# A flag would report an ordering the fetch never applied — §8's "never
# present a guess as a fact", with a column attached.
#
# Asserted rather than left absent because this repo was built from that
# sibling and an editor reconciling the two would put it back (§10).
BANNED_FLAGS = ("--antidetect", "--country-code", "--sort", "--page-size")


def check_banned_and_removed_flags():
    """Scoped to the ENGINES.

    `--country` is absent here — the flag CLAUDE.md §10 bans outright — and
    `--locale` takes its place, because on this store the market really is a
    property of the URL rather than of the browser.

    That makes the ban's REASON bite harder than usual: the market is a path
    prefix, so a `--locale` that disagreed with a `--url` would silently read
    a different market, and a different market is a different PRICE (112.00
    USD against 110.00 GBP and 21600 JPY for one variant, 2026-09-18). So
    the flag is refused alongside a URL that names a different one, and this
    check pins that the refusal exists in every engine.
    """
    for module in ENGINES:
        path = os.path.join(HERE, module + ".py")
        if not os.path.exists(path):
            continue
        source = open(path, encoding="utf-8").read()
        for flag in BANNED_FLAGS:
            check("%s does not define %s" % (module, flag),
                  '"%s"' % flag not in source)
        check("%s does not define the banned --country" % module,
              '"--country"' not in source,
              "§10 bans it: it could disagree with the URL")
        check("%s refuses --locale alongside a --url naming another market"
              % module,
              "--url already carries its locale" in source,
              "the refusal that keeps --locale from contradicting the URL "
              "is missing — on this site that means a different price")


def check_undefined_names_in_every_module():
    """§10: compileall proves a file PARSES, not that its names RESOLVE.

    A live run of a sibling repo's pyppeteer engine died with NameError on a
    line reached only while fetching, after an import had been removed — the
    module imported cleanly, --help worked, compileall passed and CI was
    green. Kept COARSE (pooled bindings, no scope tracking) so it
    under-reports rather than inventing problems.
    """
    import builtins
    modules = [f for f in sorted(os.listdir(HERE))
               if f.endswith(".py") and f != "smoke_test.py"]
    for filename in modules:
        tree = ast.parse(open(os.path.join(HERE, filename), encoding="utf-8").read())
        # Module-level dunders exist without being assigned anywhere.
        defined = set(dir(builtins)) | {"__file__", "__name__", "__doc__",
                                        "__package__", "__spec__"}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    defined.add((alias.asname or alias.name).split(".")[0])
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                   ast.ClassDef)):
                defined.add(node.name)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                defined.add(node.id)
            elif isinstance(node, ast.arg):
                defined.add(node.arg)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                defined.add(node.name)
            elif isinstance(node, ast.alias) and node.asname:
                defined.add(node.asname)
        used = {n.id for n in ast.walk(tree)
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        unresolved = sorted(used - defined)
        check("%s: every name resolves" % filename, not unresolved,
              "%s" % unresolved)


def _import_graph(entrypoint):
    """Every local module an entrypoint reaches, transitively."""
    local = {f[:-3] for f in os.listdir(HERE) if f.endswith(".py")}
    seen, queue = set(), [entrypoint]
    while queue:
        name = queue.pop()
        if name in seen or name not in local:
            continue
        seen.add(name)
        tree = ast.parse(open(os.path.join(HERE, name + ".py"),
                              encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                queue.extend(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                queue.append(node.module.split(".")[0])
    return seen


def check_dockerfile_copies_everything_the_entrypoint_imports():
    """§10: all three repos in this family shipped an image that died with
    ModuleNotFoundError on every invocation, --help included, because
    proxy_pool.py was missing from the COPY list. CI never built the image;
    this check needs no Docker."""
    path = os.path.join(HERE, "Dockerfile")
    if not os.path.exists(path):
        check("Dockerfile exists", False)
        return
    dockerfile = open(path, encoding="utf-8").read()
    # Only the COPY instructions, continuations included — a comment above
    # them naming a file is not a file the image carries.
    copy_lines, joining = [], False
    for line in dockerfile.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if joining or stripped.upper().startswith("COPY "):
            copy_lines.append(stripped)
            joining = stripped.endswith("\\")
    copied = set(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\.py", " ".join(copy_lines)))
    entry = re.search(r'(?:CMD|ENTRYPOINT)\s*\[?\s*"?(?:python3?"?,\s*"?)?'
                      r'([A-Za-z_][A-Za-z0-9_]*)\.py', dockerfile)
    entrypoint = entry.group(1) if entry else "playwright_scraper"
    needed = _import_graph(entrypoint)
    missing = sorted(needed - copied)
    check("the Dockerfile COPYs every module %s.py imports" % entrypoint,
          not missing, "missing %s" % missing)
    for unwanted in ("smoke_test", "test_smoke"):
        check("the image does not carry %s.py" % unwanted,
              unwanted not in copied)


def check_env_example_documents_exactly_what_the_loader_reads():
    import env_config
    path = os.path.join(HERE, ".env.example")
    if not os.path.exists(path):
        check(".env.example exists", False)
        return
    documented = set(re.findall(r"^\s*#?\s*([A-Z][A-Z0-9_]+)\s*=", 
                                open(path, encoding="utf-8").read(), re.M))
    read = set(env_config.ENV_KEYS)
    check("every variable the loader reads is documented",
          not (read - documented), "undocumented: %s" % sorted(read - documented))
    check("every documented variable is actually read",
          not (documented - read), "unread: %s" % sorted(documented - read))


def check_a_copied_env_example_reads_as_UNSET():
    """§17: `cp .env.example .env` followed by a run must not connect.

    The placeholder check was a literal set in a sibling repo, and the two
    credentialled URLs are documented the way the vendor documents them —
    `ws://{login}-zone-…:{password}@cb.2captcha.com:9222` — so neither
    literal matched, the run connected with the string `{login}-zone-…` as
    its username, and got a 401 a long way from its cause.
    """
    import env_config
    example = os.path.join(HERE, ".env.example")
    if not os.path.exists(example):
        check(".env.example exists", False)
        return
    text = open(example, encoding="utf-8").read()
    values = dict(re.findall(r"^([A-Z][A-Z0-9_]+)=(.*)$", text, re.M))
    check("the example actually sets every variable",
          set(values) == set(env_config.ENV_KEYS),
          "example has %s, loader reads %s"
          % (sorted(values), sorted(env_config.ENV_KEYS)))
    # Every CREDENTIAL must read as unset. The default TARGET must not: it is
    # a real, usable URL, and blanking it would remove the one setting this
    # file exists to make convenient (§17's check #3 says exactly this — the
    # credentials unset, the non-credential default still usable).
    CREDENTIALS = {"TWOCAPTCHA_KEY", "ANDIESWIM_CDP_ENDPOINT", "ANDIESWIM_PROXY"}
    before = dict(os.environ)
    try:
        for name, raw in values.items():
            os.environ[name] = raw
            got = env_config.env_value(name)
            if name in CREDENTIALS:
                check("a copied .env.example leaves %s unset" % name,
                      got is None, "got %r" % got)
            else:
                check("...while %s stays a usable default" % name,
                      got == raw.strip(), "got %r" % got)
    finally:
        os.environ.clear()
        os.environ.update(before)
    # And the counter-check: a real credential must still come through, or
    # the placeholder rule would have made the loader useless. Deliberately
    # NOT 32 hex characters — that is the shape of a real 2captcha key, and
    # this repo's own credential scan (rightly) fails on one.
    try:
        os.environ["TWOCAPTCHA_KEY"] = "not-a-real-key-but-a-real-value"
        equal("a real value is still read",
              env_config.env_value("TWOCAPTCHA_KEY"),
              "not-a-real-key-but-a-real-value")
    finally:
        os.environ.clear()
        os.environ.update(before)


def check_credential_scan_is_one_implementation_invoked_from_both():
    """§17: two sources of truth, one dead and one holed.

    `.github/ci_checks.py` sat in three repos invoked by NOTHING, while
    tests.yml carried an inline grep doing a narrower version of the same job
    — one that matched only ws:// and wss://, so an http://user:pass@
    credential would have sailed past CI.
    """
    script = os.path.join(HERE, ".github", "ci_checks.py")
    check("the credential scan exists as a script", os.path.exists(script))
    if not os.path.exists(script):
        return
    workflow = os.path.join(HERE, ".github", "workflows", "tests.yml")
    if os.path.exists(workflow):
        text = open(workflow, encoding="utf-8").read()
        check("CI INVOKES the script rather than reimplementing it",
              "ci_checks.py" in text)
    result = subprocess.run([sys.executable, script, "--all"], cwd=HERE,
                            capture_output=True, text=True)
    check("the credential scan passes on this repo's own tree",
          result.returncode == 0,
          (result.stdout + result.stderr)[-600:])


BANNED_WORDING = (
    "cloud browser", "antidetect browser", "2scraper Antidetect Browser",
    "gate.2prx.com", "ANTIDETECT_LOCAL_API",
)


def check_ci_calls_the_shared_checks_rather_than_restating_them():
    """§17: one implementation, invoked from both — asserted, not assumed.

    This repo's FIRST CI run failed on exactly this. `tests.yml` carried
    INLINE reimplementations of the `--help` and sample-output checks that
    `.github/ci_checks.py` already implements. The inline sample check still
    imported `output_writer.Business` — a class this repo renamed to
    `Product` — so the job died with ImportError while `ci_checks.py` passed
    on the same tree. One copy had been updated and the other had not, and
    nothing in the repo could see the difference.

    The guard triggers on the whole `.github` directory being absent, never
    on a file inside it being missing (§22): two suites in this family run
    INSIDE the Docker image, which deliberately COPYs no `.github/`, so a
    check that reads a workflow file is correct in the repo and red in the
    image. A check that quietly starts passing once its input disappears is
    the failure mode this one is guarding against, so the escape is the
    directory, not the file.
    """
    github_dir = os.path.join(HERE, ".github")
    if not os.path.isdir(github_dir):
        skip("ci wiring", "no .github/ directory (this is the Docker image, "
                          "which deliberately carries no CI material)")
        return

    workflow = os.path.join(github_dir, "workflows", "tests.yml")
    script = os.path.join(github_dir, "ci_checks.py")
    check("ci_checks.py exists", os.path.exists(script))
    check("tests.yml exists", os.path.exists(workflow))
    if not (os.path.exists(workflow) and os.path.exists(script)):
        return

    text = open(workflow, encoding="utf-8").read()
    for flag in ("--help-check", "--sample-check", "--secret-check"):
        check("tests.yml invokes ci_checks.py %s" % flag,
              "ci_checks.py" in text and flag in text,
              "the workflow must CALL the shared check, not restate it")

    # The positive direction is not enough on its own: the workflow could
    # call the script AND still carry a stale inline copy beside it, which is
    # exactly the state that broke the first run. So assert the tell-tales of
    # a reimplementation are gone.
    # Deliberately NOT keyed on the filename. `sample_output.json` appears
    # legitimately in the docker job, which asserts the IMAGE does not carry
    # it — so a filename tell-tale fails on a correct workflow, which is its
    # own kind of check nobody can read. What actually distinguishes a
    # reimplementation is inline Python that imports the row model or
    # dataclass machinery to rebuild the expected column list.
    for tell in ("from output_writer import", "asdict("):
        check("tests.yml does not reimplement the sample check (%r)" % tell,
              tell not in text,
              "an inline copy drifts from the shared one silently")


def check_banned_wording():
    """§12: enforced by this test rather than by review."""
    for root, dirs, files in os.walk(HERE):
        dirs[:] = [d for d in dirs if d not in
                   (".git", "__pycache__", ".pytest_cache", "node_modules")]
        for filename in files:
            if not filename.endswith((".py", ".md", ".yml", ".yaml", ".txt",
                                      ".toml", ".html", ".example")):
                continue
            path = os.path.join(root, filename)
            text = open(path, encoding="utf-8", errors="replace").read().lower()
            for phrase in BANNED_WORDING:
                if phrase.lower() in text and filename != "smoke_test.py":
                    check("%s contains no %r" % (
                        os.path.relpath(path, HERE), phrase), False)
    check("banned-wording scan ran", True)


def check_concurrency_with_the_browser_stubbed():
    """§10: a live run cannot always reach this machinery.

    Page 1 is fetched alone and decides how many pages there are, so a
    blocked page 1 means the workers never start. Driven directly instead,
    with the browser replaced.
    """
    engine = _import_engine("playwright_scraper")
    if engine is None:
        return

    class Args:
        delay = 0
        retries = 1
        retry_delay = 0
        out = "unused"
        mode = "search"
        sort = "a-z"
        pages = 50

    fetched = []
    import threading
    lock = threading.Lock()

    def fake_fetch(session, args, pool, page_num, url):
        with lock:
            fetched.append(page_num)
        outcome = engine.PageOutcome(page_num=page_num, url=url)
        # Page 6 is the end of this listing: no rows, but a served page.
        outcome.products = [] if page_num >= 6 else [object()] * 15
        outcome.state = "empty" if page_num >= 6 else "content"
        return outcome

    class FakeSession:
        def __init__(self, *a, **k):
            self.pool = None
        def open(self):
            return self
        def close(self):
            pass

    class FakePlaywright:
        def __enter__(self):
            return None
        def __exit__(self, *a):
            return False

    real_fetch = engine._fetch_one_page
    real_session = engine._BrowserSession
    real_pw = engine.sync_playwright
    engine._fetch_one_page = fake_fetch
    engine._BrowserSession = FakeSession
    engine.sync_playwright = lambda: FakePlaywright()
    try:
        specs = [(n, "u%d" % n) for n in range(2, 51)]
        results, unattempted, exhausted = engine._fetch_pages_concurrently(
            Args(), None, specs, 4)
    finally:
        engine._fetch_one_page = real_fetch
        engine._BrowserSession = real_session
        engine.sync_playwright = real_pw

    check("every page fetched was fetched exactly once",
          len(fetched) == len(set(fetched)), "%r" % sorted(fetched))
    check("dispatch STOPPED at the end of the listing", exhausted)
    check("...so the 49 queued pages cost far fewer fetches",
          len(fetched) < 15, "fetched %d of 49" % len(fetched))
    check("unattempted pages are REPORTED, not counted as failed",
          len(unattempted) > 0 and all(isinstance(n, int) for n in unattempted))
    equal("attempted + unattempted covers the whole queue",
          len(set(fetched)) + len(unattempted), 49)
    equal("outcomes are restorable to page order",
          [o.page_num for o in sorted(results, key=lambda o: o.page_num)],
          sorted(o.page_num for o in results))


def check_a_dead_worker_neither_hangs_nor_loses_its_siblings():
    engine = _import_engine("playwright_scraper")
    if engine is None:
        return

    class Args:
        delay = 0
        retries = 1
        retry_delay = 0
        out = "unused"
        mode = "search"
        sort = "a-z"
        pages = 10

    def exploding_fetch(session, args, pool, page_num, url):
        if page_num == 3:
            raise RuntimeError("worker died")
        outcome = engine.PageOutcome(page_num=page_num, url=url)
        outcome.products = [object()] * 15
        outcome.state = "content"
        return outcome

    class FakeSession:
        def __init__(self, *a, **k):
            self.pool = None
        def open(self):
            return self
        def close(self):
            pass

    class FakePlaywright:
        def __enter__(self):
            return None
        def __exit__(self, *a):
            return False

    real_fetch, real_session, real_pw = (engine._fetch_one_page,
                                         engine._BrowserSession,
                                         engine.sync_playwright)
    engine._fetch_one_page = exploding_fetch
    engine._BrowserSession = FakeSession
    engine.sync_playwright = lambda: FakePlaywright()
    try:
        specs = [(n, "u%d" % n) for n in range(2, 8)]
        results, unattempted, exhausted = engine._fetch_pages_concurrently(
            Args(), None, specs, 3)
    finally:
        engine._fetch_one_page = real_fetch
        engine._BrowserSession = real_session
        engine.sync_playwright = real_pw

    check("the run returned rather than hanging", True)
    check("the dead worker's siblings still delivered their pages",
          len(results) >= 3, "%d results" % len(results))
    check("page 3 is not reported as a success",
          3 not in [o.page_num for o in results])


def check_worker_pools_start_on_different_exits():
    engine = _import_engine("playwright_scraper")
    if engine is None:
        return
    from proxy_pool import ProxyPool
    pool = ProxyPool(["http://a:1", "http://b:2", "http://c:3"], rotate="per-run")
    firsts = [engine._worker_pool(pool, i).current for i in range(3)]
    equal("three workers start on three different exits",
          len(set(firsts)), 3)
    equal("a missing pool stays missing", engine._worker_pool(None, 0), None)


def check_fingerprint_kwargs_are_ones_the_driver_accepts():
    """§10: an unknown key in new_context(**kwargs) is a TypeError at launch,
    on the PAID path, at runtime."""
    engine = _import_engine("playwright_scraper")
    if engine is None:
        return
    try:
        from fingerprint_client import playwright_context_kwargs
    except ImportError as e:
        skip("fingerprint", str(e))
        return
    sample = {"id": "x", "country": "US",
              "userAgent": "Mozilla/5.0 Chrome/140.0.0.0",
              "screen": {"width": 1920, "height": 1080},
              "timezone": "America/New_York", "language": "en-US",
              "devicePixelRatio": 2}
    kwargs = playwright_context_kwargs(sample)
    from playwright.sync_api import sync_playwright  # noqa: F401
    import playwright.sync_api as pw_api
    signature = inspect.signature(pw_api.Browser.new_context)
    unknown = [k for k in kwargs if k not in signature.parameters]
    check("every fingerprint kwarg is one new_context accepts", not unknown,
          "unknown: %s" % unknown)


def check_every_engine_exposes_the_same_public_surface():
    for module in ENGINES:
        engine = _import_engine(module)
        if engine is None:
            continue
        for name in ("scrape", "parse_args", "PageOutcome", "_fetch_one_page",
                     "_parse_for_mode", "_target_url"):
            check("%s.%s exists" % (module, name), hasattr(engine, name))
        outcome = engine.PageOutcome(page_num=1, url="u")
        for field_name in ("state", "total_available", "pages_available",
                           "sort_applied", "products", "blocked_by",
                           "load_failed", "final_url"):
            check("%s.PageOutcome carries %r" % (module, field_name),
                  hasattr(outcome, field_name))
        check("%s.PageOutcome.ok is True for a fresh outcome" % module,
              outcome.ok)
        equal("%s shares CORE_FIELDS with its twins" % module,
              tuple(engine.CORE_FIELDS),
              ("title", "url", "sku", "handle", "price"))
        equal("%s shares PRICE_COVERAGE_FLOOR with its twins" % module,
              engine.PRICE_COVERAGE_FLOOR, 95)
        equal("%s shares CORE_FIELD_FLOOR with its twins" % module,
              engine.CORE_FIELD_FLOOR, 99)


def check_engines_do_not_evaluate_a_string_in_the_browser():
    """§18: a site whose CSP omits `unsafe-eval` kills wait_for_function with
    an EvalError and takes the run down with exit 1. This store has not
    been measured for that, and the cheap habit costs nothing where it would have
    been allowed."""
    for module in ENGINES:
        path = os.path.join(HERE, module + ".py")
        if not os.path.exists(path):
            continue
        tree = ast.parse(open(path, encoding="utf-8").read())
        called = {node.func.attr for node in ast.walk(tree)
                  if isinstance(node, ast.Call)
                  and isinstance(node.func, ast.Attribute)}
        for banned in ("wait_for_function", "waitForFunction", "waitFor"):
            check("%s never CALLS %s" % (module, banned), banned not in called,
                  "poll through page_flow.wait_for_count instead")


def check_credentials_never_reach_a_log():
    """§8: an EXCEPTION MESSAGE is a log, and the masker must be GLOBAL.

    A Playwright connection error repeats the endpoint five times (the
    message plus a four-line call log), so a masker handling only the first
    occurrence prints the password four times and looks like it is working.
    """
    for module in ENGINES:
        engine = _import_engine(module)
        if engine is None:
            continue
        masked = engine._mask_credentials(
            "tried ws://u:supersecret@h1:9222 and ws://u:supersecret@h2:9222 "
            "and again ws://u:supersecret@h1:9222")
        check("%s masks EVERY occurrence" % module,
              "supersecret" not in masked, masked)
        check("%s keeps the host and port, which are the useful half" % module,
              "h1:9222" in masked and "h2:9222" in masked, masked)
    from proxy_pool import mask
    masked = mask("http://user:secret@exit.example.com:2334")
    check("proxy_pool.mask hides the password", "secret" not in masked)
    check("proxy_pool.mask keeps the exit", "exit.example.com:2334" in masked)


def check_sample_output_matches_the_schema():
    from output_writer import Product
    expected = [f.name for f in fields(Product)]
    json_path = os.path.join(HERE, "sample_output.json")
    csv_path = os.path.join(HERE, "sample_output.csv")
    if not os.path.exists(json_path):
        check("sample_output.json exists", False)
        return
    rows = json.load(open(json_path, encoding="utf-8"))
    check("sample_output.json holds rows", bool(rows))
    equal("sample_output.json keys match the schema, in order",
          list(rows[0].keys()), expected)
    check("sample_output.json is from a real run (andieswim.com rows)",
          all(r["source"] == "andieswim.com" for r in rows))
    # The sample is a SLICE, chosen for variety rather than the first N rows
    # — a sample where every row is full-price and fully in stock documents
    # one third of what the schema can say.
    check("...and the slice shows a discount", any(r.get("discount_pct") for r in rows))
    check("...and a partially-available product",
          any(0 < (r.get("variants_available") or 0) < (r.get("variants_total") or 0)
              for r in rows))
    check("...and one that is out of stock",
          any(r.get("in_stock") is False for r in rows))
    check("...and every row carries the market its price belongs to",
          all(r.get("locale") for r in rows),
          "a price with no market is a number with no units")
    check("...and a currency wherever there is a price",
          all(r.get("currency") for r in rows if r.get("price") is not None))
    check("...and carries no fabrication markers",
          not any("example" in (r.get("url") or "").lower() or
                  "lorem" in (r.get("title") or "").lower() for r in rows))
    if os.path.exists(csv_path):
        header = next(csv.reader(open(csv_path, encoding="utf-8")))
        equal("sample_output.csv header matches the schema", header, expected)


def check_readme_numbers_are_not_stale():
    """§17's check #4: diff every numeric claim against what is on disk.

    Only the figures that MUST hold are pinned. A number that legitimately
    varies between runs is written as a RANGE in the README and not checked
    here — §17 again: a number that goes stale on the next run should not be
    written as a fraction.

    The inherited version of this check pinned the SIBLING repo's claims
    (`sz=24`, `280 results across 12 pages`) and would have passed on this
    repo forever without reading a single one of its numbers — §22's "a check
    that passes for the wrong reason". Every assertion below names something
    this README actually says.
    """
    path = os.path.join(HERE, "README.md")
    if not os.path.exists(path):
        check("README.md exists", False)
        return
    readme = open(path, encoding="utf-8").read()
    import product_parser as P
    from output_writer import Product

    # Constants the README quotes by value.
    if "limit=250" in readme or "--limit 250" in readme:
        equal("the README's default limit matches PAGE_SIZE", P.PAGE_SIZE, 250)
        equal("...and the cap it calls a cap", P.MAX_PAGE_SIZE, 250)
    if "10 results" in readme or "at 10" in readme:
        equal("the README's search cap matches the parser",
              P.SEARCH_MAX_RESULTS, 10)

    # Arithmetic the README spells out. Both sums are quoted verbatim, so a
    # future edit that changes one number and not the total fails here.
    for expr in re.findall(r"(\d+(?:\s*\+\s*\d+)+)\s*=\s*(\d+)", readme):
        parts, total = expr
        equal("the README's arithmetic holds: %s = %s" % (parts, total),
              sum(int(x) for x in re.findall(r"\d+", parts)), int(total))
    check("the README states the catalogue walk", "772" in readme)
    check("...and the paged run that exercises pagination", "180" in readme)

    # The column block, which is the thing most likely to drift when a field
    # is added: every name in it must be a real field, and every real field
    # must be in it.
    block = re.search(r"```\nsource scraped_at(.*?)```", readme, re.S)
    check("the README lists the row schema", block is not None)
    if block:
        listed = ("source scraped_at" + block.group(1)).split()
        equal("the README's column list matches the schema, in order",
              listed, [f.name for f in fields(Product)])
    claimed = re.findall(r"(\d+)\s+columns", readme)
    for number in claimed:
        equal("the README's column count matches the schema",
              int(number), len(fields(Product)))

    # Claims about the sample that a reader can check by opening the file.
    sample = os.path.join(HERE, "sample_output.json")
    if os.path.exists(sample):
        rows = json.load(open(sample, encoding="utf-8"))
        check("the README says the sample is from a real run, and it is",
              "cut from a real" in readme
              and all(r["source"] == "andieswim.com" for r in rows))

    # And the one claim that must never soften: this repo does not say a
    # captcha cannot be solved (§19). The only sentence it is entitled to is
    # about what the PAGE carries.
    for forbidden in ("cannot be solved", "impossible to solve",
                      "no solver can", "unsolvable by"):
        check("the README does not claim a captcha cannot be solved (%r)"
              % (forbidden,), forbidden not in readme.lower())


_TREE_BEFORE = None


def _tree_state():
    result = subprocess.run(["git", "status", "--porcelain"], cwd=HERE,
                            capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return sorted(line for line in result.stdout.splitlines()
                  if not line.endswith(".pyc"))


def check_no_test_mutates_the_working_tree():
    """§10: one suite used its own file as a fake chromedriver and chmod'd it
    to 755, leaving a mode change in git status.

    Compares the tree against how it looked when the suite STARTED, not
    against a clean checkout — otherwise this is permanently red while
    anyone is editing, and a check that is always red teaches everyone to
    ignore checks.
    """
    if _TREE_BEFORE is None:
        skip("git status", "not a git repository")
        return
    after = _tree_state()
    changed = sorted(set(after) - set(_TREE_BEFORE))
    check("the suite itself changed nothing in the working tree",
          not changed, "%s" % changed)


def check_captcha_capability_claims_match_the_code():
    """§19: the most expensive bug this family can ship is a SENTENCE.

    It fails in both directions and this family has shipped both:

      * saying a captcha CANNOT be solved, when the true statement is that
        THIS REPO does not implement the task type. 2Captcha solves
        enterprise reCAPTCHA and Cloudflare Turnstile and has for years, so
        such a sentence tells a reader not to buy something that works.
      * saying this repo DOES solve something it builds no task type for --
        which is what the README said here: it billed the Managed Challenge
        solve to `--twocaptcha-key`, while the only thing that clears one is
        `Captcha.setAutoSolve` over `--cdp-endpoint`.

    Neither is visible to any other check: nothing fails, nothing crashes,
    and the output is correct.
    """
    readme = open(os.path.join(HERE, "README.md"), encoding="utf-8").read()
    solver = open(os.path.join(HERE, "captcha_solver.py"), encoding="utf-8").read()
    low = readme.lower()

    # Conclusions about the PRODUCT. "Unsolvable" is a property of a PAGE —
    # it means the page carries no widget — and never of a vendor. 2Captcha
    # solves enterprise reCAPTCHA and Cloudflare Turnstile and has for years,
    # so a sentence saying otherwise tells a reader not to buy something that
    # works, and nothing else in this suite can see it.
    for phrase in ("cannot be solved", "can't be solved", "neither is solvable",
                   "is not solvable", "solver is inapplicable", "no solver can",
                   "2captcha cannot", "no captcha service"):
        check("README: no %r -- write 'this repo does not implement X'" % phrase,
              phrase not in low)

    # The pairing that matters ON THIS SITE.
    #
    # The sibling bbb-scraper pins "the README must say TurnstileTaskProxyless
    # is not built here", because its site renders Cloudflare Managed Challenges and
    # a reader could reasonably expect a key to clear one. This store renders
    # no challenge on any READ path — the only captcha it ships is Shopify's
    # storefront-forms hCaptcha, bound to form submits — so the equivalent
    # hazard is the opposite one: this README's central claim is that no key
    # is needed, and a claim like that rots the moment the site switches a
    # bot manager on.
    #
    # So the claim has to be PAIRED with the thing that would retest it — the
    # daily canary — rather than left as a sentence nobody re-measures (§13).
    claims_no_key = ("no, and it would be dishonest" in low
                     or "do i need a 2captcha account" in low)
    if claims_no_key:
        check("README pairs 'no key needed' with the canary that retests it",
              "canary" in low,
              "a claim that the site is ungated goes stale silently; the "
              "daily canary is what turns it back into a measurement")
        check("...and dates the measurement it rests on",
              re.search(r"20\d\d-\d\d-\d\d", readme) is not None,
              "§13: a number describing a living thing needs its moment")

    # And in the other direction: if the README names a task type, the solver
    # had better build it. A capability claim citing no task type is a guess
    # wearing a fact's clothes; one citing a task type nobody implemented is
    # worse.
    for task in ("TurnstileTaskProxyless", "RecaptchaV2EnterpriseTaskProxyless",
                 "RecaptchaV3TaskProxyless"):
        if task.lower() in low:
            check("README names %s, so the solver must build it" % task,
                  task in solver,
                  "the README credits a task type this repo does not send")

    # Whatever the README credits with clearing the challenge must be a thing
    # the engines actually do.
    if "setautosolve" in low:
        srcs = ""
        for name in ("playwright_scraper.py", "selenium_scraper.py",
                     "puppeteer_scraper.py"):
            path = os.path.join(HERE, name)
            if os.path.exists(path):
                srcs += open(path, encoding="utf-8").read()
        check("README credits Captcha.setAutoSolve, and an engine calls it",
              "Captcha.setAutoSolve" in srcs)
def check_no_statement_is_unreachable():
    """A statement sitting after a return/raise/break/continue in the SAME
    block, which therefore can never run.

    Narrow on purpose: it makes no claim about reachability in general, only
    about a block whose control flow has already left. Measured across the
    eighteen repos of this family on 2026-09-16 it reported six problems and
    zero false positives.

    `check_undefined_names_in_every_module` cannot see this class at all, by
    design -- it pools every binding in the file rather than tracking scopes,
    so a name used inside dead code passes as long as anything else in the
    module binds it. What was hiding in that blind spot here, and in five
    sibling repos, byte for byte: a function whose `def` line had been lost,
    leaving its docstring and body absorbed into the end of the function
    above it. Present since this repo's first commit, invisible to import,
    `--help`, `compileall`, and every green run of this suite.
    """
    for filename in sorted(f for f in os.listdir(HERE) if f.endswith(".py")):
        tree = ast.parse(open(os.path.join(HERE, filename),
                              encoding="utf-8").read())
        dead = []
        for node in ast.walk(tree):
            for field in ("body", "orelse", "finalbody"):
                block = getattr(node, field, None)
                if not isinstance(block, list):
                    continue
                for i, stmt in enumerate(block[:-1]):
                    if isinstance(stmt, (ast.Return, ast.Raise,
                                         ast.Continue, ast.Break)):
                        dead.append(block[i + 1].lineno)
                        break
        check("%s: no statement the control flow can never reach" % filename,
              not dead, "first at line %d" % min(dead) if dead else "")


def check_x_debug_header_is_redacted():
    """SECURITY.md names the Scraper API's x-debug header as a place
    credentials reach a log unmasked. It was then logged verbatim.

    The fixtures are assembled from pieces rather than written out whole,
    because this file is scanned by the credential check like every other
    and a fixture that LOOKS like a live key fails it. They are the SHAPES a
    credential takes, not the literals this repo happens to contain today.
    """
    try:
        import scraper_api_client as sac
    except ImportError:
        return

    pw = "SeCr" + "EtPw"
    key = "abcdef01" * 4
    raw = ("cdpurl=ws://acct-zone-scraping_browser-pid-7:" + pw
           + "@cb.2captcha.com:9222 cost=0.00145 key=" + key + " status=200")
    out = sac._redact_debug_header(raw)
    check("x-debug: the credential and the key are gone",
                 pw not in out and key not in out)
    check("x-debug: the cost, host and status survive",
                 "cost=0.00145" in out and "cb.2captcha.com:9222" in out
                 and "status=200" in out)

    s1, s2 = "secret" + "one", "secret" + "two"
    two = sac._redact_debug_header(
        "a=http://u1:" + s1 + "@h1:1 b=http://u2:" + s2 + "@h2:2")
    check("x-debug: both credentials are masked, not just the first",
                 s1 not in two and s2 not in two)

    src = inspect.getsource(sac)
    check("x-debug: the log line calls the redactor",
                 'logger.info("x-debug: %s", _redact_debug_header(debug))' in src)



CHECKS = [v for k, v in sorted(globals().items()) if k.startswith("check_")]


def main():
    global VERBOSE
    parser = argparse.ArgumentParser(description="andieswim-scraper offline suite")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    VERBOSE = args.verbose

    global _TREE_BEFORE
    _TREE_BEFORE = _tree_state()

    for fn in CHECKS:
        if VERBOSE:
            print("\n== %s" % fn.__name__)
        try:
            fn()
        except Exception as e:  # noqa: BLE001 — a broken check is a failure
            import traceback
            FAILURES.append("%s raised %s: %s" % (fn.__name__, type(e).__name__, e))
            print("  ERROR %s raised %s: %s" % (fn.__name__, type(e).__name__, e))
            if VERBOSE:
                traceback.print_exc()

    print("\n%d checks passed, %d failed, %d group(s) skipped."
          % (PASSED, len(FAILURES), len(SKIPS)))
    for line in SKIPS:
        print("  skipped: %s" % line)
    if FAILURES:
        print("\nFailures:")
        for line in FAILURES:
            print("  - %s" % line)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
