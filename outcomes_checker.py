import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import time

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
client = gspread.authorize(creds)
sheet = client.open("Trading Bot Log")
outcomes = sheet.worksheet("Outcomes")

rows = outcomes.get_all_values()
header = rows[0]
today = datetime.now().date()

print(f"Checking {len(rows)-1} outcome rows...\n")

for i, row in enumerate(rows[1:], start=2):
    try:
        if len(row) < 5 or not row[0] or not row[1]:
            continue

        scan_date = datetime.strptime(row[0][:10], "%Y-%m-%d").date()
        ticker = row[1]
        entry_price = float(row[3]) if row[3] else None

        if not entry_price:
            continue

        days_elapsed = (today - scan_date).days

        # Get current price
        stock = yf.Ticker(ticker)
        current_price = stock.fast_info.last_price

        # Fill in 5 day price
        if days_elapsed >= 5 and not row[5]:
            outcomes.update_cell(i, 6, round(current_price, 2))
            print(f"{ticker}: filled 5D price ${current_price:.2f}")
            time.sleep(1)

        # Fill in 10 day price
        if days_elapsed >= 10 and not row[6]:
            outcomes.update_cell(i, 7, round(current_price, 2))
            print(f"{ticker}: filled 10D price ${current_price:.2f}")
            time.sleep(1)

        # Fill in 20 day price
        if days_elapsed >= 20 and not row[7]:
            outcomes.update_cell(i, 8, round(current_price, 2))
            print(f"{ticker}: filled 20D price ${current_price:.2f}")
            time.sleep(1)

        # Calculate best return and outcome if 20 days have passed
        if days_elapsed >= 20 and row[5] and row[6] and row[7]:
            prices = [float(row[5]), float(row[6]), float(row[7])]
            best_return = round(((max(prices) - entry_price) / entry_price) * 100, 2)
            outcome = "WIN" if best_return >= 9 else "LOSS"
            if not row[8]:
                outcomes.update_cell(i, 9, best_return)
                outcomes.update_cell(i, 10, outcome)
                print(f"{ticker}: {outcome} — best return {best_return}%")
                time.sleep(1)

    except Exception as e:
        print(f"Row {i} error: {e}")

print("\nOutcomes check complete!")
