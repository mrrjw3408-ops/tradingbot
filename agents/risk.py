import sys
import os
import yfinance as yf
import pandas as pd
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (STARTING_CAPITAL, MAX_POSITION_PCT, MIN_POSITION_PCT,
                   MAX_POSITIONS, MAX_SECTOR_POSITIONS, MAX_CORRELATION)

def get_position_size(score, capital):
    pct = MIN_POSITION_PCT + (score / 10) * (MAX_POSITION_PCT - MIN_POSITION_PCT)
    return round(min(pct, MAX_POSITION_PCT) * capital, 2)

def check_correlation(tickers):
    try:
        if len(tickers) < 2:
            return {}
        data = yf.download(tickers, period="3mo", progress=False)["Close"]
        corr = data.corr()
        high_corr_pairs = []
        for i in range(len(tickers)):
            for j in range(i+1, len(tickers)):
                val = corr.iloc[i, j]
                if val > MAX_CORRELATION:
                    high_corr_pairs.append((tickers[i], tickers[j], round(val, 2)))
        return high_corr_pairs
    except:
        return []

def check_sector_concentration(signals):
    sector_counts = {}
    for s in signals:
        sector = s["sector"]
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
    return sector_counts

def apply_risk_rules(strong_signals, current_capital=STARTING_CAPITAL):
    print("=" * 50)
    print("RISK MANAGER")
    print("=" * 50)

    if not strong_signals:
        print("No signals to process")
        return []

    # Check sector concentration
    sector_counts = check_sector_concentration(strong_signals)
    approved = []
    sector_taken = {}

    for signal in strong_signals:
        ticker = signal["ticker"]
        sector = signal["sector"]
        score = signal["score"]

        # Check max positions
        if len(approved) >= MAX_POSITIONS:
            print(f"{ticker}: REJECTED — max positions reached")
            continue

        # Check sector concentration
        if sector_taken.get(sector, 0) >= MAX_SECTOR_POSITIONS:
            print(f"{ticker}: REJECTED — too many {sector} positions")
            continue

        # Calculate position size
        position_size = get_position_size(score, current_capital)

        approved.append({
            "ticker": ticker,
            "sector": sector,
            "score": score,
            "position_size": position_size,
            "position_pct": round(position_size / current_capital * 100, 1)
        })
        sector_taken[sector] = sector_taken.get(sector, 0) + 1

    # Check correlation on approved trades
    if len(approved) > 1:
        tickers = [s["ticker"] for s in approved]
        high_corr = check_correlation(tickers)
        if high_corr:
            print("\nHIGH CORRELATION WARNING:")
            for t1, t2, val in high_corr:
                print(f"  {t1} and {t2} are {val*100:.0f}% correlated — consider removing one")

    print(f"\nAPPROVED TRADES ({len(approved)}):")
    total_exposure = 0
    for s in approved:
        print(f"  {s['ticker']} ({s['sector']}): Score {s['score']} — ${s['position_size']:,.0f} ({s['position_pct']}%)")
        total_exposure += s["position_size"]

    print(f"\nTotal exposure: ${total_exposure:,.0f} ({round(total_exposure/current_capital*100, 1)}% of portfolio)")
    print("=" * 50)

    return approved

if __name__ == "__main__":
    test_signals = [
        {"ticker": "CRWD", "sector": "Backdoor Tech", "score": 8.5},
        {"ticker": "PANW", "sector": "Backdoor Tech", "score": 8.0},
        {"ticker": "FTNT", "sector": "Backdoor Tech", "score": 7.8},
        {"ticker": "ARM", "sector": "Semiconductors", "score": 7.5},
        {"ticker": "NVDA", "sector": "Semiconductors", "score": 7.2},
    ]
    apply_risk_rules(test_signals)
