import sys
import os
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agents.sentiment import get_regime
from agents.aggregator import aggregate_signals
from agents.risk import apply_risk_rules
from agents.options_strategy import analyze_batch
from agents.options_paper import log_trade, check_open_trades, get_portfolio_summary
from report import send_report
from agents.sanity_checker import run_sanity_check

print("=" * 55)
print("TRADING BOT STARTING")
print(datetime.now().strftime("%B %d, %Y %I:%M %p"))
print("=" * 55)

# Step 1 — Market regime
print("\nSTEP 1 — MARKET REGIME")
regime_data = get_regime()
regime = regime_data["regime"]

# Step 2 — Load today's scan results
print("\nSTEP 2 — LOADING SCAN RESULTS")
try:
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open("Trading Bot Log")
    scan_log = sheet.worksheet("Scan Log")

    rows = scan_log.get_all_values()
    today = datetime.now().strftime("%Y-%m-%d")
    scan_results = []

    for row in rows[1:]:
        if len(row) >= 13 and row[0].startswith(today):
            try:
                # Determine trade mode from scores
                trend_score = float(row[7]) if row[7] else 0
                mr_score = float(row[9]) if row[9] else 0
                rsi = float(row[4]) if row[4] else 50
                bb_signal = row[5] if row[5] else ""
                price = float(row[3]) if row[3] else 0

                if rsi < 40 and bb_signal == "BELOW BB":
                    trade_mode = "MEAN_REVERSION"
                elif trend_score >= 1.5:
                    trade_mode = "MOMENTUM"
                else:
                    trade_mode = "NEUTRAL"

                scan_results.append({
                    "ticker": row[1],
                    "sector": row[2],
                    "price": price,
                    "rsi": rsi,
                    "score": float(row[12]) if row[12] else 0,
                    "trade_mode": trade_mode
                })
            except:
                continue

    print(f"Loaded {len(scan_results)} stocks from today's scan")

except Exception as e:
    print(f"Error loading scan results: {e}")
    scan_results = []

# Step 3 — Aggregate signals
print("\nSTEP 3 — AGGREGATING SIGNALS")
if scan_results:
    strong_signals, watchlist = aggregate_signals(scan_results, regime_data)
else:
    print("No scan results — run outcomes.py first")
    strong_signals = []
    watchlist = []

# Step 4 — Risk management
print("\nSTEP 4 — RISK MANAGEMENT")
approved_trades = apply_risk_rules(strong_signals)

# Step 5 — Options strategy
print("\nSTEP 5 — OPTIONS STRATEGY")
options_trades = []
if approved_trades:
    options_trades = analyze_batch(approved_trades, regime)
    for trade in options_trades:
        log_trade(trade)
        time.sleep(1)
else:
    print("No approved trades to analyze for options")

# Step 6 — Check existing open paper trades
print("\nSTEP 6 — CHECKING OPEN PAPER TRADES")
check_open_trades()
options_summary = get_portfolio_summary()

# Step 6b — Run automated sanity check on closed trades
# Only sends an email when there's something genuinely new to flag or
# enough closed history to be worth checking -- avoids spamming "no closed
# trades yet" emails on every single run while positions are still open
print("\nSTEP 6b — RUNNING SANITY CHECK")
try:
    run_sanity_check(send_email=False)
except Exception as e:
    print(f"Sanity check error: {e}")

# Step 7 — Send report
print("\nSTEP 7 — SENDING REPORT")
send_report(
    regime_data,
    strong_signals,
    watchlist,
    approved_trades,
    options_trades=options_trades,
    options_summary=options_summary
)

print("\n" + "=" * 55)
print("TRADING BOT COMPLETE")
print("=" * 55)
