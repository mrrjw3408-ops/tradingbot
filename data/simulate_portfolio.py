import gspread
import sys
import os
from collections import defaultdict
from datetime import datetime, timedelta
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from google.oauth2.service_account import Credentials
from config import STARTING_CAPITAL, MAX_POSITIONS, MAX_SECTOR_POSITIONS, MAX_POSITION_PCT, MIN_POSITION_PCT
from agents.options_strategy import STRATEGY_RULES

CONFIDENCE_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "AVOID": 3}


def get_confidence(mode, regime):
    rule = STRATEGY_RULES.get((mode, regime))
    if not rule:
        return "LOW"
    return rule.get("confidence", "LOW")


def load_backtest_rows():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open("Trading Bot Log")
    bt = sheet.worksheet("Backtest Results")
    return bt.get_all_values()


def get_size_pct(score):
    pct = MIN_POSITION_PCT + (min(score, 10) / 10) * (MAX_POSITION_PCT - MIN_POSITION_PCT)
    return min(pct, MAX_POSITION_PCT)


def dedupe_signals(rows):
    """Only keep non-overlapping signals per ticker -- at least 18 days apart."""
    by_ticker = defaultdict(list)

    for row in rows[1:]:
        try:
            if len(row) < 23 or not row[16] or not row[18] or not row[22]:
                continue
            date = datetime.strptime(row[0], '%Y-%m-%d')
            score = float(row[4]) if row[4] else 0
            best_return = float(row[15]) if row[15] else 0
            ret_5d = float(row[12]) if row[12] else None
            ret_10d = float(row[13]) if row[13] else None
            ret_20d = float(row[14]) if row[14] else None

            by_ticker[row[1]].append({
                "date": date,
                "ticker": row[1],
                "sector": row[2],
                "score": score,
                "mode": row[18],
                "regime": row[22],
                "outcome": row[16],
                "best_return": best_return,
                "ret_5d": ret_5d,
                "ret_10d": ret_10d,
                "ret_20d": ret_20d,
            })
        except Exception:
            continue

    deduped = []
    for ticker, trades in by_ticker.items():
        trades.sort(key=lambda x: x["date"])
        last_date = None
        for t in trades:
            if last_date is None or (t["date"] - last_date).days >= 18:
                deduped.append(t)
                last_date = t["date"]

    return deduped


def simulate(deduped_signals, min_score=3.5, capital=STARTING_CAPITAL,
             max_positions=MAX_POSITIONS, max_sector_positions=MAX_SECTOR_POSITIONS,
             hold_days=20, prioritize_confidence=True):
    """
    Walk through signals chronologically, day by day (no lookahead bias).
    Within each day, optionally prioritize HIGH > MEDIUM > LOW confidence
    signals (using STRATEGY_RULES) when multiple compete for limited slots.
    Each position ties up its allocated capital for `hold_days`, then
    realizes its actual ret_20d (or best available) and capital is freed.
    """
    signals = [s for s in deduped_signals if s["score"] >= min_score]
    for s in signals:
        s["confidence"] = get_confidence(s["mode"], s["regime"])

    # Drop AVOID-confidence signals entirely -- matches live strategy behavior
    signals = [s for s in signals if s["confidence"] != "AVOID"]

    if prioritize_confidence:
        signals.sort(key=lambda x: (x["date"], CONFIDENCE_RANK.get(x["confidence"], 9), -x["score"]))
    else:
        signals.sort(key=lambda x: x["date"])

    cash = capital
    open_positions = []
    closed_trades = []
    sector_open_count = defaultdict(int)

    all_dates = sorted(set(s["date"] for s in signals))
    if not all_dates:
        return None

    end_date = all_dates[-1] + timedelta(days=hold_days + 1)
    signal_idx = 0
    equity_curve = []

    day = all_dates[0]
    while day <= end_date:
        # Close any positions whose hold period has ended
        still_open = []
        for pos in open_positions:
            if day >= pos["exit_date"]:
                realized_return = pos["ret_20d"] if pos["ret_20d"] is not None else pos["best_return"]
                pnl_dollars = pos["size"] * (realized_return / 100)
                cash += pos["size"] + pnl_dollars
                sector_open_count[pos["sector"]] -= 1
                closed_trades.append({
                    "ticker": pos["ticker"],
                    "sector": pos["sector"],
                    "entry_date": pos["entry_date"],
                    "exit_date": day,
                    "size": pos["size"],
                    "return_pct": realized_return,
                    "pnl_dollars": pnl_dollars,
                    "confidence": pos["confidence"]
                })
            else:
                still_open.append(pos)
        open_positions = still_open

        # Collect all signals dated today (or earlier, not yet processed) and
        # try to open positions, already sorted by confidence/score priority
        while signal_idx < len(signals) and signals[signal_idx]["date"] <= day:
            sig = signals[signal_idx]
            signal_idx += 1

            if len(open_positions) >= max_positions:
                continue
            if sector_open_count[sig["sector"]] >= max_sector_positions:
                continue

            size_pct = get_size_pct(sig["score"])
            size_dollars = round(cash * size_pct, 2) if cash > 0 else 0
            if size_dollars < 50:
                continue

            cash -= size_dollars
            open_positions.append({
                "ticker": sig["ticker"],
                "sector": sig["sector"],
                "size": size_dollars,
                "entry_date": sig["date"],
                "exit_date": sig["date"] + timedelta(days=hold_days),
                "best_return": sig["best_return"],
                "ret_20d": sig["ret_20d"],
                "confidence": sig["confidence"]
            })
            sector_open_count[sig["sector"]] += 1

        total_equity = cash + sum(p["size"] for p in open_positions)
        equity_curve.append((day, total_equity))

        day += timedelta(days=1)

    # Close out anything still open at the end at its best known return
    for pos in open_positions:
        realized_return = pos["ret_20d"] if pos["ret_20d"] is not None else pos["best_return"]
        pnl_dollars = pos["size"] * (realized_return / 100)
        cash += pos["size"] + pnl_dollars
        closed_trades.append({
            "ticker": pos["ticker"],
            "sector": pos["sector"],
            "entry_date": pos["entry_date"],
            "exit_date": end_date,
            "size": pos["size"],
            "return_pct": realized_return,
            "pnl_dollars": pnl_dollars,
            "confidence": pos["confidence"]
        })

    final_value = cash
    total_return_pct = round((final_value - capital) / capital * 100, 2)
    wins = sum(1 for t in closed_trades if t["return_pct"] > 0)
    losses = sum(1 for t in closed_trades if t["return_pct"] <= 0)
    win_rate = round(wins / len(closed_trades) * 100, 1) if closed_trades else 0
    total_days = (all_dates[-1] - all_dates[0]).days

    by_conf = defaultdict(lambda: {"count": 0, "wins": 0})
    for t in closed_trades:
        by_conf[t["confidence"]]["count"] += 1
        if t["return_pct"] > 0:
            by_conf[t["confidence"]]["wins"] += 1

    return {
        "starting_capital": capital,
        "final_value": round(final_value, 2),
        "total_return_pct": total_return_pct,
        "total_trades": len(closed_trades),
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_days": total_days,
        "equity_curve": equity_curve,
        "closed_trades": closed_trades,
        "by_confidence": dict(by_conf)
    }


def annualize(total_return_pct, total_days):
    if total_days <= 0:
        return 0
    return round((((1 + total_return_pct / 100) ** (365 / total_days)) - 1) * 100, 2)


def print_result(label, result):
    print("\n" + "=" * 55)
    print(f"PORTFOLIO SIMULATION RESULTS — {label}")
    print("=" * 55)
    print(f"Starting Capital:  ${result['starting_capital']:,.2f}")
    print(f"Final Value:       ${result['final_value']:,.2f}")
    print(f"Total Return:      {result['total_return_pct']:+.2f}%")
    print(f"Period:            {result['total_days']} days")
    print(f"Annualized:        {annualize(result['total_return_pct'], result['total_days']):+.2f}%")
    print(f"Total Trades:      {result['total_trades']}")
    print(f"Win Rate:          {result['win_rate']}%  ({result['wins']}W / {result['losses']}L)")
    print("\nBreakdown by confidence tier:")
    for conf, d in result["by_confidence"].items():
        wr = round(d["wins"] / d["count"] * 100, 1) if d["count"] else 0
        print(f"  {conf:<8} {d['count']} trades, {wr}% win rate")
    print("=" * 55)


if __name__ == "__main__":
    print("Loading backtest data from Google Sheets...")
    rows = load_backtest_rows()
    print(f"Total raw rows: {len(rows)-1}")

    print("Deduplicating overlapping signals (18+ day gap per ticker)...")
    deduped = dedupe_signals(rows)
    print(f"Deduplicated, non-overlapping signals: {len(deduped)}")

    print("\nRunning NAIVE (chronological, no prioritization) simulation...")
    naive_result = simulate(deduped, min_score=3.5, prioritize_confidence=False)
    if naive_result:
        print_result("NAIVE (first-come-first-served)", naive_result)

    print("\nRunning PRIORITIZED (confidence-ranked) simulation...")
    prioritized_result = simulate(deduped, min_score=3.5, prioritize_confidence=True)
    if prioritized_result:
        print_result("PRIORITIZED (highest confidence first)", prioritized_result)
        