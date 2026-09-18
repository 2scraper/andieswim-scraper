"""
page_flow.py
------------
The retry / solve / blocked decision, as DATA rather than as three copies of
an if-chain (CLAUDE.md §1).

This store answers a request six ways, and five of them want a different
response:

    one of its own JSON payloads, holding products   -> parse
    one of its own JSON payloads, holding none       -> parse; it is an ANSWER
    an HTML page built out of its own assets         -> parse
    "this route is not here" (404, or its template)  -> stop; do NOT retry
    a challenge widget                               -> solve, or rotate
    anything else                                    -> wait, then retry

Three copies of that triage across three engines would drift, and the drift
would be silent — one engine reporting exit 3 where its twin reports exit 0
on the same response.

TWO OF THOSE SIX ARE WORTH SPELLING OUT
----------------------------------------
**An empty payload is an ANSWER, not a block.** The page after the last one
of a collection answers HTTP 200 with `{"products": []}`, and so does a
collection handle that does not exist — those two are byte-identical, which
is why `empty` never means "we are sure this collection is empty". The
engines resolve it against the store's own collection index and report
`unknown_collection` rather than `empty` when the handle is absent (§20).

**`not_found` must not retry.** A mistyped handle is not going to start
existing, and three retries on a typo turn an instant, clear answer into a
slow, confusing one. It is not `blocked` either: sending a reader to hunt for
a proxy problem when they mistyped something is the failure this state exists
to prevent.

WHAT THIS SITE DOES *NOT* DO, RE-MEASURED RATHER THAN INHERITED
----------------------------------------------------------------
The repo this one was built from documents an edge that refuses a request
whose User-Agent names an HTTP client library, by killing the connection
rather than answering — so on THAT site a timeout from an HTTP client is a
block rather than a slow network. CLAUDE.md §13: a warning you inherited is
not one you measured.

Re-measured here, 2026-09-18, one URL and one address:

    no User-Agent header at all   HTTP 200
    curl/8.5.0                    HTTP 200
    python-urllib/3.11            HTTP 200
    a crawler User-Agent          HTTP 200
    an ordinary browser UA        HTTP 200
    20 requests in 4.9 s          20 x HTTP 200

So `classify_transport_error` is kept — a dead proxy and a real timeout still
want opposite responses (§8) — but there is no User-Agent denylist here and
this module carries no helper pretending otherwise.

Nothing here imports a browser, and **no JavaScript crosses this boundary**:
Selenium's `execute_script` takes a function BODY with an explicit `return`
while Playwright and pyppeteer take `() => expr`, so a shared snippet would
quietly acquire one driver's dialect. The callbacks below are named for the
OPERATION instead, and each engine spells it in its own dialect (§1).
"""

import logging
import re
from typing import Callable, Optional, Tuple
from urllib.parse import urlparse

import product_parser
from product_parser import (PAGE_SIZE, detect_bot_challenge,  # noqa: F401
                            detect_page_state, is_endpoint_url,
                            is_product_url)

log = logging.getLogger("page_flow")


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------

# How many product entries mean "this response is a listing".
#
# `> 1` on purpose, per CLAUDE.md §5: waiting for ONE match resolves on
# something unrelated long before the data is really there.
#
# But note WHAT is being counted here, because it is not what the family
# usually counts. Every route this repo fetches is a JSON endpoint that
# arrives COMPLETE with its response — there is no grid to paint, no lazy
# load, and no scroll. §8 says missing content is one of three things
# (unpainted, lazy-loaded, or a different page served to this session); on a
# JSON document it is NONE of the three, and a readiness wait on one can only
# ever burn its whole budget and then succeed or fail on the first sample.
#
# So the anchor is a property of the PAYLOAD rather than of the DOM, the wait
# collapses to a single check on the endpoint routes, and the constant exists
# for the one route that is a real page: `--mode product --dump-html`, where
# a rendered product page is captured alongside the JSON.
MIN_CARD_MATCHES = 2

# The readiness anchor for a rendered page.
#
# Only ever used on the HTML product route. `[data-oke-reviews-product-id]`
# is the store's own attribute, present once on a product page and **zero
# times** on a collection page — counted on the captures, per §18, before it
# was chosen. The obvious alternative, `.product-card`, counts 0 on the
# server-rendered collection HTML (the grid is painted later by React) and is
# therefore an anchor that never fires on the page kind it names.
READY_SELECTOR_LISTING = "[data-oke-reviews-product-id]"
READY_SELECTOR_PRODUCT = "[data-oke-reviews-product-id]"

# A JSON endpoint on this store answers in well under a second from a
# datacenter address — measured 0.44 s for the 890 KB one-pieces payload — so
# the budget here is for a bad network, not for a slow site.
CONTENT_TIMEOUT_MS = 30_000
CONTENT_TIMEOUT_MS_PRODUCT = 20_000


def ready_selector(mode: str) -> str:
    return READY_SELECTOR_PRODUCT if mode == "product" else READY_SELECTOR_LISTING


def min_matches(mode: str) -> int:
    return 1 if mode == "product" else MIN_CARD_MATCHES


def content_timeout_ms(mode: str) -> int:
    return CONTENT_TIMEOUT_MS_PRODUCT if mode == "product" else CONTENT_TIMEOUT_MS


def wait_is_meaningful(url: str) -> bool:
    """Whether waiting for content on this address can change the answer.

    False for every JSON endpoint, which is every address a normal run
    fetches. Stated as a function rather than left implicit because the
    engines must not spend `CONTENT_TIMEOUT_MS` polling a document that was
    complete when it arrived — that is 30 s per page of pure loss on a run
    that is already correct, and it would look exactly like a slow site.
    """
    return not is_endpoint_url(url)


# How long to keep polling for an anchor, and how often.
#
# Polled through `count(selector)` — a callback each engine implements with
# its own `querySelectorAll` call — and NEVER by handing the browser a string
# to evaluate. CLAUDE.md §18: a site whose Content-Security-Policy omits
# `unsafe-eval` kills `wait_for_function` with an `EvalError` and takes the
# run down with exit 1, on the site's most obvious URL. This store's own CSP
# was not measured for that, and the cheap habit costs nothing on a site that
# would have allowed it — and note the wait barely runs here anyway, since
# every routine fetch is a JSON endpoint (see `wait_is_meaningful`).
READY_POLL_MS = 500


def wait_for_count(count: Callable[[str], int], selector: str, minimum: int,
                   timeout_ms: int, sleep_ms: Callable[[int], None]) -> int:
    """Poll `count(selector)` until it reaches `minimum` or the budget runs out.

    Returns the last count seen, so a caller can report "3 of 4 expected"
    rather than only that it timed out.
    """
    waited = 0
    seen = 0
    while waited <= timeout_ms:
        seen = count(selector)
        if seen >= minimum:
            return seen
        sleep_ms(READY_POLL_MS)
        waited += READY_POLL_MS
    return seen


# ---------------------------------------------------------------------------
# The policy
# ---------------------------------------------------------------------------

def classify(html: Optional[str], status: Optional[int] = None,
             url: str = "") -> str:
    """Name what the store answered with. See product_parser.detect_page_state.

    The argument ORDER is the contract: every engine calls
    `classify(html, status, url)`. A sibling repo shipped `classify(html,
    url=...)` in two of three engines against a callee that took `status`
    second, and both crashed on their first fetch — invisible to import,
    `--help`, `compileall` and 400+ green offline assertions, because none of
    those calls a function the way a live run does (§17). `smoke_test.py`
    binds every engine's call against this signature for that reason.
    """
    return detect_page_state(html or "", status, url)[0]


def classify_with_reason(html: Optional[str], status: Optional[int] = None,
                         url: str = "") -> Tuple[str, Optional[str]]:
    """`classify`, keeping the detail — the marker or the status that decided.

    Engines log this so a red run says WHY, rather than only that it was
    red.
    """
    return detect_page_state(html or "", status, url)


# ---------------------------------------------------------------------------
# The transport-level refusal
# ---------------------------------------------------------------------------
# Exception TEXT this site's refusal arrives as, in the three libraries this
# repo can reach it through. Matched against `type(exc).__name__` and
# `str(exc)` together, because `requests` puts the useful half in the class
# name and Chromium puts it in the message.
#
# Chromium's proxy errors are listed separately below and deliberately NOT
# folded in here: §8 says a proxy failure is not a timeout and the two want
# opposite responses — a timeout deserves another try at the same exit, a
# dead proxy a different one.
_TRANSPORT_REFUSAL_RE = re.compile(
    r"stream .* was not closed cleanly"
    r"|INTERNAL_ERROR"
    r"|ERR_HTTP2_PROTOCOL_ERROR"
    r"|ERR_CONNECTION_RESET"
    r"|ERR_EMPTY_RESPONSE"
    r"|RemoteDisconnected"
    r"|Connection aborted"
    r"|ReadTimeout"
    r"|Read timed out",
    re.I)

# Chromium's own names for "the proxy is dead", which is a different fault
# with a different remedy (§8). Kept apart so the caller can rotate rather
# than retry.
_PROXY_FAILURE_RE = re.compile(
    r"ERR_PROXY_CONNECTION_FAILED"
    r"|ERR_TUNNEL_CONNECTION_FAILED"
    r"|ERR_PROXY_AUTH_(?:UNSUPPORTED|REQUESTED)"
    r"|ERR_UNEXPECTED_PROXY_AUTH",
    re.I)


def classify_transport_error(exc: BaseException) -> str:
    """Name a fetch that raised instead of answering.

    Returns one of:

        "proxy"      the exit is dead          -> rotate, do not retry here
        "refused"    the edge hung up          -> see below
        "error"      anything else             -> ordinary retry

    "refused" is kept but, on THIS store, means what it says on the tin: a
    connection that died. There is no User-Agent denylist here — re-measured
    2026-09-18, HTTP 200 with no User-Agent header at all and with every
    client-library UA tried — so unlike the repo this code came from, a reset
    here really is a network fault and an ordinary retry is the right
    response. The distinction that still matters is "proxy": a dead exit
    wants a rotation, not a retry (§8).

    This deliberately over-classifies a genuine slow network as "refused".
    That is the safer direction: the remedy printed for "refused" (send a
    browser UA, then rotate the exit) is harmless advice on a slow network,
    whereas silently retrying a refusal forever is a run that never ends and
    never says why.
    """
    text = f"{type(exc).__name__}: {exc}"
    if _PROXY_FAILURE_RE.search(text):
        return "proxy"
    if _TRANSPORT_REFUSAL_RE.search(text):
        return "refused"
    return "error"


# NO User-Agent denylist here, and the ABSENCE is a measurement.
#
# The repo this one was built from carries a `ua_will_be_refused()` helper,
# because THAT site's edge kills the connection on a request whose
# User-Agent names an HTTP client library. Re-measured on this store,
# 2026-09-18, one URL and one address: HTTP 200 with no User-Agent header at
# all, with `curl/8.5.0`, with `python-urllib/3.11`, with a crawler UA and
# with an ordinary browser UA. Twenty rapid requests: twenty 200s.
#
# So the helper was deleted rather than copied. It also had no consumer
# outside its own module (§17: grep every public name for one), which makes
# it the exact pair of defects CLAUDE.md warns about — dead code whose
# comment reads like enforcement, carrying a claim inherited rather than
# measured (§13, §16).


# How many product links a SERVED page must carry before "we parsed nothing"
# is reported as OUR failure rather than as an empty category (§20).
#
# Two rather than one: a single stray product link can appear in a nav
# flyout or a "recently viewed" strip on a page that genuinely lists no
# products, and calling that a parser failure would cry wolf on a correct
# answer. A real grid links to far more than two.
PARSE_FAILURE_MIN_LINKS = 2


def looks_like_a_parse_failure(state: str, rows: int, link_count: int) -> bool:
    """True when the page was SERVED, links to products, and parsed to zero.

    That combination is this repo's bug, not the site's, and it deserves to
    say so by name — "0 products" sends the reader to check the URL when the
    thing to check is the parser. Deliberately NOT a new exit code: the
    catalogue question really was answered, so it stays EXIT_NO_PRODUCTS and
    only the `stop_reason` differs (§20).
    """
    if rows:
        return False
    if state not in ("content", "empty"):
        return False
    return link_count >= PARSE_FAILURE_MIN_LINKS


STATE_POLICY = {
    # A page with the site's own structured data on it.
    "content":   {"retry": False, "solve": False, "blocked": False, "parse": True},
    # A listing payload the store served that holds no products — the page
    # after the last one, or a genuinely empty collection. The site answered
    # exactly what was asked. EXIT_NO_PRODUCTS rather than EXIT_BLOCKED:
    # reporting it as blocked sends a user hunting for a proxy problem that
    # is not there.
    #
    # It is ALSO what a misspelt collection handle produces, byte for byte —
    # `/collections/does-not-exist/products.json` answers HTTP 200 with
    # `{"products": []}` rather than 404. That distinction cannot be made
    # from the document, so it is not made here: the engines check the handle
    # against the collection index and report `unknown_collection` instead of
    # `empty` when it is absent (§20).
    "empty":     {"retry": False, "solve": False, "blocked": False, "parse": True},
    # A refusal with no challenge on it. There is nothing to solve — the edge
    # is not offering a test, it is declining — so the only move is a
    # different exit. Paying a solver here would buy nothing, which is why
    # `solve` is False on a state whose name says blocked.
    "blocked":   {"retry": True,  "solve": False, "blocked": True,  "parse": False},
    # A challenge widget. This one IS a test, and it is the state that pays
    # for a solver. A fresh browser from a different exit clears it too,
    # which is why `retry` is also True.
    "captcha":   {"retry": True,  "solve": True,  "blocked": True,  "parse": False},
    # Not recognisably a page or payload this store serves. A wait, not a
    # spend.
    "unknown":   {"retry": True,  "solve": False, "blocked": False, "parse": False},
    # The store answered "this route is not here" — a 404 page, or a 404 with
    # a zero-byte body on a JSON route. RETRYING IS WRONG: the address is
    # not going to start existing, and three retries on a typo turn an
    # instant, clear answer into a slow, confusing one. Not blocked either,
    # for the same reason as `empty`: sending a reader to hunt for a proxy
    # problem when they mistyped a handle is the failure this state exists to
    # prevent.
    "not_found": {"retry": False, "solve": False, "blocked": False, "parse": False},
}


def should_retry(state: str) -> bool:
    return STATE_POLICY.get(state, STATE_POLICY["unknown"])["retry"]


def should_solve(state: str) -> bool:
    return STATE_POLICY.get(state, STATE_POLICY["unknown"])["solve"]


def counts_as_blocked(state: str) -> bool:
    return STATE_POLICY.get(state, STATE_POLICY["unknown"])["blocked"]


def should_parse(state: str) -> bool:
    return STATE_POLICY.get(state, STATE_POLICY["unknown"])["parse"]


# Whether a blocked page is worth re-fetching at all.
#
# True here, and CONSULTED rather than merely documented — the engines read
# it, so setting it False really does stop the retry loop. (A sibling repo
# carried this constant with a paragraph of justification and no reader,
# which is the same defect as dead code that looks load-bearing: §17.)
#
# True, though it has never had occasion to fire on this store: nothing here
# has ever answered `blocked`. It stays True because IF that changes, a
# re-fetch is the cheap thing to try first — a rotation moves the address and
# a fresh browser re-rolls the headers — and a False here would have to be a
# decision rather than an oversight.
RETRY_ON_BLOCKED = True

# How many times to re-fetch a blocked page when there is no proxy pool to
# rotate into.
#
# One, and only one: without a pool every retry leaves from the same address
# with the same headers, which is the pair the edge decided on. A second
# attempt is a second identical refusal. WITH a pool, the engines retry once
# per remaining exit instead, because there the retry changes the one
# variable the refusal depends on.
BLOCK_RETRIES_WITHOUT_POOL = 1

# At most one solve per page. A challenge that survives a solved token is not
# a challenge this run can pass, and a second solve is a second charge for
# the same answer.
SOLVES_PER_PAGE = 1


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

def pagination_is_addressable(url: str) -> bool:
    """Whether page N of this listing can be fetched without walking to it.

    This is the question CLAUDE.md §18 says to ask PER URL rather than per
    site, because a sibling repo has one page kind that paginates by address
    and one that does not — and a `page_url()` used unconditionally there
    reported a COMPLETE run holding page 1.

On this store the two listing kinds answer DIFFERENTLY, which is exactly
    why the question is asked per URL (measured 2026-09-18):

        /collections/{h}/products.json?limit=250&page=N
            -> a different slice each time. Walking the whole catalogue gave
               250 + 250 + 250 + 22 = 772 distinct handles, no repeats,
               page 5 empty.
        /search/suggest.json?q=…
            -> ONE response. Shopify caps predictive search at 10 results
               per type and publishes no page 2 at all.

    A PRODUCT is one document and not paginated either, so both of those
    return False and the engines fetch them alone.
    """
    parsed = urlparse(url or "")
    if not (parsed.scheme and parsed.netloc):
        return False
    return product_parser.pagination_is_addressable(url)


def pages_to_plan(pages_requested: int, pages_avail: Optional[int]) -> int:
    """How many pages a run may ask for, given what page 1 reported.

This store publishes no usable total (see `plan_from_total` for the count it
    DOES publish and why it is not used), so `pages_avail` arrives None on
    every normal run and the request stands unclamped.

    There is no site-imposed ceiling either — unlike bbb-scraper, where the
    same function has to cap at 15 pages of a 19,016-result search. A
    `--pages 50` here is limited only by what the collection holds, and
    walking off the end is FREE: page 5 of a 4-page collection answers HTTP
    200 with an empty array rather than the 500 that site returns, so an
    overshoot costs one request and manufactures no error.
    """
    requested = max(1, int(pages_requested))
    if not pages_avail:
        return requested
    return max(1, min(requested, int(pages_avail)))


def plan_from_total(pages_requested: int, total: Optional[int],
                    page_size: int = PAGE_SIZE) -> int:
    """`pages_to_plan`, taking a result COUNT rather than a page count.

    Kept, and deliberately never given the one count this site publishes.

    `/collections.json` reports a `products_count` per collection, and it is
    NOT a count of products the storefront will serve: 472 against 180 served
    for `one-pieces`, 3089 against 322 for `all-swimwear`, against a
    whole-store total of 772 published products. Planning from it would clamp
    nothing and would make every run look short of a target it was never
    going to reach — CLAUDE.md §13's rotted number, except the number was
    never right rather than merely stale.

    So the run discovers its own end from the data instead (§7 layer 3): a
    page that returns no products, or adds no new id, is the last one. That
    costs exactly one extra request per run and cannot be wrong.
    """
    return pages_to_plan(pages_requested,
                         (None if total is None
                          else max(1, -(-int(total) // max(1, page_size)))))


def concurrency_limit(cdp_endpoint: Optional[str]) -> Optional[int]:
    """1 when workers would collide, else None for "no limit imposed here".

    The Scraping Browser API allows ONE live connection per profile, so N
    workers sharing a `pid` collide with `profile_locked`. Several `pid`s,
    one run each, is the way to parallelise that path (§7).
    """
    return 1 if cdp_endpoint else None
