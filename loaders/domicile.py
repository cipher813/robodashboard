"""Classify a holding's domicile as US vs International — by domicile, not by
listing venue, so ADRs (RIO, ASML, TSM …) count as International even though
they trade on US exchanges.

Primary signal is yfinance's ``country`` field (the company's HQ/incorporation
country). When that's missing, fall back to the ticker's exchange suffix
(``D05.SP`` → Singapore, ``RMS.PA`` → France …), which is unambiguously
non-US. A per-ticker override map (from config) wins over both, for cases like
US-domiciled international-exposure ETFs (e.g. DIVI) that the operator wants
counted by exposure rather than fund domicile.
"""

from __future__ import annotations

US = "US"
INTERNATIONAL = "International"
UNKNOWN = "Unknown"

# Exchange suffixes that imply a non-US listing → International domicile when
# yfinance gives us no country. (US tickers are unsuffixed or .US.)
_NON_US_SUFFIXES = {
    "AX",  # Australia (ASX)
    "AS",  # Amsterdam
    "BR",  # Brussels
    "DE",  # Germany (XETRA)
    "HK",  # Hong Kong
    "L",  # London (LSE)
    "MI",  # Milan
    "PA",  # Paris
    "SI",  # Singapore (SGX)
    "SP",  # Singapore (alt)
    "SW",  # Switzerland (SIX)
    "SE",  # Stockholm / Swiss-listed (non-US either way)
    "T",  # Tokyo
    "TO",  # Toronto
    "HE",  # Helsinki
    "ST",  # Stockholm
    "CO",  # Copenhagen
    "MC",  # Madrid
}


def _normalize_overrides(overrides: dict | None) -> dict:
    """Lower-bound-friendly override lookup keyed by upper-cased ticker."""
    if not overrides:
        return {}
    return {str(k).upper(): str(v) for k, v in overrides.items()}


def classify_domicile(ticker: str, country: str | None, overrides: dict | None = None) -> str:
    """Return ``US`` / ``International`` / ``Unknown`` for one holding.

    Args:
        ticker: The (possibly suffixed) symbol, e.g. ``RIO`` or ``D05.SP``.
        country: yfinance ``info['country']`` (may be empty/None).
        overrides: Optional ``{ticker: "US"|"International"}`` map that wins
            over the automatic classification (for ETFs / manual corrections).
    """
    key = (ticker or "").upper()
    ov = _normalize_overrides(overrides)
    if key in ov:
        val = ov[key].strip().lower()
        if val in ("us", "united states", "domestic"):
            return US
        if val in ("international", "intl", "foreign"):
            return INTERNATIONAL
        return ov[key]  # pass through an explicit custom label

    if country:
        return US if country.strip() == "United States" else INTERNATIONAL

    # No country — infer from a non-US exchange suffix.
    if "." in key:
        suffix = key.rsplit(".", 1)[1]
        if suffix in _NON_US_SUFFIXES:
            return INTERNATIONAL

    return UNKNOWN
