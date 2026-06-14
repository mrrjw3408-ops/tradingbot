import yfinance as yf
import pandas as pd
import gspread
import time
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TICKERS, SECTORS


def clean(val):
    try:
        if val != val:
            return 0
        return round(float(val), 2)
    except:
        return 0


def get_trading_days(start_date, end_date):
    dates = pd.date_range(start=start_date, end=end_date, freq='B')
    return [d.strftime('%Y-%m-%d') for d in dates]


def calculate_signals(df, as_of_date, sector, etf_return):
    try:
        hist = df[df.index.strftime('%Y-%m-%d') <= as_of_date].copy()
        if len(hist) < 200:
            return None

        closes = hist['Close'].dropna()
        delta = closes.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / loss
        rsi = float(100 - (100 / (1 + rs.iloc[-1])))

        ma20 = closes.rolling(20).mean()
        bb_upper = ma20 + 2 * closes.rolling(20).std()
        bb_lower = ma20 - 2 * closes.rolling(20).std()

        ema12 = closes.ewm(span=12).mean()
        ema26 = closes.ewm(span=26).mean()
        macd = ema12 - ema26
        signal_line = macd.ewm(span=9).mean()

        ma50 = closes.rolling(50).mean()
        ma200 = closes.rolling(200).mean()
        vol_avg = hist['Volume'].rolling(20).mean()

        price = float(closes.iloc[-1])
        bb_low = float(bb_lower.iloc[-1])
        bb_up = float(bb_upper.iloc[-1])
        ma50_val = float(ma50.iloc[-1])
        ma200_val = float(ma200.iloc[-1])
        macd_val = float(macd.iloc[-1])
        macd_sig = float(signal_line.iloc[-1])
        vol_now = float(hist['Volume'].iloc[-1])
        vol_avg_val = float(vol_avg.iloc[-1])

        if any(v != v for v in [price, rsi, macd_val, macd_sig, bb_low, bb_up, ma50_val, ma200_val]):
            return None

        volume_spike = vol_now > vol_avg_val

        lookback = min(20, len(closes) - 1)
        stock_return = (closes.iloc[-1] / closes.iloc[-lookback] - 1) * 100
        rel_strength = float(stock_return) - float(etf_return)
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

        if rsi < 40 and price <= bb_low:
            trade_mode = "MEAN_REVERSION"
            mr_weight = 1.5
            trend_weight = 0.5
        elif ma50_val > ma200_val and price > ma50_val:
            trade_mode = "MOMENTUM"
            mr_weight = 0.5
            trend_weight = 1.5
        else:
            trade_mode = "NEUTRAL"
            mr_weight = 1.0
            trend_weight = 1.0

        weighted_score = (mr_score * mr_weight) + (trend_score * trend_weight) + sector_score + vol_score
        score = round(min(weighted_score, 10), 2)

        return {
            "price": price,
            "score": score,
            "trend_score": trend_score,
            "sector_score": sector_score,
            "mr_score": mr_score,
            "vol_score": vol_score,
            "rsi": rsi,
            "trade_mode": trade_mode,
            "bb_low": bb_low,
            "bb_up": bb_up
        }

    except:
        return None


def get_future_price(df, as_of_date, days_forward):
    try:
        future_date = (datetime.strptime(as_of_date, '%Y-%m-%d') + timedelta(days=days_forward)).strftime('%Y-%m-%d')
        future_data = df[df.index.strftime('%Y-%m-%d') > as_of_date]
        future_data = future_data[future_data.index.strftime('%Y-%m-%d') <= future_date]
        if future_data.empty:
            return None
        return float(future_data['Close'].dropna().iloc[-1])
    except:
        return None


def get_regime_on_date(spy_closes, spy_ma50_series, vix_df, as_of_date):
    try:
        spy_hist = spy_closes[spy_closes.index.strftime('%Y-%m-%d') <= as_of_date]
        ma50_hist = spy_ma50_series[spy_ma50_series.index.strftime('%Y-%m-%d') <= as_of_date]
        vix_hist = vix_df[vix_df.index.strftime('%Y-%m-%d') <= as_of_date]

        if spy_hist.empty or ma50_hist.empty:
            return None, None, None, "UNKNOWN"

        spy_price = float(spy_hist.iloc[-1])
        spy_ma50 = float(ma50_hist.iloc[-1])
        vix = float(vix_hist["Close"].iloc[-1]) if not vix_hist.empty else 20.0

        score = 0
        if spy_price > spy_ma50:
            score += 1
        if vix < 15:
            score += 1
        elif vix > 25:
            score -= 1

        if score >= 2:
            regime = "BULL"
        elif score <= 0:
            regime = "BEAR"
        else:
            regime = "NEUTRAL"

        return spy_price, spy_ma50, vix, regime
    except:
        return None, None, None, "UNKNOWN"


def run_backtest(start_date, end_date, window_name="Backtest"):
    print(f"\n{'='*50}")
    print(f"BACKTESTER — {window_name}")
    print(f"Period: {start_date} to {end_date}")
    print(f"{'='*50}\n")

    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open("Trading Bot Log")
    backtest_sheet = sheet.worksheet("Backtest Results")

    trading_days = get_trading_days(start_date, end_date)
    print(f"Trading days to process: {len(trading_days)}")

    print("Fetching sector ETF data...")
    buffer_start = (datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=300)).strftime('%Y-%m-%d')
    buffer_end = (datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=30)).strftime('%Y-%m-%d')

    etf_returns = {}
    for sector, etf in SECTORS.items():
        try:
            df = yf.Ticker(etf).history(start=start_date, end=end_date)
            closes = df['Close'].dropna()
            if len(closes) > 20:
                ret = (closes.iloc[-1] / closes.iloc[-20] - 1) * 100
                etf_returns[sector] = float(ret) if ret == ret else 0
            else:
                etf_returns[sector] = 0
        except:
            etf_returns[sector] = 0

    print("Fetching SPY and VIX history for regime detection...")
    spy_df = yf.Ticker("SPY").history(start=buffer_start, end=buffer_end)
    spy_df.index = spy_df.index.tz_localize(None) if spy_df.index.tzinfo else spy_df.index
    spy_closes = spy_df["Close"].dropna()
    spy_ma50_series = spy_closes.rolling(50).mean()

    vix_df = yf.Ticker("^VIX").history(start=buffer_start, end=buffer_end)
    vix_df.index = vix_df.index.tz_localize(None) if vix_df.index.tzinfo else vix_df.index

    total_logged = 0
    total_signals = 0
    mode_counts = {"MEAN_REVERSION": 0, "MOMENTUM": 0, "NEUTRAL": 0}
    regime_counts = {"BULL": 0, "NEUTRAL": 0, "BEAR": 0, "UNKNOWN": 0}

    for sector, tickers in TICKERS.items():
        print(f"\nProcessing {sector}...")
        etf_ret = etf_returns.get(sector, 0)

        for ticker in tickers:
            try:
                df = yf.Ticker(ticker).history(start=buffer_start, end=buffer_end)

                if df.empty or len(df) < 200:
                    continue

                df.index = df.index.tz_localize(None) if df.index.tzinfo else df.index

                sample_days = trading_days[::5]

                for date in sample_days:
                    try:
                        signals = calculate_signals(df, date, sector, etf_ret)
                        if signals is None:
                            continue

                        spy_price, spy_ma50, vix, regime = get_regime_on_date(
                            spy_closes, spy_ma50_series, vix_df, date
                        )

                        price = signals["price"]
                        score = signals["score"]
                        trade_mode = signals["trade_mode"]
                        mode_counts[trade_mode] = mode_counts.get(trade_mode, 0) + 1
                        regime_counts[regime] = regime_counts.get(regime, 0) + 1

                        price_5d = get_future_price(df, date, 7)
                        price_10d = get_future_price(df, date, 14)
                        price_20d = get_future_price(df, date, 28)

                        ret_5d = round((price_5d / price - 1) * 100, 2) if price_5d else None
                        ret_10d = round((price_10d / price - 1) * 100, 2) if price_10d else None
                        ret_20d = round((price_20d / price - 1) * 100, 2) if price_20d else None

                        returns = [r for r in [ret_5d, ret_10d, ret_20d] if r is not None]
                        best_return = round(max(returns), 2) if returns else None
                        outcome = "WIN" if best_return and best_return >= 3 else "LOSS" if best_return is not None else ""

                        row = [
                            date, ticker, sector,
                            clean(price),
                            clean(score),
                            clean(signals["trend_score"]),
                            clean(signals["sector_score"]),
                            clean(signals["mr_score"]),
                            clean(signals["vol_score"]),
                            clean(price_5d) if price_5d else "",
                            clean(price_10d) if price_10d else "",
                            clean(price_20d) if price_20d else "",
                            clean(ret_5d) if ret_5d is not None else "",
                            clean(ret_10d) if ret_10d is not None else "",
                            clean(ret_20d) if ret_20d is not None else "",
                            clean(best_return) if best_return is not None else "",
                            outcome,
                            window_name,
                            trade_mode,
                            clean(spy_price) if spy_price else "",
                            clean(spy_ma50) if spy_ma50 else "",
                            clean(vix) if vix else "",
                            regime
                        ]

                        backtest_sheet.append_row(row)
                        total_logged += 1

                        if score >= 3.5:
                            total_signals += 1
                            print(f"  {ticker} {date}: Score {score} | Mode: {trade_mode} | Regime: {regime} | VIX: {vix:.1f} | Best: {best_return}% | {outcome}")

                        time.sleep(1.5)

                    except Exception as e:
                        continue

            except Exception as e:
                print(f"  {ticker}: error — {e}")
                continue

    print(f"\n{'='*50}")
    print(f"BACKTEST COMPLETE — {window_name}")
    print(f"Total rows logged: {total_logged}")
    print(f"High score signals (3.5+): {total_signals}")
    print(f"Trade modes: {mode_counts}")
    print(f"Regimes seen: {regime_counts}")
    print(f"{'='*50}\n")
    return total_logged


if __name__ == "__main__":
    windows = [
        ("2025-09-01", "2025-11-30", "Window 1 - Fall 2025"),
        ("2025-06-01", "2025-08-31", "Window 2 - Summer 2025"),
        ("2025-03-01", "2025-05-31", "Window 3 - Spring 2025"),
    ]

    for start, end, name in windows:
        run_backtest(start, end, name)
        print(f"Waiting 30 seconds before next window...")
        time.sleep(30)

    print("\nAll backtest windows complete!")
    print("Check your Backtest Results tab in Google Sheets!")
    