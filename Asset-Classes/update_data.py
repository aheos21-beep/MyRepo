#!/usr/bin/env python3
"""
Refresh Asset-Classes/data.json. Run by
.github/workflows/monthly-asset-refresh.yml.

Requires ANTHROPIC_API_KEY (for the six searched rows) and EIA_API_KEY (for
the two energy rows). See ASSET-SOURCES.md for why each asset is here.

Design, and the reasoning behind it:

1. One horizon, one number. A single 1-year figure per asset. The previous
   build carried three years and compounded them, which produced the worst bug
   it ever had (a correct ~1,400% three-year total rendered as +77,248%).
   Nothing here multiplies two forecasts together.

2. Fetched beats searched. Eleven of seventeen rows come from an API or a
   published holdings file, so they cost nothing and return the same answer
   every run. Only six rows involve a language model at all.

3. Every row names its publisher. No medians of anonymous sell-side views —
   that mechanism is what made the old build swing 8-45pp between identical
   runs. If an institution cannot be named, the asset is not on the list.

4. The model never does arithmetic and never picks a number. For the six
   searched rows it reports what a named document says; Python derives the
   percentage.

5. An asset class is defined by a benchmark you could buy. Equity sleeves are
   computed over a benchmark ETF's actual holdings and weights:
   sum(w_i * ((target_i / price_i - 1) + yield_i)). The ETF is not the
   forecast — the analyst targets are. The ETF settles which names, at what
   weight, so that choice belongs to the fund provider rather than to us.

6. A 200 is not evidence the right fund was fetched. iShares returns a
   well-formed CSV for a wrong product id: id 239500 was requested as IDV and
   served DVY, with nothing in the response signalling an error. So identity
   is asserted, not inferred — via the fund name inside the file (US funds) or
   the ticker in the download URL (Canadian files, which carry no name line).

7. Columns are read by name, never by position. The same provider uses
   'Shares' for one fund and 'Quantity' for another, and IDV carries an extra
   'Type' column that shifts everything after it.

8. Publisher cadence, not fetch cadence. CREA publishes quarterly and the
   World Bank twice a year; asking them monthly buys nothing and costs money.
   Searched rows are skipped until their next publication is due, and every
   row carries the date its publisher last published rather than the date we
   happened to fetch it.

9. Failures stale, they do not guess. A row that cannot be refreshed keeps its
   previous value, is listed in data["staleAssetIds"], and says so in the UI.
"""
import argparse
import csv
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

DATA_PATH = Path(__file__).parent / "data.json"
HISTORY_PATH = Path(__file__).parent / "history.json"
MAX_HISTORY_MONTHS = 12

HTTP_TIMEOUT = 60
USER_AGENT = "asset-classes-dashboard/2.0"

# Pricing per token, from https://platform.claude.com/docs/en/about-claude/pricing
PRICING_MODEL_FAMILY = "claude-haiku-4-5"
PRICE_PER_INPUT_TOKEN = 1.00 / 1_000_000
PRICE_PER_OUTPUT_TOKEN = 5.00 / 1_000_000
PRICE_PER_CACHE_WRITE_TOKEN = 1.25 / 1_000_000
PRICE_PER_CACHE_READ_TOKEN = 0.10 / 1_000_000
PRICE_PER_SEARCH = 10.00 / 1_000

# A search-heavy turn legitimately pauses mid-work and must be handed back to
# resume. This is not a retry and it earns its keep.
MAX_PAUSE_CONTINUATIONS = 4

# One attempt, deliberately. A whole-request retry only fires on "ended without
# calling the tool" — a transient API failure raises instead and never reaches
# it. The first live run showed that condition is deterministic, not random:
# CBRE ended its turn twice identically because the tool had no way to express
# "this document has no figure", and the second attempt re-ran every web search
# to reach the same place. A failed group now stales and can be re-run
# deliberately with --repair-stale, rather than every run paying double on the
# way down.
REQUEST_ATTEMPTS = 1

# Content farms publish confident numbers with no analyst behind them and are
# indistinguishable from research once they are in context.
BLOCKED_SOURCE_DOMAINS = [
    "longforecast.com", "coinpriceforecast.com", "walletinvestor.com",
    "gov.capital", "pricepredictions.com", "digitalcoinprice.com",
    "coincodex.com", "30rates.com", "traders-union.com", "cryptopolitan.com",
]

# A 1-year forecast outside this band is a unit or scale error, not a bullish
# analyst. Deliberately wide: real commodity years do reach +/-50%.
RETURN_SANITY_BOUNDS = (-90.0, 200.0)
# A forecast level this far from today's level is a unit mismatch (one run
# averaged "$16/kg" with "$15,646/tonne" and produced +12,074%).
PRICE_SCALE_RATIO = 5.0

# Below this share of a fund, a top-10 stands in for too little of the sleeve:
# renormalising reweights it onto its largest names. Set by XLK, the lowest
# sleeve that still ships, at 59%: a cap-weighted tech fund genuinely is its
# top names. The Canadian sector sleeves sit at 79-89%. Anything under this
# uses a full holdings file instead.
MIN_SLEEVE_COVERAGE = 0.55
# A sleeve whose holdings mostly lack analyst targets is not a consensus.
MIN_SLEEVE_TARGET_COVERAGE = 0.60

# Each holding's expected return is clipped into this weighted percentile band
# before weighting, so one bad quote cannot carry a sleeve. Symmetric by
# design — see winsorize().
WINSOR_TAIL = 0.05
# Percentile clipping needs a tail to clip. With ten holdings the 5th
# percentile IS the minimum and winsorizing is a no-op, so it only runs on the
# full-holdings sleeves (~100 names). The top-10 sleeves are protected by
# HOLDING_RETURN_BOUNDS instead, which does not depend on sample size.
MIN_WINSOR_HOLDINGS = 25

# A single stock whose mean analyst target implies a move outside this band
# over twelve months is a stale quote, a corporate action or a mis-scaled
# figure — not a forecast. Such holdings are dropped like a missing target,
# so the coverage check notices if too many go. Deliberately wide and
# symmetric: this removes errors, not opinions.
HOLDING_RETURN_BOUNDS = (-60.0, 120.0)


# ---------------------------------------------------------------------------
# The asset list. See ASSET-SOURCES.md.
# ---------------------------------------------------------------------------

# method="ishares"  : full holdings CSV from an iShares product page
# method="yf_top"   : yfinance top-10 holdings, renormalised
# method="eia"      : EIA STEO series
# method="boc"      : Bank of Canada Valet
# method="search"   : one named publisher, via web search
ASSETS = [
    # --- Fetched: cash ---
    dict(id="hisa", name="HISA (Canada)", cat="Cash", color="#3fb950",
         method="boc", publisher="Bank of Canada"),

    # --- Fetched: equity sleeves, full holdings file ---
    dict(id="cad-div", name="CAD Dividend Stocks", cat="Equity", color="#58a6ff",
         method="ishares", ticker="CDZ",
         url="https://www.blackrock.com/ca/investors/en/products/239834/ishares-sptsx-canadian-dividend-aristocrats-index-fund",
         expect="Dividend Aristocrats", publisher="Analyst consensus via CDZ holdings"),
    dict(id="us-div", name="US Dividend Stocks", cat="Equity", color="#79c0ff",
         method="ishares", ticker="DVY",
         url="https://www.ishares.com/us/products/239500/ishares-select-dividend-etf",
         expect="Select Dividend", publisher="Analyst consensus via DVY holdings"),
    dict(id="intl-div", name="Intl Dividend Stocks", cat="Equity", color="#a5d6ff",
         method="ishares", ticker="IDV",
         url="https://www.ishares.com/us/products/239499/ishares-international-select-dividend-etf",
         expect="International Select Dividend", publisher="Analyst consensus via IDV holdings"),

    # --- Fetched: equity sleeves, yfinance top-10 (all measured 79-89% cover) ---
    dict(id="cad-reit", name="Canadian REITs", cat="Equity", color="#d2a8ff",
         method="yf_top", ticker="XRE.TO", publisher="Analyst consensus via XRE holdings"),
    dict(id="us-tech", name="US Tech", cat="Equity", color="#a371f7",
         method="yf_top", ticker="XLK", publisher="Analyst consensus via XLK holdings"),
    dict(id="cad-energy", name="Canadian Energy", cat="Equity", color="#ffa657",
         method="yf_top", ticker="XEG.TO", publisher="Analyst consensus via XEG holdings"),
    dict(id="cad-fin", name="Canadian Financials", cat="Equity", color="#7ee787",
         method="yf_top", ticker="XFN.TO", publisher="Analyst consensus via XFN holdings"),
    dict(id="cad-util", name="Canadian Utilities", cat="Equity", color="#56d364",
         method="yf_top", ticker="ZUT.TO", publisher="Analyst consensus via ZUT holdings"),

    # --- Fetched: energy ---
    dict(id="oil", name="WTI Crude Oil", cat="Commodity", color="#f0883e",
         method="eia", series="WTIPUUS", publisher="EIA Short-Term Energy Outlook"),
    dict(id="natgas", name="Natural Gas", cat="Commodity", color="#ffa198",
         method="eia", series="NGHHUUS", publisher="EIA Short-Term Energy Outlook"),

    # --- Searched: one named authority each ---
    dict(id="cad-re", name="Canadian Real Estate", cat="Real Estate", color="#f778ba",
         method="search", group="crea", publisher="CREA",
         cadence_months=3,
         hint="Canadian Real Estate Association (CREA) quarterly housing market forecast, "
              "national average home price forecast for next year"),
    dict(id="us-re", name="US Real Estate", cat="Real Estate", color="#db61a2",
         method="search", group="cbre", publisher="CBRE",
         cadence_months=6,
         hint="CBRE US Real Estate Market Outlook, commercial property value / total return forecast"),
    dict(id="potash", name="Potash", cat="Commodity", color="#e3b341",
         method="search", group="cmo", publisher="World Bank CMO",
         cadence_months=6,
         hint="World Bank Commodity Markets Outlook potash price forecast, USD per tonne"),
    dict(id="copper", name="Copper", cat="Commodity", color="#ec8e2c",
         method="search", group="cmo", publisher="World Bank CMO",
         cadence_months=6,
         hint="World Bank Commodity Markets Outlook copper price forecast, USD per tonne"),
    dict(id="aluminium", name="Aluminium", cat="Commodity", color="#bfc7d5",
         method="search", group="cmo", publisher="World Bank CMO",
         cadence_months=6,
         hint="World Bank Commodity Markets Outlook aluminum price forecast, USD per tonne"),
    dict(id="nickel", name="Nickel", cat="Commodity", color="#9db1c5",
         method="search", group="cmo", publisher="World Bank CMO",
         cadence_months=6,
         hint="World Bank Commodity Markets Outlook nickel price forecast, USD per tonne"),
]

SEARCH_GROUPS = {
    "crea": "CREA quarterly housing market forecast",
    "cbre": "CBRE US real estate market outlook",
    "cmo": "World Bank Commodity Markets Outlook",
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def http_get(url, timeout=HTTP_TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def load_json(path, default):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default


def write_json(path, payload):
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")


def months_between(earlier, later):
    return (later.year - earlier.year) * 12 + (later.month - earlier.month)


def check_return(pct, label):
    """Reject a return that is outside anything a real 1-year forecast reaches.

    This is a unit/scale guard, not a view on the market. It catches a price
    compared against a rate, or a per-tonne figure compared against per-pound.
    """
    lo, hi = RETURN_SANITY_BOUNDS
    if not isinstance(pct, (int, float)) or pct != pct:
        raise ValueError(f"{label}: return is not a number ({pct!r})")
    if not lo <= pct <= hi:
        raise ValueError(f"{label}: {pct:.1f}% is outside {RETURN_SANITY_BOUNDS}; unit or scale error")
    return round(float(pct), 1)


# ---------------------------------------------------------------------------
# Fetch: Bank of Canada (HISA)
# ---------------------------------------------------------------------------

# Candidates in preference order. The 1-year Government of Canada yield is the
# market's own expectation for one year of cash, which is what a HISA tracks.
# Valet series naming has changed over the years, so several are tried and the
# one that answers is recorded — guessing a single id and failing silently is
# how a row goes stale without anyone noticing.
BOC_SERIES_CANDIDATES = [
    ("V80691345", "1-year Government of Canada treasury bill yield"),
    ("BD.CDN.1YR.DQ.YLD", "1-year Government of Canada benchmark bond yield"),
    ("V122558", "1-year Government of Canada benchmark bond yield"),
    ("V80691342", "3-month Government of Canada treasury bill yield"),
]


def fetch_boc_rate():
    """Return (rate_pct, description, observation_date) from the BoC Valet API."""
    errors = []
    for series, description in BOC_SERIES_CANDIDATES:
        url = f"https://www.bankofcanada.ca/valet/observations/{series}/json?recent=1"
        try:
            payload = json.loads(http_get(url, timeout=30))
            obs = payload.get("observations") or []
            if not obs:
                errors.append(f"{series}: no observations")
                continue
            row = obs[-1]
            value = row.get(series, {}).get("v")
            if value in (None, ""):
                errors.append(f"{series}: empty value")
                continue
            print(f"    BoC series {series} -> {value}% on {row['d']}")
            return float(value), description, row["d"]
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as e:
            errors.append(f"{series}: {type(e).__name__}")
    raise ValueError(f"no Bank of Canada series answered ({'; '.join(errors)})")


def hisa_projection():
    rate, description, observed = fetch_boc_rate()
    # A HISA is cash: the rate IS the one-year return. There is no capital
    # appreciation to add, and treating the rate as a price level is what once
    # printed 39.5% for a savings account.
    pct = check_return(rate, "hisa")
    why = (f"{description} is {rate:.2f}% as of {observed} (Bank of Canada Valet API). "
           f"For cash the prevailing rate is the one-year return.")
    return dict(r=pct, why=why, published=observed, basis=f"{rate:.2f}%")


# ---------------------------------------------------------------------------
# Fetch: EIA STEO (oil, natural gas)
# ---------------------------------------------------------------------------

def fetch_eia_series(series, api_key):
    """Return the STEO monthly series as an ordered list of (period, value)."""
    params = urllib.parse.urlencode({
        "api_key": api_key,
        "frequency": "monthly",
        "data[0]": "value",
        "facets[seriesId][]": series,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 40,
    }, safe="[]")
    payload = json.loads(http_get(f"https://api.eia.gov/v2/steo/data/?{params}"))
    rows = payload.get("response", {}).get("data") or []
    points = [(r["period"], float(r["value"])) for r in rows if r.get("value") is not None]
    if not points:
        raise ValueError(f"EIA returned no values for {series}")
    points.sort(key=lambda p: p[0])
    return points, (rows[0].get("seriesDescription") or series), (rows[0].get("unit") or "")


def eia_projection(asset, api_key, today):
    """One year out versus the most recent actual month.

    STEO runs ~18 months forward, so a 12-month-ahead point exists rather than
    needing extrapolation. Anchoring to the current month (not to the far end)
    is what keeps this a 1-year figure.
    """
    points, description, unit = fetch_eia_series(asset["series"], api_key)
    by_period = dict(points)

    current_key = today.strftime("%Y-%m")
    # The current month may not be published yet; walk back to the latest that is.
    anchor = next((p for p in reversed([k for k, _ in points]) if p <= current_key), None)
    if anchor is None:
        raise ValueError(f"{asset['id']}: no STEO period at or before {current_key}")

    year, month = int(anchor[:4]), int(anchor[5:])
    target_key = f"{year + 1:04d}-{month:02d}"
    if target_key not in by_period:
        raise ValueError(f"{asset['id']}: STEO has no {target_key} (horizon ends {points[-1][0]})")

    base, target = by_period[anchor], by_period[target_key]
    if base <= 0 or target <= 0:
        raise ValueError(f"{asset['id']}: non-positive prices base={base} target={target}")
    if not (1 / PRICE_SCALE_RATIO <= target / base <= PRICE_SCALE_RATIO):
        raise ValueError(f"{asset['id']}: {base} -> {target} is off-scale; unit change?")

    pct = check_return((target / base - 1) * 100, asset["id"])
    why = (f"EIA Short-Term Energy Outlook projects {description} at {target:,.2f} {unit} "
           f"in {target_key}, against {base:,.2f} in {anchor}.")
    return dict(r=pct, why=why, published=anchor, basis=f"{base:,.2f} {unit}")


# ---------------------------------------------------------------------------
# Fetch: equity sleeves
# ---------------------------------------------------------------------------

def _find_header_row(rows):
    """iShares files carry a preamble before the real header."""
    for i, row in enumerate(rows):
        if row and row[0].strip().lower() == "ticker":
            return i
    raise ValueError("no 'Ticker' header row found in holdings file")


def fetch_ishares_holdings(asset):
    """Return (holdings, as_of) from an iShares product page.

    Columns are read by NAME: the same provider uses 'Shares' for CDZ and
    'Quantity' for DVY/IDV, and IDV inserts a 'Type' column that shifts every
    position after it.
    """
    page = http_get(asset["url"])
    links = set(re.findall(r'href="([^"]+)"', page))
    candidates = [h for h in links if re.search(r"(fileType=csv|latest-holdings\.csv)", h, re.I)]
    if not candidates:
        raise ValueError(f"{asset['id']}: no holdings CSV link on {asset['url']}")

    url = sorted(candidates, key=len)[0]
    if not url.startswith("http"):
        url = urllib.parse.urljoin(asset["url"], url)
    text = http_get(url)

    # A wrong product id returns 200 with a valid CSV for a different fund, so
    # identity is asserted rather than inferred from a 200. The US files name
    # the fund on their first line; the Canadian ones do not, and carry the
    # ticker in the download URL instead (fileName=CDZ_holdings). Either proves
    # identity; neither being present does not.
    head = text[:400]
    named = asset["expect"].lower() in head.lower()
    in_url = re.search(rf"\b{re.escape(asset['ticker'])}[_-]?holdings\b", url, re.I) is not None
    if not (named or in_url):
        raise ValueError(
            f"{asset['id']}: cannot confirm this is {asset['ticker']} — neither "
            f"{asset['expect']!r} in the file nor {asset['ticker']} in the download URL. "
            f"File begins {head.splitlines()[0][:80]!r}, url {url[:110]!r}"
        )

    as_of = None
    m = re.search(r"Fund Holdings as of,\"?([^\"\n]+)", text)
    if m:
        try:
            as_of = datetime.strptime(m.group(1).strip(), "%b %d, %Y").date().isoformat()
        except ValueError:
            as_of = None

    rows = list(csv.reader(io.StringIO(text)))
    start = _find_header_row(rows)
    header = [c.strip() for c in rows[start]]
    idx = {name: i for i, name in enumerate(header)}
    for required in ("Ticker", "Weight (%)"):
        if required not in idx:
            raise ValueError(f"{asset['id']}: holdings file has no {required!r} column; saw {header}")

    holdings = []
    for row in rows[start + 1:]:
        if len(row) <= idx["Weight (%)"]:
            continue
        ticker = row[idx["Ticker"]].strip()
        asset_class = row[idx["Asset Class"]].strip() if "Asset Class" in idx else "Equity"
        if not ticker or ticker == "-" or asset_class.lower() != "equity":
            continue
        try:
            weight = float(row[idx["Weight (%)"]].replace(",", ""))
        except ValueError:
            continue
        if weight > 0:
            exchange = row[idx["Exchange"]].strip() if "Exchange" in idx else ""
            holdings.append({
                "ticker": ticker, "weight": weight, "exchange": exchange,
                # A provider file lists a local ticker; it must be mapped.
                "symbol": yahoo_symbol(ticker, exchange, asset.get("ticker", "")),
            })

    if not holdings:
        raise ValueError(f"{asset['id']}: holdings file parsed to zero equity rows")
    print(f"    {asset['ticker']}: {len(holdings)} holdings, {sum(h['weight'] for h in holdings):.1f}% of fund"
          + (f", as of {as_of}" if as_of else ""))
    return holdings, as_of


def fetch_yf_top_holdings(asset):
    """Return (holdings, None) from yfinance's top-10 for a fund."""
    import yfinance as yf

    top = yf.Ticker(asset["ticker"]).funds_data.top_holdings
    if top is None or len(top) == 0:
        raise ValueError(f"{asset['id']}: yfinance returned no holdings for {asset['ticker']}")

    weight_col = top.columns[-1]
    # yfinance already returns Yahoo symbols, suffixes and all ('BMO.TO', 'RY').
    # Rewriting them turned 'BMO.TO' into 'BMO-TO.TO' and cost four sleeves
    # every one of their analyst targets, so they are passed through untouched.
    holdings = [{"ticker": str(sym), "weight": float(row[weight_col]) * 100.0,
                 "exchange": "", "symbol": str(sym)}
                for sym, row in top.iterrows() if float(row[weight_col]) > 0]
    covered = sum(h["weight"] for h in holdings) / 100.0
    if covered < MIN_SLEEVE_COVERAGE:
        raise ValueError(
            f"{asset['id']}: top-{len(holdings)} covers only {covered:.1%} of {asset['ticker']}; "
            f"renormalising that would reweight the sleeve onto its largest names"
        )
    print(f"    {asset['ticker']}: top-{len(holdings)} covers {covered:.1%} of fund")
    return holdings, None


# iShares lists foreign holdings by local ticker and exchange; Yahoo wants a
# suffix. Only the exchanges these three funds actually hold are mapped.
EXCHANGE_SUFFIX = {
    "toronto stock exchange": ".TO", "tsx venture exchange": ".V",
    "london stock exchange": ".L", "euronext paris": ".PA",
    "euronext amsterdam": ".AS", "euronext brussels": ".BR",
    "xetra": ".DE", "deutsche boerse ag": ".DE", "six swiss exchange": ".SW",
    "borsa italiana": ".MI", "bolsa de madrid": ".MC", "tokyo stock exchange": ".T",
    "asx - all markets": ".AX", "australian securities exchange": ".AX",
    "hong kong exchanges and clearing ltd": ".HK",
    "singapore exchange": ".SI", "nasdaq omx stockholm": ".ST",
    "oslo bors asa": ".OL", "nasdaq omx helsinki": ".HE",
    "nasdaq omx copenhagen": ".CO", "bolsa mexicana de valores": ".MX",
    "new zealand exchange": ".NZ",
}


def yahoo_symbol(ticker, exchange, fund_ticker):
    """Map a provider file's local ticker + exchange onto a Yahoo symbol.

    Only for provider files. Symbols that already come from Yahoo must not be
    passed through here — they are already correct, and re-suffixing them
    produces 'BMO-TO.TO'.
    """
    base = ticker.replace(".", "-").strip()
    suffix = EXCHANGE_SUFFIX.get((exchange or "").strip().lower(), "")
    if not suffix and fund_ticker.endswith(".TO"):
        suffix = ".TO"
    return base + suffix


def weighted_quantile(pairs, q):
    """Quantile of (weight, value) pairs, weighted.

    The point estimate is weight-weighted, so the range around it must be too.
    An unweighted range describes a different basket than the number it sits
    next to, and can in principle sit entirely to one side of it.
    """
    ordered = sorted(pairs, key=lambda p: p[1])
    total = sum(w for w, _ in ordered)
    if total <= 0:
        return None
    cum = 0.0
    for w, value in ordered:
        cum += w
        if cum >= q * total:
            return value
    return ordered[-1][1]


def winsorize(pairs, tail=WINSOR_TAIL):
    """Clip values into the weighted [tail, 1-tail] band, keeping weights.

    An outlier guard, not a view. A stale quote, a mis-scaled target or a name
    mid-takeover can otherwise let one holding carry a sleeve. Clipping is
    symmetric on purpose: trimming only the top would quietly redefine the
    asset class as its less-favoured half, which is a thumb on the scale
    dressed up as prudence.
    """
    lo = weighted_quantile(pairs, tail)
    hi = weighted_quantile(pairs, 1 - tail)
    if lo is None or hi is None or lo > hi:
        return pairs, 0
    clipped = [(w, min(max(v, lo), hi)) for w, v in pairs]
    n_clipped = sum(1 for (_, v), (_, c) in zip(pairs, clipped) if v != c)
    return clipped, n_clipped


def equity_sleeve_projection(asset, holdings, as_of, today):
    """Weighted expected return over a benchmark's holdings.

    sum(w_i * ((target_i / price_i - 1) + yield_i)), renormalised over the
    holdings that actually carry an analyst target. Holdings without one are
    dropped rather than substituted — an invented target is worse than a
    smaller sample.
    """
    import yfinance as yf

    contributions, used_weight, total_weight = [], 0.0, 0.0

    for h in holdings:
        total_weight += h["weight"]
        try:
            info = yf.Ticker(h["symbol"]).get_info() or {}
        except Exception:
            continue
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        target = info.get("targetMeanPrice")
        if not price or not target or price <= 0 or target <= 0:
            continue
        if not (1 / PRICE_SCALE_RATIO <= target / price <= PRICE_SCALE_RATIO):
            continue  # a target 5x the price is a stale or mis-scaled quote
        raw_yield = info.get("dividendYield") or 0.0
        # Yahoo has returned this both as a fraction and as a percent.
        income = raw_yield * 100.0 if raw_yield < 1 else raw_yield
        income = min(income, 15.0)
        expected = (target / price - 1) * 100.0 + income
        if not (HOLDING_RETURN_BOUNDS[0] <= expected <= HOLDING_RETURN_BOUNDS[1]):
            print(f"    {asset['id']}: dropped {h['symbol']} at {expected:+.0f}%; outside "
                  f"{HOLDING_RETURN_BOUNDS}, treating as a bad quote")
            continue
        contributions.append((h["weight"], expected))
        used_weight += h["weight"]

    if total_weight <= 0:
        raise ValueError(f"{asset['id']}: holdings carry no weight")
    coverage = used_weight / total_weight
    if coverage < MIN_SLEEVE_TARGET_COVERAGE:
        raise ValueError(
            f"{asset['id']}: only {coverage:.0%} of {asset['ticker']} by weight has analyst "
            f"targets ({len(contributions)} of {len(holdings)} names); not a consensus"
        )

    clipped, n_clipped = (winsorize(contributions)
                          if len(contributions) >= MIN_WINSOR_HOLDINGS
                          else (contributions, 0))
    if n_clipped:
        print(f"    {asset['id']}: clipped {n_clipped} outlying holding(s)")

    weighted = sum(w * e for w, e in clipped) / used_weight
    pct = check_return(weighted, asset["id"])

    # Dispersion matters more than the point estimate here: a single number
    # hides that sleeve constituents routinely span -1% to +25%. Weighted, so
    # the range describes the same basket as the number beside it.
    # 10th-90th rather than quartiles. A weighted IQR is so narrow on a
    # concentrated sleeve that the mean can sit outside it — arithmetically
    # correct under skew, but it reads as a broken number next to the figure
    # it describes.
    lo = hi = None
    if len(clipped) >= 4:
        p10, p90 = weighted_quantile(clipped, 0.10), weighted_quantile(clipped, 0.90)
        if p10 is not None and p90 is not None:
            lo, hi = round(p10, 1), round(p90, 1)

    why = (f"Weighted analyst consensus across {len(contributions)} of {len(holdings)} "
           f"{asset['ticker']} holdings ({coverage:.0%} of fund weight): mean target plus "
           f"income yield. Middle 80% of fund weight spans {lo}% to {hi}%."
           + (" The average sits outside that band, so a few large holdings carry "
              "this sleeve." if not (lo <= pct <= hi) else "")
           + (f" {n_clipped} outlier(s) clipped." if n_clipped else "")
           if lo is not None else
           f"Weighted analyst consensus across {len(contributions)} of {len(holdings)} "
           f"{asset['ticker']} holdings ({coverage:.0%} of fund weight).")

    return dict(r=pct, why=why, published=as_of or today.isoformat(),
                basis=f"{len(contributions)} holdings", lo=lo, hi=hi)


def sleeve_projection(asset, today):
    holdings, as_of = (fetch_ishares_holdings(asset) if asset["method"] == "ishares"
                       else fetch_yf_top_holdings(asset))
    return equity_sleeve_projection(asset, holdings, as_of, today)


# ---------------------------------------------------------------------------
# Searched rows
# ---------------------------------------------------------------------------

SEARCH_TOOL = {
    "name": "submit_forecasts",
    "description": (
        "Report the forecast figures found in the named publication. Report only what the "
        "document states; do NOT compute percentage changes — that arithmetic is done downstream."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "forecasts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "The asset id exactly as given"},
                        "currentValue": {"type": "number", "description": "The current level the publication compares against"},
                        "forecastValue": {"type": "number", "description": "The level forecast roughly one year ahead, in the SAME unit as currentValue"},
                        "unit": {"type": "string", "description": "Unit both values are quoted in, e.g. 'USD/tonne' or 'CAD'"},
                        "publisher": {"type": "string", "description": "The institution that published it"},
                        "publishedDate": {"type": "string", "description": "Publication date of the document, YYYY-MM-DD or YYYY-MM"},
                        "note": {"type": "string", "description": "Under 200 characters: what the document says and which edition it is"},
                    },
                    "required": ["id", "currentValue", "forecastValue", "unit", "publisher", "publishedDate", "note"],
                },
            },
            "notFound": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Ids you could NOT find a figure for in this publication. Reporting an id "
                    "here is a correct, expected answer — always preferable to omitting it "
                    "silently or substituting a different source."
                ),
            },
        },
        "required": ["forecasts"],
    },
}


class CostTracker:
    def __init__(self):
        self.total = 0.0

    def add(self, usage):
        cost = usage.input_tokens * PRICE_PER_INPUT_TOKEN
        cost += usage.output_tokens * PRICE_PER_OUTPUT_TOKEN
        cost += (usage.cache_creation_input_tokens or 0) * PRICE_PER_CACHE_WRITE_TOKEN
        cost += (usage.cache_read_input_tokens or 0) * PRICE_PER_CACHE_READ_TOKEN
        if usage.server_tool_use:
            cost += usage.server_tool_use.web_search_requests * PRICE_PER_SEARCH
        self.total += cost
        return cost


def extract_search_sources(blocks):
    sources, seen = [], set()
    for b in blocks:
        if b.type == "web_search_tool_result" and isinstance(b.content, list):
            for result in b.content:
                if result.url not in seen:
                    seen.add(result.url)
                    sources.append({"title": result.title, "url": result.url})
    return sources


def searches_used(usage):
    return getattr(getattr(usage, "server_tool_use", None), "web_search_requests", 0) or 0


def request_tool_call(client, model_id, prompt, tools, tool_name, max_tokens, costs,
                      min_searches=0, report=None):
    """Run one request, resuming paused turns.

    Paused turns are resumed because a search-heavy turn genuinely is unfinished.
    A turn that simply ends without calling the tool is NOT retried: that has
    proven deterministic rather than transient, so a second attempt re-runs
    every search to fail the same way. The group stales instead.

    min_searches guards against the opposite failure. Giving the model a legal
    way to answer "not found" let it satisfy tool_choice on the very first turn
    without searching at all — a whole group came back empty in 28ms having
    spent zero searches. An answer reached without looking is refused and sent
    back, which is cheap precisely because nothing was spent reaching it.
    """
    last_stop = None
    for attempt in range(1, REQUEST_ATTEMPTS + 1):
        messages = [{"role": "user", "content": prompt}]
        sources, searched, pushed_back = [], 0, False
        for _ in range(MAX_PAUSE_CONTINUATIONS + 1):
            response = client.messages.create(
                model=model_id, max_tokens=max_tokens, tools=tools,
                tool_choice={"type": "any", "disable_parallel_tool_use": True},
                messages=messages,
            )
            costs.add(response.usage)
            sources += extract_search_sources(response.content)
            searched += searches_used(response.usage)

            submitted = next((b for b in response.content
                              if b.type == "tool_use" and b.name == tool_name), None)
            if submitted is not None:
                if searched >= min_searches or pushed_back:
                    if report is not None:
                        report["searches"] = searched
                    return submitted.input, sources
                # Answered without looking. Reject it and require the search.
                print(f"    submitted after {searched} searches; requiring a search first")
                pushed_back = True
                messages = messages + [
                    {"role": "assistant", "content": response.content},
                    {"role": "user", "content": [{
                        "type": "tool_result",
                        "tool_use_id": submitted.id,
                        "is_error": True,
                        "content": ("Rejected: you called this tool without using web_search. "
                                    "You cannot know whether the publication contains these "
                                    "figures without looking. Search the web for the named "
                                    "publication now, read it, and only then call the tool again."),
                    }]},
                ]
                continue

            last_stop = response.stop_reason
            if last_stop != "pause_turn":
                break
            messages = messages + [{"role": "assistant", "content": response.content}]
        if REQUEST_ATTEMPTS > 1:
            print(f"    attempt {attempt}/{REQUEST_ATTEMPTS}: no {tool_name} call (stop_reason={last_stop})")
    raise ValueError(f"no {tool_name} call after {REQUEST_ATTEMPTS} attempts (last stop_reason={last_stop})")


def search_group(client, model_id, group, assets, today, costs):
    """Research one publication covering one or more assets. Returns {id: projection}."""
    blocks = "\n".join(
        f"- id: {a['id']}\n  Asset: {a['name']}\n  Look for: {a['hint']}" for a in assets
    )
    prompt = f"""Today is {today}, which is after your training cutoff — you cannot know current forecasts from memory.

Use web_search to find the most recent edition of: **{SEARCH_GROUPS[group]}**.

Read the figures for each of the following {len(assets)} item(s) out of that publication:

{blocks}

Rules:
- Use ONLY that named publication as the source of the forecast figures. Do not blend in other forecasters, and do not use aggregator or price-prediction sites.
- Report the CURRENT level and the level forecast roughly ONE YEAR ahead, both in the SAME unit. Do not compute a percentage change — that is done downstream.
- If the publication gives a multi-year path, use the point closest to one year out.
- Report the document's own publication date, not today's date.
- If you genuinely cannot find a figure for an item in that publication, put its id in "notFound". Do NOT substitute a different source, and do NOT skip calling the tool.

Search first — you cannot know whether the publication contains these figures without reading it, and an answer submitted without searching will be rejected.

You MUST finish by calling submit_forecasts, even if you found nothing at all — in that case call it with an empty "forecasts" list and every id in "notFound". Ending your turn without calling it loses the whole group."""

    report = {}
    submitted, sources = request_tool_call(
        client, model_id, prompt,
        tools=[{"type": "web_search_20250305", "name": "web_search",
                "max_uses": max(3, 2 * len(assets)), "blocked_domains": BLOCKED_SOURCE_DOMAINS},
               SEARCH_TOOL],
        tool_name="submit_forecasts",
        max_tokens=700 * len(assets) + 500,
        costs=costs,
        # "Not found" is only a real answer if it was reached by looking.
        min_searches=1,
        report=report,
    )
    # Log the search count unconditionally. Without it there is no way to tell
    # a genuine "the document does not say" from an answer given without
    # looking — and CI buffers stdout, so timings in the log prove nothing.
    print(f"    {report.get('searches', 0)} web search(es) used, "
          f"{len(sources)} source(s) seen")

    not_found = [str(i) for i in (submitted.get("notFound") or [])]
    if not_found:
        print(f"    publication carries no figure for {not_found}")

    by_id = {}
    for f in submitted.get("forecasts") or []:
        asset_id = f.get("id")
        if asset_id not in {a["id"] for a in assets}:
            continue
        current, forecast = f.get("currentValue"), f.get("forecastValue")
        if not isinstance(current, (int, float)) or not isinstance(forecast, (int, float)):
            continue
        if current <= 0 or forecast <= 0:
            print(f"    {asset_id}: non-positive levels {current} -> {forecast}; skipped")
            continue
        if not (1 / PRICE_SCALE_RATIO <= forecast / current <= PRICE_SCALE_RATIO):
            print(f"    {asset_id}: {current} -> {forecast} off-scale; likely unit mismatch, skipped")
            continue
        try:
            pct = check_return((forecast / current - 1) * 100, asset_id)
        except ValueError as e:
            print(f"    {e}")
            continue
        unit = f.get("unit", "")
        by_id[asset_id] = dict(
            r=pct,
            why=f"{f.get('publisher')} ({f.get('publishedDate')}): {forecast:,.6g} {unit} "
                f"one year out vs {current:,.6g} {unit} now. {f.get('note', '')}".strip(),
            published=str(f.get("publishedDate") or today.isoformat())[:10],
            basis=f"{current:,.6g} {unit}",
        )
        print(f"    {asset_id}: {current:,.6g} -> {forecast:,.6g} {unit} => {pct:+.1f}%")

    return by_id, sources


def select_model(client):
    models = [m.id for m in client.models.list().data]
    preferred = [m for m in models if m.startswith(PRICING_MODEL_FAMILY)]
    if preferred:
        return preferred[0]
    fallback = next((m for m in models if "haiku" in m), None)
    if fallback is None:
        raise RuntimeError(f"no Haiku model available; saw: {models}")
    print(f"Warning: {PRICING_MODEL_FAMILY} unavailable, using {fallback}; cost figures may be wrong.")
    return fallback


# ---------------------------------------------------------------------------
# Cadence
# ---------------------------------------------------------------------------

def search_is_due(asset, previous, today, force):
    """Searched rows are skipped until their publisher publishes again.

    CREA publishes quarterly and the World Bank twice a year. Asking monthly
    returns the same document at full price, and worse, invites the model to
    find a different source when the real one has not moved.
    """
    if force:
        return True
    published = (previous or {}).get("published")
    if not published:
        return True
    try:
        last = datetime.strptime(published[:7], "%Y-%m").date()
    except ValueError:
        return True
    return months_between(last, today) >= asset.get("cadence_months", 3)


# ---------------------------------------------------------------------------
# History / arrows
# ---------------------------------------------------------------------------

def compute_ranks(assets):
    """Rank 1..N by the 1-year figure, best first."""
    ranked = sorted(range(len(assets)), key=lambda i: -assets[i]["r"])
    return {assets[idx]["id"]: rank for rank, idx in enumerate(ranked, start=1)}


def position_change(prev_rank, new_rank):
    if prev_rank is None or prev_rank == new_rank:
        return "same"
    return "up" if new_rank < prev_rank else "down"


def apply_history(updated_assets, data_date):
    """Set posChange against the previous *distinct* run date.

    Re-running on a date that already has an entry replaces it. Otherwise
    repeated same-day runs compare each asset against a run from minutes
    earlier, which silently makes every arrow meaningless.
    """
    history = load_json(HISTORY_PATH, {"history": []})
    entries = history.get("history", [])

    replacing = bool(entries) and entries[-1]["date"] == data_date
    baseline = entries[:-1] if replacing else entries
    prev_ranks = baseline[-1]["ranks"] if baseline else {}

    new_ranks = compute_ranks(updated_assets)
    for asset in updated_assets:
        asset["posChange"] = position_change(prev_ranks.get(asset["id"]), new_ranks[asset["id"]])

    history["history"] = (baseline + [{"date": data_date, "ranks": new_ranks}])[-MAX_HISTORY_MONTHS:]
    return history


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Refresh Asset-Classes projections.")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--repair-stale", action="store_true",
                       help="refresh only the assets the last run left stale")
    scope.add_argument("--only", metavar="IDS", help="comma-separated asset ids to refresh")
    parser.add_argument("--force-search", action="store_true",
                        help="run searched rows even when their publisher is not due")
    return parser.parse_args()


def resolve_targets(args, data):
    known = {a["id"] for a in ASSETS}
    if args.repair_stale:
        wanted = set(data.get("staleAssetIds") or [])
        if not wanted:
            return [], True
    elif args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        unknown = wanted - known
        if unknown:
            raise SystemExit(f"unknown asset ids: {sorted(unknown)}")
    else:
        return ASSETS, False
    return [a for a in ASSETS if a["id"] in wanted], True


def refresh(targets, previous_by_id, today, costs, force_search):
    """Fetch every targeted asset. Returns (projections, sources, stale_ids, skipped)."""
    results, sources, stale, skipped = {}, [], [], []
    eia_key = os.environ.get("EIA_API_KEY", "").strip()

    fetched = [a for a in targets if a["method"] != "search"]
    searched = [a for a in targets if a["method"] == "search"]

    for asset in fetched:
        print(f"  {asset['id']} ({asset['method']})...")
        try:
            if asset["method"] == "boc":
                results[asset["id"]] = hisa_projection()
            elif asset["method"] == "eia":
                if not eia_key:
                    raise ValueError("EIA_API_KEY is not set")
                results[asset["id"]] = eia_projection(asset, eia_key, today)
            else:
                results[asset["id"]] = sleeve_projection(asset, today)
            print(f"    => {results[asset['id']]['r']:+.1f}%")
        except Exception as e:
            print(f"    FAILED ({type(e).__name__}: {e}) — keeping previous value")
            stale.append(asset["id"])

    # Group searched rows by publication so one document serves several assets.
    groups = {}
    for asset in searched:
        if not search_is_due(asset, previous_by_id.get(asset["id"]), today, force_search):
            skipped.append(asset["id"])
            continue
        groups.setdefault(asset["group"], []).append(asset)

    if skipped:
        print(f"  Not due (publisher has not published since last fetch): {skipped}")

    if groups:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        model_id = select_model(client)
        print(f"  Using model: {model_id}")
        for group, assets in groups.items():
            print(f"  Searching {SEARCH_GROUPS[group]} for {[a['id'] for a in assets]}...")
            try:
                by_id, group_sources = search_group(client, model_id, group, assets, today, costs)
            except Exception as e:
                print(f"    FAILED ({type(e).__name__}: {e}) — keeping previous values")
                stale.extend(a["id"] for a in assets)
                continue
            results.update(by_id)
            missing = [a["id"] for a in assets if a["id"] not in by_id]
            if missing:
                print(f"    no usable figure for {missing} — keeping previous values")
                stale.extend(missing)
            # One search budget serves the whole group, so sources belong to
            # the group rather than to any single asset within it.
            label = SEARCH_GROUPS[group]
            if group_sources:
                sources.append((sorted(by_id) or [a["id"] for a in assets],
                                label, group_sources))

    return results, sources, stale, skipped


def main():
    args = parse_args()
    today = date.today()
    data = load_json(DATA_PATH, {"assets": []})
    previous_by_id = {a["id"]: a for a in data.get("assets", [])}
    costs = CostTracker()

    targets, partial = resolve_targets(args, data)
    if partial and not targets:
        print("Nothing to repair: no stale assets recorded.")
        return

    data_date = data.get("updated") if (partial and data.get("updated")) else today.isoformat()
    print(f"{'Repairing' if partial else 'Refreshing'} {len(targets)} of {len(ASSETS)} assets (date {data_date})")

    results, source_groups, stale_ids, skipped = refresh(
        targets, previous_by_id, today, costs, args.force_search
    )
    if not results and not skipped:
        raise RuntimeError("nothing was refreshed; leaving data.json untouched")

    updated_assets = []
    for spec in ASSETS:
        previous = previous_by_id.get(spec["id"], {})
        fresh = results.get(spec["id"])
        row = {
            "id": spec["id"], "name": spec["name"], "cat": spec["cat"],
            "color": spec["color"], "publisher": spec["publisher"],
        }
        if fresh:
            row.update({k: v for k, v in fresh.items() if v is not None})
        elif "r" in previous:
            row.update({k: previous[k] for k in ("r", "why", "published", "basis", "lo", "hi")
                        if k in previous})
        else:
            # Never invent a value for an asset that has never been fetched.
            print(f"  {spec['id']}: no current or previous value — omitted from output")
            continue
        updated_assets.append(row)

    if not updated_assets:
        raise RuntimeError("no assets have a value; leaving data.json untouched")

    refreshed = set(results)
    kept = [s for s in data.get("sources", [])
            if not (set(str(s.get("assetId", "")).split("+")) & refreshed)] if partial else []
    seen = {s["url"] for s in kept}
    all_sources = list(kept)
    for ids, label, group_sources in source_groups:
        for s in group_sources:
            if s["url"] not in seen:
                seen.add(s["url"])
                all_sources.append({**s, "assetId": "+".join(ids), "assetName": label})

    still_stale = sorted((set(data.get("staleAssetIds") or []) | set(stale_ids)) - refreshed) \
        if partial else sorted(set(stale_ids))
    total_cost = costs.total + (data.get("lastRunCostUsd", 0.0) if partial else 0.0)

    history = apply_history(updated_assets, data_date)
    data.update({
        "assets": updated_assets,
        "updated": data_date,
        "horizon": "1-year",
        "sources": all_sources,
        "lastRunCostUsd": round(total_cost, 2),
        "staleAssetIds": still_stale,
    })
    write_json(DATA_PATH, data)
    write_json(HISTORY_PATH, history)

    summary = (f"data.json updated — {len(refreshed)} of {len(updated_assets)} assets refreshed, "
               f"{len(all_sources)} sources, cost ${costs.total:.4f}, date {data_date}")
    if skipped:
        summary += f" | not due: {skipped}"
    if still_stale:
        summary += f" | STALE (kept previous values): {still_stale}"
    print(summary)


if __name__ == "__main__":
    main()
