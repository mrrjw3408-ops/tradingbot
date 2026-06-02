import yfinance as yf
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
client = gspread.authorize(creds)
sheet = client.open("Trading Bot Log").sheet1

tickers = ["AAPL", "TSLA", "NVDA", "MSFT", "AMD", "META", "AMZN", "GOOGL"]

print("Scanning stocks...")

for ticker in tickers:
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="3mo")
        delta = df["Close"].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / loss
        df["RSI"] = 100 - (100 / (1 + rs))
        df["MA20"] = df["Close"].rolling(20).mean()
        df["BB_upper"] = df["MA20"] + 2 * df["Close"].rolling(20).std()
        df["BB_lower"] = df["MA20"] - 2 * df["Close"].rolling(20).std()
        df["Vol_Avg"] = df["Volume"].rolling(20).mean()
        latest = df.iloc[-1]
        rsi = latest["RSI"]
        price = latest["Close"]
        bb_upper = latest["BB_upper"]
        bb_lower = latest["BB_lower"]
        volume_spike = latest["Volume"] > latest["Vol_Avg"]
        if rsi < 35 and price <= bb_lower and volume_spike:
            signal = "STRONG BUY SIGNAL"
        elif rsi < 35:
            signal = "OVERSOLD"
        elif rsi > 65:
            signal = "OVERBOUGHT"
        elif price < bb_lower:
            signal = "BELOW BB"
        elif price > bb_upper:
            signal = "ABOVE BB"
        else:
            signal = "Neutral"
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        sheet.append_row([now, ticker, round(price, 2), round(rsi, 2), signal, round(bb_upper, 2), round(bb_lower, 2)])
        print(f"{ticker}: ${price:.2f} | RSI: {rsi:.1f} | {signal} - Logged!")
    except Exception as e:
      print(f"{ticker}: Error - {type(e).__name__}: {e}")

print("Scan complete! Check your Google Sheet!")
sheet.append_row([now, ticker, round(price, 2), round(rsi, 2), signal, round(bb_upper, 2), round(bb_lower, 2), int(latest["Volume"]), int(latest["Vol_Avg"])])

import yfinance as yf
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
client = gspread.authorize(creds)
sheet = client.open("Trading Bot Log").sheet1

tickers = ["AAPL", "TSLA", "NVDA", "MSFT", "AMD", "META", "AMZN", "GOOGL"]

print("Scanning stocks...")

for ticker in tickers:
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="3mo")
        delta = df["Close"].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / loss
        df["RSI"] = 100 - (100 / (1 + rs))
        df["MA20"] = df["Close"].rolling(20).mean()
        df["BB_upper"] = df["MA20"] + 2 * df["Close"].rolling(20).std()
        df["BB_lower"] = df["MA20"] - 2 * df["Close"].rolling(20).std()
        df["Vol_Avg"] = df["Volume"].rolling(20).mean()
        latest = df.iloc[-1]
        rsi = latest["RSI"]
        price = latest["Close"]
        bb_upper = latest["BB_upper"]
        bb_lower = latest["BB_lower"]
        volume_spike = latest["Volume"] > latest["Vol_Avg"]
        if rsi < 35 and price <= bb_lower and volume_spike:
            signal = "STRONG BUY SIGNAL"
        elif rsi < 35:
            signal = "OVERSOLD"
        elif rsi > 65:
            signal = "OVERBOUGHT"
        elif price < bb_lower:
            signal = "BELOW BB"
        elif price > bb_upper:
            signal = "ABOVE BB"
        else:
            signal = "Neutral"
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        sheet.append_row([now, ticker, round(price, 2), round(rsi, 2), signal, round(bb_upper, 2), round(bb_lower, 2), int(latest["Volume"]), int(latest["Vol_Avg"])])
        print(f"{ticker}: ${price:.2f} | RSI: {rsi:.1f} | {signal} - Logged!")
    except Exception as e:
        print(f"{ticker}: Error - {e}")

print("Scan complete! Check your Google Sheet!")
