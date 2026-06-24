import yfinance as yf
import time
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import VIX_LOW, VIX_HIGH, BREADTH_BULL, BREADTH_BEAR, YIELD_CURVE_FLAT, SECTORS

def get_vix_score():
    for attempt in range(3):
        try:
            vix = yf.Ticker("^VIX")
            vix_price = vix.fast_info.last_price
            if not vix_price or vix_price != vix_price or vix_price <= 0:
                raise ValueError("bad VIX price")
            if vix_price < VIX_LOW:
                return 1, vix_price, "BULLISH"
            elif vix_price > VIX_HIGH:
                return -1, vix_price, "BEARISH"
            else:
                return 0, vix_price, "NEUTRAL"
        except Exception:
            time.sleep(2)
    return 0, None, "UNKNOWN"

def get_spy_score():
    for attempt in range(3):
        try:
            df = yf.Ticker("SPY").history(period="1y")
            closes = df["Close"].dropna()
            if len(closes) < 200:
                raise ValueError("insufficient SPY data")
            price = float(closes.iloc[-1])
            ma50 = float(closes.rolling(50).mean().iloc[-1])
            ma200 = float(closes.rolling(200).mean().iloc[-1])
            if not price or price != price or price <= 0:
                raise ValueError("bad SPY price")
            if price > ma50 and ma50 > ma200:
                return 1, price, ma50, ma200, "BULLISH"
            elif price > ma200:
                return 0, price, ma50, ma200, "NEUTRAL"
            else:
                return -1, price, ma50, ma200, "BEARISH"
        except Exception:
            time.sleep(2)
    return 0, None, None, None, "UNKNOWN"

def get_sector_rotation_score():
    try:
        growth_etfs = ["SOXX", "XLK"]
        defensive_etfs = ["XLU", "XLP", "XLV"]
        
        growth_returns = []
        defensive_returns = []
        
        for etf in growth_etfs:
            df = yf.Ticker(etf).history(period="1mo")
            if not df.empty:
                ret = (df["Close"].iloc[-1] / df["Close"].iloc[-20] - 1) * 100
                growth_returns.append(ret)
        
        for etf in defensive_etfs:
            df = yf.Ticker(etf).history(period="1mo")
            if not df.empty:
                ret = (df["Close"].iloc[-1] / df["Close"].iloc[-20] - 1) * 100
                defensive_returns.append(ret)
        
        avg_growth = sum(growth_returns) / len(growth_returns) if growth_returns else 0
        avg_defensive = sum(defensive_returns) / len(defensive_returns) if defensive_returns else 0
        
        if avg_growth > avg_defensive + 2:
            return 1, avg_growth, avg_defensive, "BULLISH - Growth leading"
        elif avg_defensive > avg_growth + 2:
            return -1, avg_growth, avg_defensive, "BEARISH - Defensives leading"
        else:
            return 0, avg_growth, avg_defensive, "NEUTRAL - Mixed rotation"
    except:
        return 0, 0, 0, "UNKNOWN"

def get_yield_curve_score():
    try:
        tnx = yf.Ticker("^TNX").fast_info.last_price
        irx = yf.Ticker("^IRX").fast_info.last_price
        spread = tnx - irx
        if spread > YIELD_CURVE_FLAT:
            return 1, spread, "BULLISH - Normal curve"
        elif spread < -YIELD_CURVE_FLAT:
            return -1, spread, "BEARISH - Inverted"
        else:
            return 0, spread, "NEUTRAL - Flat"
    except:
        return 0, 0, "UNKNOWN"

def get_breadth_score():
    try:
        advance_tickers = ["SPY", "QQQ", "IWM", "DIA"]
        advancing = 0
        total = 0
        for t in advance_tickers:
            df = yf.Ticker(t).history(period="5d")
            if not df.empty:
                total += 1
                if df["Close"].iloc[-1] > df["Close"].iloc[-2]:
                    advancing += 1
        pct = (advancing / total * 100) if total > 0 else 50
        if pct >= BREADTH_BULL:
            return 1, pct, "BULLISH"
        elif pct <= BREADTH_BEAR:
            return -1, pct, "BEARISH"
        else:
            return 0, pct, "NEUTRAL"
    except:
        return 0, 50, "UNKNOWN"

def get_regime():
    print("=" * 50)
    print("MARKET REGIME ANALYSIS")
    print("=" * 50)

    vix_score, vix_val, vix_label = get_vix_score()
    spy_score, spy_price, ma50, ma200, spy_label = get_spy_score()
    rotation_score, growth_ret, def_ret, rotation_label = get_sector_rotation_score()
    yield_score, spread, yield_label = get_yield_curve_score()
    breadth_score, breadth_pct, breadth_label = get_breadth_score()

    print(f"VIX:            {vix_val:.1f} — {vix_label}" if vix_val is not None else "VIX:            UNAVAILABLE")
    print(f"SPY:            ${spy_price:.2f} | 50MA: ${ma50:.2f} | 200MA: ${ma200:.2f} — {spy_label}" if spy_price is not None else "SPY:            UNAVAILABLE")
    print(f"Sector Rotation: Growth {growth_ret:.1f}% vs Defensive {def_ret:.1f}% — {rotation_label}")
    print(f"Yield Curve:    Spread {spread:.2f}% — {yield_label}")
    print(f"Breadth:        {breadth_pct:.0f}% advancing — {breadth_label}")

    total_score = vix_score + spy_score + rotation_score + yield_score + breadth_score

    if total_score >= 3:
        regime = "BULL"
        threshold_adjustment = 0
    elif total_score >= 0:
        regime = "NEUTRAL"
        threshold_adjustment = 1
    else:
        regime = "BEAR"
        threshold_adjustment = 2

    print(f"\nREGIME SCORE: {total_score}/5")
    print(f"MARKET REGIME: {regime}")
    print(f"THRESHOLD ADJUSTMENT: +{threshold_adjustment} points")
    print("=" * 50)

    return {
    "regime": regime,
    "score": total_score,
    "threshold_adjustment": threshold_adjustment,
    "vix": vix_val if vix_val is not None else 0,
    "spy": spy_price if spy_price is not None else 0,
    "breadth": breadth_pct,
    "rotation": rotation_label,
    "yield_curve": spread
}

if __name__ == "__main__":
    get_regime()
