import yfinance as yf
import sys
import os
from datetime import datetime, timedelta
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import STARTING_CAPITAL, MAX_POSITION_PCT

# Rebuilt from DEDUPLICATED, score>=3.5 data (not raw overlapping rows):
# MOMENTUM_BULL    = 57.7% WR, n=220  -> only combination with real, sufficient edge
# NEUTRAL_BULL     = 66.7% WR, n=12   -> promising but far too small a sample to trust
# NEUTRAL_NEUTRAL  = 56.3% WR, n=183  -> modest edge, decent sample
# MOMENTUM_NEUTRAL = 53.9% WR, n=1255 -> barely above coinflip, large sample
# NEUTRAL_BEAR     = 37.5% WR, n=24   -> BELOW coinflip, do not trust the "HIGH" label
# MEAN_REVERSION_*  = essentially no qualifying independent trades after dedup

STRATEGY_RULES = {
    ("MOMENTUM", "BULL"):          {"strategy": "BUY_CALL_SPREAD", "confidence": "HIGH",   "size_pct": 0.05},
    ("NEUTRAL", "NEUTRAL"):        {"strategy": "SELL_PUT_SPREAD", "confidence": "MEDIUM", "size_pct": 0.03},
    ("MOMENTUM", "NEUTRAL"):       {"strategy": "SELL_PUT_SPREAD", "confidence": "LOW",    "size_pct": 0.02},
    ("NEUTRAL", "BULL"):           {"strategy": "SELL_PUT_SPREAD", "confidence": "LOW",    "size_pct": 0.02},  # promising, too few trades to size up yet
    ("NEUTRAL", "BEAR"):           {"strategy": "NO_TRADE",        "confidence": "AVOID",  "size_pct": 0.00},  # was wrongly HIGH -- 37.5% WR
    ("MEAN_REVERSION", "BEAR"):    {"strategy": "NO_TRADE",        "confidence": "AVOID",  "size_pct": 0.00},  # insufficient independent samples
    ("MEAN_REVERSION", "NEUTRAL"): {"strategy": "NO_TRADE",        "confidence": "AVOID",  "size_pct": 0.00},  # 0% WR, n=2 -- worthless sample
    ("MEAN_REVERSION", "BULL"):    {"strategy": "NO_TRADE",        "confidence": "AVOID",  "size_pct": 0.00},  # no qualifying data
    ("MOMENTUM", "BEAR"):          {"strategy": "NO_TRADE",        "confidence": "AVOID",  "size_pct": 0.00},  # confirmed weak earlier
}

def get_options_chain(ticker):
    try:
        stock = yf.Ticker(ticker)
        expirations = stock.options
        if not expirations:
            return None, None

        today = datetime.now()
        target_date = today + timedelta(days=30)

        best_exp = None
        best_diff = float('inf')
        for exp in expirations:
            exp_date = datetime.strptime(exp, '%Y-%m-%d')
            days_out = (exp_date - today).days
            if days_out < 14:
                continue
            diff = abs((exp_date - target_date).days)
            if diff < best_diff:
                best_diff = diff
                best_exp = exp

        if not best_exp:
            return None, None

        chain = stock.option_chain(best_exp)
        return chain, best_exp
    except:
        return None, None


def find_put_spread(ticker, price, chain, expiration):
    try:
        puts = chain.puts
        if puts.empty:
            return None

        target_strike = round(price * 0.95)
        available = puts[puts['strike'] <= price].copy()
        if available.empty:
            return None

        available['strike_diff'] = abs(available['strike'] - target_strike)
        short_put = available.nsmallest(1, 'strike_diff').iloc[0]
        short_strike = short_put['strike']
        short_premium = round((short_put['bid'] + short_put['ask']) / 2, 2)

        if short_premium <= 0:
            return None

        long_strike_target = round(short_strike * 0.95)
        long_puts = puts[abs(puts['strike'] - long_strike_target) < 10]
        if long_puts.empty:
            long_puts = puts[puts['strike'] < short_strike]
            if long_puts.empty:
                return None
            long_put = long_puts.iloc[-1]
        else:
            long_put = long_puts.iloc[0]

        long_premium = round((long_put['bid'] + long_put['ask']) / 2, 2)
        long_strike = long_put['strike']

        net_credit = round(short_premium - long_premium, 2)
        if net_credit <= 0:
            return None

        max_loss = round((short_strike - long_strike) - net_credit, 2)
        spread_width = round(short_strike - long_strike, 2)
        breakeven = round(short_strike - net_credit, 2)
        return_on_risk = round((net_credit / max_loss) * 100, 1) if max_loss > 0 else 0

        return {
            "type": "BULL_PUT_SPREAD",
            "expiration": expiration,
            "short_strike": short_strike,
            "long_strike": long_strike,
            "net_credit": net_credit,
            "max_loss": max_loss,
            "max_profit": net_credit,
            "spread_width": spread_width,
            "breakeven": breakeven,
            "return_on_risk": return_on_risk,
            "short_iv": round(float(short_put.get('impliedVolatility', 0)) * 100, 1),
        }
    except Exception as e:
        return None


def find_call_spread(ticker, price, chain, expiration):
    try:
        calls = chain.calls
        if calls.empty:
            return None

        target_strike = round(price * 1.05)
        available = calls[calls['strike'] >= price].copy()
        if available.empty:
            return None

        available['strike_diff'] = abs(available['strike'] - target_strike)
        long_call = available.nsmallest(1, 'strike_diff').iloc[0]
        long_strike = long_call['strike']
        long_premium = round((long_call['bid'] + long_call['ask']) / 2, 2)

        if long_premium <= 0:
            return None

        short_strike_target = round(long_strike * 1.05)
        short_calls = calls[abs(calls['strike'] - short_strike_target) < 10]
        if short_calls.empty:
            short_calls = calls[calls['strike'] > long_strike]
            if short_calls.empty:
                return None
            short_call = short_calls.iloc[0]
        else:
            short_call = short_calls.iloc[0]

        short_premium = round((short_call['bid'] + short_call['ask']) / 2, 2)
        short_strike = short_call['strike']

        net_debit = round(long_premium - short_premium, 2)
        if net_debit <= 0:
            return None

        max_profit = round((short_strike - long_strike) - net_debit, 2)
        max_loss = net_debit
        breakeven = round(long_strike + net_debit, 2)
        return_on_risk = round((max_profit / max_loss) * 100, 1) if max_loss > 0 else 0

        return {
            "type": "BULL_CALL_SPREAD",
            "expiration": expiration,
            "long_strike": long_strike,
            "short_strike": short_strike,
            "net_debit": net_debit,
            "max_profit": max_profit,
            "max_loss": max_loss,
            "breakeven": breakeven,
            "return_on_risk": return_on_risk,
            "long_iv": round(float(long_call.get('impliedVolatility', 0)) * 100, 1),
        }
    except:
        return None


def get_earnings_date(ticker):
    try:
        stock = yf.Ticker(ticker)
        calendar = stock.calendar
        if calendar is None:
            return None
        if hasattr(calendar, 'empty') and calendar.empty:
            return None
        if isinstance(calendar, dict):
            earnings = calendar.get('Earnings Date', None)
            if earnings:
                if isinstance(earnings, list):
                    return earnings[0].date() if hasattr(earnings[0], 'date') else None
                return earnings.date() if hasattr(earnings, 'date') else None
        return None
    except:
        return None


def analyze_trade(ticker, sector, score, trade_mode, regime, price, capital=STARTING_CAPITAL):
    print(f"\nAnalyzing {ticker} — Score: {score} | Mode: {trade_mode} | Regime: {regime} | Price: ${price:.2f}")

    key = (trade_mode, regime)
    rules = STRATEGY_RULES.get(key, {"strategy": "NO_TRADE", "confidence": "UNKNOWN", "size_pct": 0.00})

    strategy = rules["strategy"]
    confidence = rules["confidence"]
    size_pct = rules["size_pct"]

    if strategy == "NO_TRADE":
        print(f"  SKIP — {trade_mode} + {regime} has poor historical win rate")
        return None

    earnings = get_earnings_date(ticker)
    if earnings:
        days_to_earnings = (earnings - datetime.now().date()).days
        if 0 < days_to_earnings < 21:
            print(f"  SKIP — Earnings in {days_to_earnings} days")
            return None

    chain, expiration = get_options_chain(ticker)
    if chain is None:
        print(f"  SKIP — Could not fetch options chain")
        return None

    print(f"  Expiration selected: {expiration}")

    if strategy == "SELL_PUT_SPREAD":
        spread = find_put_spread(ticker, price, chain, expiration)
    else:
        spread = find_call_spread(ticker, price, chain, expiration)

    if spread is None:
        print(f"  SKIP — Could not find suitable spread")
        return None

    max_loss_per_contract = spread.get('max_loss', 0) * 100
    if max_loss_per_contract <= 0:
        print(f"  SKIP — Invalid spread pricing")
        return None

    position_dollars = round(capital * size_pct, 2)
    contracts = max(1, int(position_dollars / max_loss_per_contract))
    total_risk = round(contracts * max_loss_per_contract, 2)
    credit_or_debit = spread.get('net_credit', spread.get('net_debit', 0))
    total_credit = round(contracts * credit_or_debit * 100, 2)

    result = {
        "ticker": ticker,
        "sector": sector,
        "score": score,
        "trade_mode": trade_mode,
        "regime": regime,
        "price": price,
        "strategy": strategy,
        "confidence": confidence,
        "spread": spread,
        "contracts": contracts,
        "total_risk": total_risk,
        "total_credit": total_credit,
        "position_pct": round(size_pct * 100, 1),
        "earnings_date": str(earnings) if earnings else "None found"
    }

    print(f"  Strategy: {strategy} ({confidence} confidence)")
    if strategy == "SELL_PUT_SPREAD":
        print(f"  Sell ${spread['short_strike']}P / Buy ${spread['long_strike']}P")
        print(f"  Credit: ${spread['net_credit']} | Max Loss: ${spread['max_loss']} | ROR: {spread['return_on_risk']}%")
        print(f"  Breakeven: ${spread['breakeven']} | IV: {spread.get('short_iv', 0)}%")
    else:
        print(f"  Buy ${spread['long_strike']}C / Sell ${spread['short_strike']}C")
        print(f"  Debit: ${spread['net_debit']} | Max Profit: ${spread['max_profit']} | ROR: {spread['return_on_risk']}%")
        print(f"  Breakeven: ${spread['breakeven']} | IV: {spread.get('long_iv', 0)}%")
    print(f"  Contracts: {contracts} | Total Risk: ${total_risk} | Size: {size_pct*100}%")
    print(f"  Earnings: {result['earnings_date']}")

    return result


def analyze_batch(signals, regime, capital=STARTING_CAPITAL):
    print("=" * 55)
    print(f"OPTIONS STRATEGY AGENT")
    print(f"Regime: {regime} | Capital: ${capital:,.0f}")
    print("=" * 55)

    approved = []
    skipped = []

    for signal in signals:
        result = analyze_trade(
            signal["ticker"],
            signal["sector"],
            signal["score"],
            signal.get("trade_mode", "NEUTRAL"),
            regime,
            signal["price"],
            capital
        )
        if result:
            approved.append(result)
        else:
            skipped.append(signal["ticker"])

    print(f"\n{'='*55}")
    print(f"APPROVED OPTIONS TRADES: {len(approved)}")
    print(f"SKIPPED: {len(skipped)}")
    if skipped:
        print(f"Skipped: {', '.join(skipped)}")
    print("=" * 55)

    return approved


if __name__ == "__main__":
    aapl_price = yf.Ticker("AAPL").fast_info.last_price
    nvda_price = yf.Ticker("NVDA").fast_info.last_price
    crwd_price = yf.Ticker("CRWD").fast_info.last_price

    test_signals = [
        {"ticker": "AAPL", "sector": "Backdoor Tech", "score": 4.0, "trade_mode": "MEAN_REVERSION", "price": aapl_price},
        {"ticker": "NVDA", "sector": "Semiconductors", "score": 3.5, "trade_mode": "MOMENTUM", "price": nvda_price},
        {"ticker": "CRWD", "sector": "Backdoor Tech", "score": 4.5, "trade_mode": "MEAN_REVERSION", "price": crwd_price},
    ]

    analyze_batch(test_signals, "BEAR")
    