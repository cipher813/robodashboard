"""Tests for loaders/alpha_engine.py — indexing, join, coverage (no S3)."""

import json

import pandas as pd
import pytest

from loaders import alpha_engine as ae


def _holdings():
    return pd.DataFrame({
        "ticker": ["EOG", "AAPL", "D05.SI"],  # D05.SI = SGX, not in AE universe
        "name": ["EOG Resources", "Apple", "DBS Group"],
        "shares": [100, 50, 200],
        "market_value": [12000.0, 9000.0, 7000.0],
        "weight_pct": [0.43, 0.32, 0.25],
    })


def _signals_doc():
    return {
        "date": "2026-05-22",
        "market_regime": "caution",
        "signals": {
            "EOG": {"ticker": "EOG", "signal": "ENTER", "rating": "BUY", "score": 75.7,
                    "conviction": "stable", "thesis_summary": "Strong commodity cycle.", "sector": "Energy"},
            "AAPL": {"ticker": "AAPL", "signal": "EXIT", "rating": "SELL", "score": 40.0,
                     "conviction": "weakening", "thesis_summary": "Valuation stretched.", "sector": "Technology"},
        },
        "buy_candidates": [
            {"ticker": "EOG", "signal": "ENTER", "score": 75.7, "rating": "BUY", "sector": "Energy"},
            {"ticker": "NVDA", "signal": "ENTER", "score": 82.1, "rating": "BUY", "sector": "Technology"},
        ],
    }


def _predictions_doc():
    return {
        "date": "2026-05-28",
        "model_hit_rate_30d": 0.55,
        "predictions": [
            {"ticker": "EOG", "predicted_direction": "UP", "prediction_confidence": 0.7,
             "predicted_alpha": 0.05, "momentum_veto": False},
            {"ticker": "AAPL", "predicted_direction": "DOWN", "prediction_confidence": 0.8,
             "predicted_alpha": -0.03, "momentum_veto": True},
        ],
    }


def test_index_signals_handles_dict_and_list():
    by_dict = ae.index_signals(_signals_doc())
    assert set(by_dict) == {"EOG", "AAPL"}
    as_list = {"signals": [{"ticker": "EOG"}, {"ticker": "AAPL"}]}
    assert set(ae.index_signals(as_list)) == {"EOG", "AAPL"}


def test_index_predictions_handles_list():
    by_ticker = ae.index_predictions(_predictions_doc())
    assert by_ticker["AAPL"]["momentum_veto"] is True


def test_join_holdings_attaches_views_and_flags_tracked():
    joined = ae.join_holdings(_holdings(), _signals_doc(), _predictions_doc())
    by_ticker = joined.set_index("ticker")
    assert by_ticker.loc["EOG", "signal"] == "ENTER"
    assert by_ticker.loc["EOG", "predicted_direction"] == "UP"
    assert by_ticker.loc["EOG", "tracked"]
    assert by_ticker.loc["AAPL", "signal"] == "EXIT"
    assert not by_ticker.loc["D05.SI", "tracked"]
    assert pd.isna(by_ticker.loc["D05.SI", "signal"])


def test_join_holdings_orders_tracked_first():
    joined = ae.join_holdings(_holdings(), _signals_doc(), _predictions_doc())
    # Last row should be the untracked SGX ticker.
    assert joined["ticker"].iloc[-1] == "D05.SI"


def test_coverage_summary_counts():
    joined = ae.join_holdings(_holdings(), _signals_doc(), _predictions_doc())
    cov = ae.coverage_summary(joined)
    assert cov["n_holdings"] == 3
    assert cov["n_tracked"] == 2
    assert cov["n_exit"] == 1   # AAPL
    assert cov["n_veto"] == 1   # AAPL


def test_unheld_buy_candidates_excludes_held():
    unheld = ae.unheld_buy_candidates(_holdings(), _signals_doc())
    tickers = {c["ticker"] for c in unheld}
    assert tickers == {"NVDA"}  # EOG is held → excluded


def test_coverage_summary_empty():
    cov = ae.coverage_summary(pd.DataFrame())
    assert cov == {"n_holdings": 0, "n_tracked": 0, "n_exit": 0, "n_veto": 0}


class _FakeS3:
    """Minimal boto3-s3-client stand-in."""

    def __init__(self, payloads):
        self._payloads = payloads

    def get_object(self, Bucket, Key):
        if Key not in self._payloads:
            raise KeyError(Key)
        body = json.dumps(self._payloads[Key]).encode()

        class _Body:
            def read(self_inner):
                return body

        return {"Body": _Body()}


def test_load_signals_via_injected_client():
    s3 = _FakeS3({ae.SIGNALS_KEY: _signals_doc()})
    doc = ae.load_signals("bucket", s3_client=s3)
    assert doc["market_regime"] == "caution"


def test_read_s3_json_wraps_errors():
    s3 = _FakeS3({})  # missing key → KeyError
    with pytest.raises(ae.AlphaEngineUnavailable):
        ae.load_signals("bucket", s3_client=s3)
