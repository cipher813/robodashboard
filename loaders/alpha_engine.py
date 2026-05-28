"""Alpha Engine signal loader.

Reads the alpha-engine research signals + predictor predictions from S3 and
joins them onto the real holdings, so the dashboard can answer "for the stocks
I actually own, what does my paper-trading system say?".

I/O (the S3 fetch) is isolated in ``load_signals`` / ``load_predictions``; the
``join_holdings`` and indexing helpers are pure and unit-tested without S3.
"""

from __future__ import annotations

import json
import logging

import pandas as pd

logger = logging.getLogger(__name__)

SIGNALS_KEY = "signals/latest.json"
PREDICTIONS_KEY = "predictor/predictions/latest.json"


class AlphaEngineUnavailable(RuntimeError):
    """Raised when alpha-engine data cannot be loaded (boto3/creds/bucket)."""


def _read_s3_json(bucket: str, key: str, s3_client=None) -> dict:
    """Fetch + parse a JSON object from S3.

    Uses the default AWS profile/credential chain. Raises
    AlphaEngineUnavailable with a human-readable cause on any failure so the
    page can surface *why* it's unavailable rather than silently blanking.
    """
    if s3_client is None:
        try:
            import boto3
        except ImportError as e:
            raise AlphaEngineUnavailable(
                "boto3 is not installed — run `pip install boto3` to enable the Alpha Engine page."
            ) from e
        s3_client = boto3.client("s3")
    try:
        obj = s3_client.get_object(Bucket=bucket, Key=key)
        return json.loads(obj["Body"].read())
    except Exception as e:  # botocore errors, no creds, missing key, etc.
        raise AlphaEngineUnavailable(f"Could not read s3://{bucket}/{key}: {e}") from e


def load_signals(bucket: str, s3_client=None) -> dict:
    """Load the latest research signals document."""
    return _read_s3_json(bucket, SIGNALS_KEY, s3_client)


def load_predictions(bucket: str, s3_client=None) -> dict:
    """Load the latest predictor predictions document."""
    return _read_s3_json(bucket, PREDICTIONS_KEY, s3_client)


def index_signals(signals_doc: dict) -> dict[str, dict]:
    """Return {ticker -> signal record} from a signals document."""
    sig = (signals_doc or {}).get("signals", {})
    if isinstance(sig, dict):
        return sig
    return {s["ticker"]: s for s in sig if s.get("ticker")}


def index_predictions(predictions_doc: dict) -> dict[str, dict]:
    """Return {ticker -> prediction record} from a predictions document."""
    preds = (predictions_doc or {}).get("predictions", [])
    if isinstance(preds, dict):
        return preds
    return {p["ticker"]: p for p in preds if p.get("ticker")}


def join_holdings(
    holdings: pd.DataFrame,
    signals_doc: dict,
    predictions_doc: dict,
) -> pd.DataFrame:
    """Join alpha-engine research + predictor views onto held tickers.

    Returns one row per holding with the system's view attached, plus a
    ``tracked`` flag (True when the research universe covers the ticker).
    Rows are ordered tracked-first, then by market value.
    """
    sig_by_ticker = index_signals(signals_doc)
    pred_by_ticker = index_predictions(predictions_doc)

    rows = []
    for _, h in holdings.iterrows():
        ticker = h["ticker"]
        sig = sig_by_ticker.get(ticker, {})
        pred = pred_by_ticker.get(ticker, {})
        tracked = bool(sig) or bool(pred)
        rows.append({
            "ticker": ticker,
            "name": h.get("name", ticker),
            "shares": h.get("shares"),
            "market_value": h.get("market_value"),
            "weight_pct": h.get("weight_pct"),
            "tracked": tracked,
            # Research view
            "signal": sig.get("signal"),
            "rating": sig.get("rating"),
            "score": sig.get("score"),
            "conviction": sig.get("conviction"),
            "thesis_summary": sig.get("thesis_summary"),
            # Predictor view
            "predicted_direction": pred.get("predicted_direction"),
            "prediction_confidence": pred.get("prediction_confidence"),
            "predicted_alpha": pred.get("predicted_alpha"),
            "momentum_veto": pred.get("momentum_veto"),
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df.sort_values(
            ["tracked", "market_value"],
            ascending=[False, False],
            inplace=True,
            kind="stable",
        )
        df.reset_index(drop=True, inplace=True)
    return df


def unheld_buy_candidates(holdings: pd.DataFrame, signals_doc: dict) -> list[dict]:
    """Return buy_candidates the system likes that are NOT currently held."""
    held = set(holdings["ticker"]) if not holdings.empty else set()
    candidates = (signals_doc or {}).get("buy_candidates", []) or []
    return [c for c in candidates if c.get("ticker") and c["ticker"] not in held]


def coverage_summary(joined: pd.DataFrame) -> dict:
    """Headline coverage counts + flags worth surfacing."""
    if joined.empty:
        return {"n_holdings": 0, "n_tracked": 0, "n_exit": 0, "n_veto": 0}
    return {
        "n_holdings": len(joined),
        "n_tracked": int(joined["tracked"].sum()),
        "n_exit": int((joined["signal"] == "EXIT").sum()),
        "n_veto": int((joined["momentum_veto"] == True).sum()),  # noqa: E712
    }
