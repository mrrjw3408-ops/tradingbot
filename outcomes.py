import yfinance as yf
import pandas as pd
import gspread
import time
from google.oauth2.service_account import Credentials
from datetime import datetime

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

stocks = {
    "Energy": ["XOM","CVX","COP","EOG","SLB","MPC","PSX","VLO","OXY","HAL","BKR","DVN","WMB","OKE","KMI","LNG","ET","EPD","PAA","TRGP","MPLX","ENB","TRP","NRG","AES","EXC","NEE","DUK","SO","ED","PCG","ETR","XEL","WEC","ES","CMS","NI","ATO"],
    "Infrastructure": ["UNP","CSX","NSC","CP","CNI","WAB","GWW","PWR","MTZ","EME","ACM","FLR","KBR","TTEK","VMC","MLM","EXP","AWK","AMT","CCI","SBAC","DLR","EQIX","PLD","PSA","EXR","CUBE","REXR","FR","EGP","STAG","LXP","TRNO","MSEX","CWT","SJW","YORW","ARTNA"],
    "Finance": ["JPM","BAC","WFC","GS","MS","C","BLK","SCHW","AXP","COF","USB","PNC","TFC","BK","STT","MTB","CFG","HBAN","RF","KEY","FITB","ZION","CMA","V","MA","PYPL","FIS","FISV","GPN","DFS","BOKF","FFIN","WBS","UMBF","IBOC","CVBF","WAFD","TCBI"],
    "Health": ["JNJ","UNH","PFE","ABT","TMO","MRK","DHR","BMY","AMGN","GILD","CVS","CI","HUM","CNC","MOH","ELV","HCA","THC","UHS","ISRG","SYK","BSX","MDT","ZBH","EW","HOLX","DXCM","LLY","BIIB","REGN","VRTX","IQV","CRL","MEDP","ICLR","EVH","MMSI","NVCR","FATE"],
    "Semiconductors": ["NVDA","AMD","INTC","QCOM","AVGO","TXN","MU","AMAT","LRCX","KLAC","ASML","TSM","ARM","MRVL","ADI","NXPI","ON","SWKS","QRVO","MPWR","WOLF","SITM","AMBA","ALGM","DIOD","FORM","ACLS","ONTO","UCTT","COHU","ICHR","MTSI","AXTI","PDFS","CEVA","SLAB","TSEM","UMC"],
    "Backdoor Tech": ["CSCO","FFIV","NTAP","PSTG","HPE","DELL","STX","WDC","T","VZ","TMUS","LUMN","CRWD","PANW","FTNT","ZS","OKTA","S","TENB","RPD","VRNS","QLYS","ETN","CARR","TT","JCI","GTLS","VICR","CTS","LFUS","NOVT","CABO","SHEN","ITRN","AWR","OTIS"]
}

print("Checking market conditions...")
spy_df = yf.Ticker("SPY").history(period="3mo")
spy_ma50 = spy_df["Close"].rolling(50).mean().iloc[-1]
spy_price = spy_df["Close"].iloc[-1]
market_uptrend = spy_price > spy_ma50
market_filter_bonus = 0 if market_uptrend else -2
print(f"SPY: ${spy_price:.2f} | 50MA: ${spy_ma50:.2f} | {'UPTREND' if market_uptrend else 'DOWNTREND'}")

print("Fetching sector ETF benchmarks...")
etf_returns = {}
for sector, etf in sector_etfs.items():
    try:
        etf_df = yf.Ticker(etf).history(period="1mo")
        etf_returns[sector] = (etf_df["Close"].iloc[-1] / etf_df["Close"].iloc[-20] - 1) * 100
        print(f"{etf} ({sector}): {etf_returns[sector]:.2f}%")
    except:
        etf_returns[sector] = 0

print("Starting scan of 300 stocks...\n")
now = datetime.now().strftime("%Y-%m-%d %H:%M")
logged = 0

for sector, tickers in stocks.items():
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period="1y")
            if df.empty or len(df) < 200:
                continue

            delta = df["Close"].diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = -delta.where(delta < 0, 0).rolling(14).mean()
            rs = gain / loss
            df["RSI"] = 100 - (100 / (1 + rs))

            df["MA20"] = df["Close"].rolling(20).mean()
            df["BB_upper"] = df["MA20"] + 2 * df["Close"].rolling(20).std()
            df["BB_lower"] = df["MA20"] - 2 * df["Close"].rolling(20).std()

            df["EMA12"] = df["Close"].ewm(span=12).mean()
            df["EMA26"] = df["Close"].ewm(span=26).mean()
            df["MACD"] = df["EMA12"] - df["EMA26"]
            df["Signal_Line"] = df["MACD"].ewm(span=9).mean()

            df["Vol_Avg"] = df["Volume"].rolling(20).mean()
            df["MA50"] = df["Close"].rolling(50).mean()
            df["MA200"] = df["Close"].rolling(200).mean()

            stock_return = (df["Close"].iloc[-1] / df["Close"].iloc[-20] - 1) * 100
            sector_return = etf_returns.get(sector, 0)
            rel_strength = stock_return - sector_return

            latest = df.iloc[-1]
            price = latest["Close"]
            rsi = latest["RSI"]
            macd = latest["MACD"]
            macd_signal = latest["Signal_Line"]
            bb_lower = latest["BB_lower"]
            bb_upper = latest["BB_upper"]
            ma50 = latest["MA50"]
            ma200 = latest["MA200"]
            volume_spike = latest["Volume"] > latest["Vol_Avg"]

            mr_score = 0
            if rsi < 35:
                mr_score += 0.5
            if price <= bb_lower:
                mr_score += 0.5
            if macd > macd_signal:
                mr_score += 0.5

            trend_score = 0
            if ma50 > ma200:
                trend_score += 1.0
            if price > ma50:
                trend_score += 1.0

            sector_score = 0
            if rel_strength > 0.02:
                sector_score = 1.5
            elif rel_strength > 0:
                sector_score = 0.75

            vol_score = 0.5 if volume_spike else 0
            institutional_score = 0

            score = mr_score + trend_score + sector_score + vol_score + institutional_score
            score = round(min(max(score + market_filter_bonus, 0), 10), 2)

            breakdown = f"Trend:{trend_score}|Sector:{sector_score}|MeanRev:{mr_score}|Vol:{vol_score}|Inst:{institutional_score}"

            scan_log.append_row([
                now, ticker, sector,
                round(price, 2),
                round(rsi, 2),
                "BELOW BB" if price <= bb_lower else "ABOVE BB" if price >= bb_upper else "Neutral",
                "HIGH" if volume_spike else "Normal",
                round(trend_score, 2),
                round(sector_score, 2),
                round(mr_score, 2),
                round(vol_score, 2),
                round(institutional_score, 2),
                round(score, 2),
                breakdown
            ])

            outcomes.append_row([
                now, ticker, sector,
                round(price, 2),
                round(score, 2),
                "", "", "", "", ""
            ])

            logged += 1
            print(f"{ticker} ({sector}): ${price:.2f} | RSI: {rsi:.1f} | Score: {score} | {breakdown}")
            time.sleep(2.5)

        except Exception as e:
            print(f"{ticker}: skipped — {e}")

print(f"\nScan complete! {logged} stocks logged to Google Sheets!")
