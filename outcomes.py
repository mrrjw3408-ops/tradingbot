import yfinance as yf
import pandas as pd
import gspread
import time
from google.oauth2.service_account import Credentials
from datetime import datetime
import sys
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import TICKERS

def clean(val):
    try:
        if val != val:
            return 0
        return round(float(val), 2)
    except:
        return 0

print("Starting outcomes.py...")

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
client = gspread.authorize(creds)
sheet = client.open("Trading Bot Log")
scan_log = sheet.worksheet("Scan Log")
outcomes = sheet.worksheet("Outcomes")
print("Sheets connected...")

sector_etfs = {
    "Energy": "XLE",
    "Infrastructure": "PAVE",
    "Finance": "XLF",
    "Health": "XLV",
    "Semiconductors": "SOXX",
    "Backdoor Tech": "XLK"
}

stocks = TICKERS

print("Checking market conditions...")
spy_df = yf.Ticker("SPY").history(period="3mo")
spy_closes = spy_df["Close"].dropna()
spy_ma50 = spy_closes.rolling(50).mean().iloc[-1]
spy_price = spy_closes.iloc[-1]
market_uptrend = spy_price > spy_ma50
market_filter_bonus = 0 if market_uptrend else -2
print(f"SPY: ${spy_price:.2f} | 50MA: ${spy_ma50:.2f} | {'UPTREND' if market_uptrend else 'DOWNTREND'}")

print("Fetching sector ETF benchmarks...")
etf_returns = {}
for sector, etf in sector_etfs.items():
    try:
        etf_df = yf.Ticker(etf).history(period="3mo")
        closes = etf_df["Close"].dropna()
        if len(closes) < 10:
            etf_returns[sector] = 0
            continue
        lookback = min(20, len(closes) - 1)
        ret = (closes.iloc[-1] / closes.iloc[-lookback] - 1) * 100
        etf_returns[sector] = ret if ret == ret else 0
        print(f"{etf} ({sector}): {etf_returns[sector]:.2f}%")
    except:
        etf_returns[sector] = 0

print("Starting scan of 300 stocks...\n")
now = datetime.now().strftime("%Y-%m-%d %H:%M")
logged = 0

for sector, tickers in stocks.items():
    for ticker in tickers:
        try:
            def fetch():
                return yf.Ticker(ticker).history(period="1y")
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(fetch)
                df = future.result(timeout=15)

            if df.empty or len(df) < 200:
                continue

            closes = df["Close"].dropna()
            if len(closes) < 200:
                continue

            delta = closes.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = -delta.where(delta < 0, 0).rolling(14).mean()
            rs = gain / loss
            rsi_series = 100 - (100 / (1 + rs))

            ma20 = closes.rolling(20).mean()
            bb_upper = ma20 + 2 * closes.rolling(20).std()
            bb_lower = ma20 - 2 * closes.rolling(20).std()

            ema12 = closes.ewm(span=12).mean()
            ema26 = closes.ewm(span=26).mean()
            macd = ema12 - ema26
            signal_line = macd.ewm(span=9).mean()

            vol_avg = df["Volume"].rolling(20).mean()
            ma50 = closes.rolling(50).mean()
            ma200 = closes.rolling(200).mean()

            price = float(closes.iloc[-1])
            rsi = float(rsi_series.iloc[-1])
            macd_val = float(macd.iloc[-1])
            macd_sig = float(signal_line.iloc[-1])
            bb_low = float(bb_lower.iloc[-1])
            bb_up = float(bb_upper.iloc[-1])
            ma50_val = float(ma50.iloc[-1])
            ma200_val = float(ma200.iloc[-1])
            vol_now = float(df["Volume"].iloc[-1])
            vol_avg_val = float(vol_avg.iloc[-1])

            if any(v != v for v in [price, rsi, macd_val, macd_sig, bb_low, bb_up, ma50_val, ma200_val]):
                continue

            volume_spike = vol_now > vol_avg_val

            lookback = min(20, len(closes) - 1)
            stock_return = (closes.iloc[-1] / closes.iloc[-lookback] - 1) * 100
            sector_return = etf_returns.get(sector, 0)
            rel_strength = float(stock_return) - float(sector_return)
            if rel_strength != rel_strength:
                rel_strength = 0

            mr_score = 0
            if rsi < 35:
                mr_score += 0.5
            if price <= bb_low:
                mr_score += 0.5
            if macd_val > macd_sig:
                mr_score += 0.5

            trend_score = 0
            if ma50_val > ma200_val:
                trend_score += 1.0
            if price > ma50_val:
                trend_score += 1.0

            sector_score = 0
            if rel_strength > 0.02:
                sector_score = 1.5
            elif rel_strength > 0:
                sector_score = 0.75

            vol_score = 0.5 if volume_spike else 0
            institutional_score = 0

            if rsi < 40 and price <= bb_low:
                trade_mode = "MEAN_REVERSION"
                weighted_score = (mr_score * 1.5) + (trend_score * 0.5) + sector_score + vol_score + institutional_score
            elif ma50_val > ma200_val and price > ma50_val:
                trade_mode = "MOMENTUM"
                weighted_score = (mr_score * 0.5) + (trend_score * 1.5) + sector_score + vol_score + institutional_score
            else:
               trade_mode = "NEUTRAL"
               weighted_score = mr_score + trend_score + sector_score + vol_score + institutional_score

            score = weighted_score
            score = round(min(max(score + market_filter_bonus, 0), 10), 2)

            breakdown = f"Trend:{trend_score}|Sector:{sector_score}|MeanRev:{mr_score}|Vol:{vol_score}|Inst:{institutional_score}"

            bb_signal = "BELOW BB" if price <= bb_low else "ABOVE BB" if price >= bb_up else "Neutral"
            vol_signal = "HIGH" if volume_spike else "Normal"

            scan_log.append_row([
                now, ticker, sector,
                clean(price), clean(rsi),
                bb_signal, vol_signal,
                clean(trend_score), clean(sector_score),
                clean(mr_score), clean(vol_score),
                clean(institutional_score), clean(score),
                breakdown
            ])

            outcomes.append_row([
                now, ticker, sector,
                clean(price), clean(score),
                "", "", "", "", ""
            ])

            logged += 1
            print(f"{ticker} ({sector}): ${price:.2f} | RSI: {rsi:.1f} | Score: {score} | {breakdown}")
            time.sleep(1.5)

        except (Exception, FutureTimeoutError) as e:
            print(f"{ticker}: skipped — {e}")

print(f"\nScan complete! {logged} stocks logged to Google Sheets!")
