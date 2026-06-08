import sys
import os
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time

# Add path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agents.sentiment import get_regime
from agents.aggregator import aggregate_signals
from agents.risk import apply_risk_rules
from report import send_report

print("=" * 50)
print("TRADING BOT STARTING")
print(datetime.now().strftime("%B %d, %Y %I:%M %p"))
print("=" * 50)

# Step 1 — Get market regime
print("\nSTEP 1 — MARKET REGIME")
regime_data = get_regime()

# Step 2 — Load latest scan results from Google Sheets
print("\nSTEP 2 — LOADING SCAN RESULTS")
try:
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open("Trading Bot Log")
    scan_log = sheet.worksheet("Scan Log")
    
    rows = scan_log.get_all_values()
    headers = rows[0]
    
    # Get today's scans only
    today = datetime.now().strftime("%Y-%m-%d")
    scan_results = []
    
    for row in rows[1:]:
        if len(row) >= 10 and row[0].startswith(today):
            try:
                scan_results.append({
                    "ticker": row[1],
                    "sector": row[2],
                    "price": float(row[3]) if row[3] else 0,
                    "rsi": float(row[4]) if row[4] else 0,
                    "score": float(row[9]) if row[9] else 0
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
    print("No scan results found — run outcomes.py first")
    strong_signals = []
    watchlist = []

# Step 4 — Apply risk rules
print("\nSTEP 4 — RISK MANAGEMENT")
approved_trades = apply_risk_rules(strong_signals)

# Step 5 — Send report
print("\nSTEP 5 — SENDING REPORT")
send_report(regime_data, strong_signals, watchlist, approved_trades)

print("\n" + "=" * 50)
print("TRADING BOT COMPLETE")
print("=" * 50)
