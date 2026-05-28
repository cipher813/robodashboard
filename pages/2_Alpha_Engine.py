"""Alpha Engine page — the paper-trading system's view of your real holdings.

Joins alpha-engine research signals (ENTER/HOLD/EXIT + composite score) and
predictor predictions (UP/FLAT/DOWN + confidence + 21d alpha + veto) onto the
tickers you actually own, and flags buy candidates you don't yet hold.
"""

from __future__ import annotations

import streamlit as st

from bootstrap import get_clients, get_portfolio
from loaders import alpha_engine as ae

st.set_page_config(page_title="Alpha Engine · RoboDashboard", page_icon=":robot_face:", layout="wide")
st.title("Alpha Engine")
st.caption("Your paper-trading system's research signals + predictor view, mapped onto your real holdings.")

config, _, _, _ = get_clients()
ae_config = config.get("alpha_engine", {})
if not ae_config.get("enabled", True):
    st.info("Alpha Engine integration is disabled in config.yaml (alpha_engine.enabled: false).")
    st.stop()

bucket = ae_config.get("bucket", "alpha-engine-research")

df, _ = get_portfolio()
if df.empty:
    st.error("No holdings loaded — can't map alpha-engine signals.")
    st.stop()

# ── Load signals + predictions (graceful on failure) ─────────────────────────

try:
    signals_doc = ae.load_signals(bucket)
    predictions_doc = ae.load_predictions(bucket)
except ae.AlphaEngineUnavailable as e:
    st.warning(f"Alpha Engine data unavailable: {e}")
    st.stop()

regime = signals_doc.get("market_regime", "unknown")
sig_date = signals_doc.get("date", "?")
pred_date = predictions_doc.get("date", "?")
hit_rate = predictions_doc.get("model_hit_rate_30d")

cols = st.columns(4)
cols[0].metric("Market regime", str(regime).title())
cols[1].metric("Signals as of", sig_date)
cols[2].metric("Predictions as of", pred_date)
if hit_rate is not None:
    cols[3].metric("Predictor 30d hit rate", f"{hit_rate:.0%}")

# ── Join + coverage ──────────────────────────────────────────────────────────

joined = ae.join_holdings(df, signals_doc, predictions_doc)
cov = ae.coverage_summary(joined)

c1, c2, c3 = st.columns(3)
c1.metric("Holdings tracked", f"{cov['n_tracked']} / {cov['n_holdings']}")
c2.metric("EXIT signals on holdings", cov["n_exit"], delta_color="inverse")
c3.metric("Predictor vetoes on holdings", cov["n_veto"], delta_color="inverse")

if cov["n_exit"] or cov["n_veto"]:
    st.warning("The system is flagging EXIT and/or veto on positions you hold — see the table below.")

# ── Holdings × system view ───────────────────────────────────────────────────

st.subheader("Your holdings — system view")

tracked = joined[joined["tracked"]].copy()
untracked = joined[~joined["tracked"]]

if tracked.empty:
    st.info("None of your current holdings are in the alpha-engine research universe (S&P 500+400).")
else:
    display_cols = [
        "ticker",
        "name",
        "market_value",
        "weight_pct",
        "signal",
        "rating",
        "score",
        "conviction",
        "predicted_direction",
        "prediction_confidence",
        "predicted_alpha",
        "momentum_veto",
    ]
    show = tracked[[c for c in display_cols if c in tracked.columns]].copy()
    if "weight_pct" in show:
        show["weight_pct"] = show["weight_pct"] * 100
    if "prediction_confidence" in show:
        show["prediction_confidence"] = show["prediction_confidence"] * 100
    if "predicted_alpha" in show:
        show["predicted_alpha"] = show["predicted_alpha"] * 100
    st.dataframe(
        show,
        width="stretch",
        hide_index=True,
        column_config={
            "ticker": st.column_config.TextColumn("Ticker", width="small"),
            "name": st.column_config.TextColumn("Name", width="medium"),
            "market_value": st.column_config.NumberColumn("Mkt Value", format="$%,.0f"),
            "weight_pct": st.column_config.NumberColumn("Weight %", format="%.1f%%"),
            "signal": st.column_config.TextColumn("Signal", help="ENTER / HOLD / EXIT"),
            "rating": st.column_config.TextColumn("Rating", help="BUY / HOLD / SELL"),
            "score": st.column_config.NumberColumn("Score", format="%.0f", help="Composite attractiveness 0–100"),
            "conviction": st.column_config.TextColumn("Conviction"),
            "predicted_direction": st.column_config.TextColumn("Pred. Dir", help="UP / FLAT / DOWN"),
            "prediction_confidence": st.column_config.NumberColumn("Confidence", format="%.0f%%"),
            "predicted_alpha": st.column_config.NumberColumn(
                "Pred. 21d α", format="%+.1f%%", help="Predicted 21-day market-relative alpha"
            ),
            "momentum_veto": st.column_config.CheckboxColumn(
                "Veto", help="High-confidence DOWN → executor HOLD override"
            ),
        },
    )

    with st.expander("Theses for tracked holdings"):
        for _, r in tracked.iterrows():
            if r.get("thesis_summary"):
                st.markdown(f"**{r['ticker']}** · {r.get('signal') or '—'} · score {r.get('score') or '—'}")
                st.caption(r["thesis_summary"])

if not untracked.empty:
    st.caption("Not in the research universe: " + ", ".join(sorted(untracked["ticker"].tolist())))

# ── Buy candidates you don't hold ────────────────────────────────────────────

st.subheader("Buy candidates you don't hold")
unheld = ae.unheld_buy_candidates(df, signals_doc)
if not unheld:
    st.info("No un-held buy candidates in the latest signals.")
else:
    import pandas as pd

    cand_df = pd.DataFrame(unheld)
    cand_cols = [
        c for c in ["ticker", "sector", "rating", "score", "conviction", "sector_rating"] if c in cand_df.columns
    ]
    st.dataframe(
        cand_df[cand_cols].sort_values("score", ascending=False) if "score" in cand_cols else cand_df[cand_cols],
        width="stretch",
        hide_index=True,
        column_config={
            "score": st.column_config.NumberColumn("Score", format="%.0f"),
        },
    )
