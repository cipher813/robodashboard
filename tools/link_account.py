"""One-time account linking script for SnapTrade.

Usage:
    python tools/link_account.py

Steps:
    1. Creates a SnapTrade user (if first time)
    2. Generates a redirect URL for brokerage OAuth
    3. Opens browser for you to link your account
    4. Saves user_id + user_secret to .env
"""

from __future__ import annotations

import os
import sys
import webbrowser
from pathlib import Path

from dotenv import load_dotenv, set_key
from snaptrade_client import SnapTrade

ENV_PATH = Path(__file__).parent.parent / ".env"


def main():
    load_dotenv(ENV_PATH)

    client_id = os.environ.get("SNAPTRADE_CLIENT_ID")
    consumer_key = os.environ.get("SNAPTRADE_CONSUMER_KEY")

    if not client_id or not consumer_key:
        print("ERROR: Set SNAPTRADE_CLIENT_ID and SNAPTRADE_CONSUMER_KEY in .env first.")
        print("Get these from https://snaptrade.com after creating a developer account.")
        sys.exit(1)

    client = SnapTrade(consumer_key=consumer_key, client_id=client_id)

    # Check if user already exists
    user_id = os.environ.get("SNAPTRADE_USER_ID")
    user_secret = os.environ.get("SNAPTRADE_USER_SECRET")

    if not user_id or not user_secret:
        print("\n--- Step 1: Register SnapTrade user ---")
        user_id_input = input("Choose a user ID (e.g., your email or username): ").strip()
        if not user_id_input:
            print("ERROR: User ID cannot be empty.")
            sys.exit(1)

        response = client.authentication.register_snap_trade_user(user_id=user_id_input)
        user_id = response.body.get("userId", user_id_input)
        user_secret = response.body.get("userSecret", "")

        # Save to .env
        set_key(str(ENV_PATH), "SNAPTRADE_USER_ID", user_id)
        set_key(str(ENV_PATH), "SNAPTRADE_USER_SECRET", user_secret)
        print(f"User registered. Saved to {ENV_PATH}")
    else:
        print(f"Using existing user: {user_id}")

    # Generate login link for account connection
    print("\n--- Step 2: Link brokerage account ---")
    response = client.authentication.login_snap_trade_user(
        user_id=user_id,
        user_secret=user_secret,
    )

    redirect_url = response.body.get("redirectURI") or response.body.get("loginRedirectURI", "")
    if not redirect_url:
        print("ERROR: Could not get redirect URL from SnapTrade.")
        print(f"Response: {response.body}")
        sys.exit(1)

    print("\nOpening browser to link your brokerage account...")
    print(f"URL: {redirect_url}")
    webbrowser.open(redirect_url)

    print("\n--- Step 3: Complete linking in browser ---")
    print("After linking your account in the browser, press Enter to verify.")
    input("Press Enter to continue...")

    # Verify accounts
    accounts = client.account_information.list_user_accounts(
        user_id=user_id,
        user_secret=user_secret,
    )

    if accounts.body:
        print(f"\nLinked {len(accounts.body)} account(s):")
        for acct in accounts.body:
            print(f"  - {acct.get('name', 'Unknown')} ({acct.get('number', '')})")
        print("\nSetup complete. Run: streamlit run app.py")
    else:
        print("\nNo accounts found. Try running this script again or check SnapTrade dashboard.")


if __name__ == "__main__":
    main()
