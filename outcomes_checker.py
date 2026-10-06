import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
client = gspread.authorize(creds)
sheet = client.open("Trading Bot Log")
outcomes = sheet.worksheet("Outcomes")

rows = outcomes.get_all_values()
header = rows[0]
today = datetime.now().date()
cutoff_date = today - timedelta(days=25)
cutoff_str = cutoff_date.strftime("%Y-%m-%d")

print(f"Total rows: {len(rows)-1}")

price_cache = {}

def get_price(ticker):
    if ticker in price_cache:
        return price_cache[ticker]
    def fetch():
        df = yf.Ticker(ticker).history(period="1d")
        if df.empty:
            raise ValueError("no data")
        return float(df["Close"].iloc[-1])
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fetch)
        price = future.result(timeout=15)
    price_cache[ticker] = price
    return price

checked = 0
skipped_old = 0

for i, row in enumerate(rows[1:], start=2):
    try:
        if len(row) < 5 or not row[0] or not row[1]:
            continue

        if row[0][:10] < cutoff_str:
            skipped_old += 1
            continue

        scan_date = datetime.strptime(row[0][:10], "%Y-%m-%d").date()
        ticker = row[1]
        entry_price = float(row[3]) if row[3] else None

        if not entry_price:
            continue

        days_elapsed = (today - scan_date).days

        needs_5d = days_elapsed >= 5 and not row[5]
        needs_10d = days_elapsed >= 10 and not row[6]
        needs_20d = days_elapsed >= 20 and not row[7]

        if not (needs_5d or needs_10d or needs_20d):
            continue

        checked += 1
        current_price = get_price(ticker)

        if needs_5d:
            outcomes.update_cell(i, 6, round(current_price, 2))
            print(f"{ticker}: filled 5D price ${current_price:.2f}")
            time.sleep(1)

        if needs_10d:
            outcomes.update_cell(i, 7, round(current_price, 2))
            print(f"{ticker}: filled 10D price ${current_price:.2f}")
            time.sleep(1)

        if needs_20d:
            outcomes.update_cell(i, 8, round(current_price, 2))
            print(f"{ticker}: filled 20D price ${current_price:.2f}")
            time.sleep(1)

        if days_elapsed >= 20 and row[5] and row[6] and row[7]:
            prices = [float(row[5]), float(row[6]), float(row[7])]
            best_return = round(((max(prices) - entry_price) / entry_price) * 100, 2)
            outcome = "WIN" if best_return >= 9 else "LOSS"
            if not row[8]:
                outcomes.update_cell(i, 9, best_return)
                outcomes.update_cell(i, 10, outcome)
                print(f"{ticker}: {outcome} — best return {best_return}%")
                time.sleep(1)

    except (Exception, FutureTimeoutError) as e:
        print(f"Row {i} error: {e}")

print(f"\nOutcomes check complete! Checked {checked} rows, skipped {skipped_old} old rows, {len(price_cache)} unique tickers fetched.")
