"""Read-only SnapTrade client.

Fetches account data, positions, and balances from linked brokerage accounts
via the SnapTrade API. This module has NO TRADING METHODS — it is read-only
by design.

Usage:
    reader = SnapTradeReader.from_env()
    accounts = reader.get_accounts()
    holdings = reader.get_aggregated_holdings()
    nav = reader.get_total_nav()
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
from snaptrade_client import SnapTrade

logger = logging.getLogger(__name__)

POSITIONS_CACHE_PATH = Path("cache/positions_latest.json")


class SnapTradeReader:
    """Read-only SnapTrade client. NO TRADING METHODS."""

    def __init__(self, client_id: str, consumer_key: str, user_id: str, user_secret: str):
        self._client = SnapTrade(consumer_key=consumer_key, client_id=client_id)
        self._user_id = user_id
        self._user_secret = user_secret

    @classmethod
    def from_env(cls) -> SnapTradeReader:
        """Create reader from environment variables."""
        return cls(
            client_id=os.environ["SNAPTRADE_CLIENT_ID"],
            consumer_key=os.environ["SNAPTRADE_CONSUMER_KEY"],
            user_id=os.environ["SNAPTRADE_USER_ID"],
            user_secret=os.environ["SNAPTRADE_USER_SECRET"],
        )

    def get_accounts(self) -> list[dict]:
        """Return all linked accounts with id, name, type, and institution."""
        response = self._client.account_information.list_user_accounts(
            user_id=self._user_id,
            user_secret=self._user_secret,
        )
        accounts = []
        for acct in response.body:
            accounts.append(
                {
                    "id": str(acct.get("id", "")),
                    "name": acct.get("name", ""),
                    "number": acct.get("number", ""),
                    "type": acct.get("institution_type", acct.get("type", "")),
                    "institution": acct.get("brokerage_authorization", {}).get("brokerage", {}).get("name", "")
                    if isinstance(acct.get("brokerage_authorization"), dict)
                    else "",
                }
            )
        logger.info("Found %d linked accounts", len(accounts))
        return accounts

    def get_holdings(self, account_id: str) -> list[dict]:
        """Get positions for a single account."""
        response = self._client.account_information.get_user_holdings(
            account_id=account_id,
            user_id=self._user_id,
            user_secret=self._user_secret,
        )
        holdings = []
        for pos in response.body.get("positions", []):
            symbol_info = pos.get("symbol", {}) or {}
            symbol_obj = symbol_info.get("symbol", {}) or {}
            ticker = symbol_obj.get("symbol", "") if isinstance(symbol_obj, dict) else str(symbol_obj)
            if not ticker:
                continue
            # Native trading currency (e.g. SGD for SGX, HKD for SEHK). Prefer the
            # symbol's currency; fall back to the position-level currency, then USD.
            ccy_obj = (symbol_obj.get("currency") if isinstance(symbol_obj, dict) else None) or pos.get("currency")
            currency = ccy_obj.get("code", "USD") if isinstance(ccy_obj, dict) else "USD"
            holdings.append(
                {
                    "account_id": account_id,
                    "ticker": ticker,
                    "currency": currency,
                    "shares": float(pos.get("units", 0)),
                    "avg_cost": float(pos.get("average_purchase_price") or 0),
                    "current_price": float(pos.get("price") or 0),
                    "market_value": float(pos.get("open_pnl", 0))
                    + float(pos.get("units", 0)) * float(pos.get("average_purchase_price") or 0),
                }
            )
        return holdings

    def get_all_holdings(self) -> pd.DataFrame:
        """Get all positions across all accounts."""
        accounts = self.get_accounts()
        all_holdings = []
        for acct in accounts:
            try:
                holdings = self.get_holdings(acct["id"])
                for h in holdings:
                    h["account_name"] = acct["name"]
                    h["account_type"] = acct["type"]
                all_holdings.extend(holdings)
            except Exception as e:
                logger.warning("Failed to fetch holdings for account %s: %s", acct["name"], e)
        df = pd.DataFrame(all_holdings)
        if not df.empty:
            self._save_cache(df)
        return df

    def get_aggregated_holdings(self) -> pd.DataFrame:
        """Get holdings aggregated by ticker across all accounts.

        Computes weighted average cost basis across sub-accounts.
        """
        df = self.get_all_holdings()
        if df.empty:
            return df
        agg = (
            df.groupby("ticker")
            .agg(
                currency=("currency", "first"),  # constant per ticker
                shares=("shares", "sum"),
                total_cost=("avg_cost", lambda x: (x * df.loc[x.index, "shares"]).sum()),
                market_value=("market_value", "sum"),
                n_accounts=("account_id", "nunique"),
            )
            .reset_index()
        )
        agg["avg_cost"] = agg["total_cost"] / agg["shares"]
        agg["avg_cost"] = agg["avg_cost"].round(4)
        agg.drop(columns=["total_cost"], inplace=True)
        return agg

    def get_balances(self) -> dict:
        """Get cash balances per account and aggregate."""
        accounts = self.get_accounts()
        balances = {}
        total_cash = 0.0
        for acct in accounts:
            try:
                response = self._client.account_information.get_user_account_balance(
                    account_id=acct["id"],
                    user_id=self._user_id,
                    user_secret=self._user_secret,
                )
                cash = sum(float(b.get("cash", 0)) for b in response.body)
                balances[acct["name"]] = cash
                total_cash += cash
            except Exception as e:
                logger.warning("Failed to fetch balance for account %s: %s", acct["name"], e)
        balances["total"] = total_cash
        return balances

    def get_total_nav(self) -> float:
        """Get total net asset value across all accounts."""
        holdings = self.get_all_holdings()
        balances = self.get_balances()
        positions_value = holdings["market_value"].sum() if not holdings.empty else 0
        return positions_value + balances.get("total", 0)

    def _save_cache(self, df: pd.DataFrame) -> None:
        """Save positions to local cache for offline fallback."""
        try:
            POSITIONS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            cache_data = {
                "timestamp": datetime.now().isoformat(),
                "positions": df.to_dict(orient="records"),
            }
            POSITIONS_CACHE_PATH.write_text(json.dumps(cache_data, indent=2, default=str))
        except Exception as e:
            logger.debug("Failed to save positions cache: %s", e)

    @staticmethod
    def load_cached_holdings() -> tuple[pd.DataFrame, str]:
        """Load last-known positions from cache. Returns (df, timestamp)."""
        if not POSITIONS_CACHE_PATH.exists():
            return pd.DataFrame(), ""
        data = json.loads(POSITIONS_CACHE_PATH.read_text())
        return pd.DataFrame(data["positions"]), data["timestamp"]
