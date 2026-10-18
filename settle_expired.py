import sys
import csv
from datetime import datetime, timedelta

WRITE = "--write" in sys.argv


def parse_spread(strategy, desc):
    # Same parsing the bot uses: "Sell $45.0P / Buy $35.0P" or "Buy $500.0C / Sell $520.0C"
    if strategy == "SELL_PUT_SPREAD":
        short_k = float(desc.split("$")[1].split("P")[0])
        long_k = float(desc.split("$")[2].split("P")[0])
    else:
        long_k = float(desc.split("$")[1].split("C")[0])
        short_k = float(desc.split("$")[2].split("C")[0])
    return short_k, long_k


def settle(strategy, short_k, long_k, S, entry_credit, contracts):
    # Value of the spread at expiration (intrinsic value only) and resulting P&L
    width = abs(short_k - long_k)
    if strategy == "SELL_PUT_SPREAD":
        value = min(max(short_k - S, 0), width)
        pnl = (entry_credit - value) * contracts * 100
    else:
        value = min(max(S - long_k, 0), width)
        pnl = (value - abs(entry_credit)) * contracts * 100
    return round(value, 2), round(pnl, 2)


def main():
    import gspread
    import yfinance as yf
    from google.oauth2.service_account import Credentials

    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
    client = gspread.authorize(creds)
    opt = client.open("Trading Bot Log").worksheet("Options Paper Trades")
    rows = opt.get_all_values()

    backup = "options_trades_backup_" + datetime.now().strftime("%Y%m%d_%H%M") + ".csv"
    with open(backup, "w", newline="") as f:
        csv.writer(f).writerows(rows)
    print(f"Backed up the whole sheet to {backup}\n")

    today = datetime.now().date()
    price_cache = {}

    def close_on_or_before(ticker, exp):
        key = (ticker, exp)
        if key in price_cache:
            return price_cache[key]
        df = yf.Ticker(ticker).history(
            start=(exp - timedelta(days=7)).isoformat(),
            end=(exp + timedelta(days=1)).isoformat(),
        )
        closes = df["Close"].dropna()
        closes = closes[[d.date() <= exp for d in closes.index]]
        if closes.empty:
            raise ValueError("no price data")
        price_cache[key] = float(closes.iloc[-1])
        return price_cache[key]

    updates, failed = [], []
    wins = losses = 0
    total = 0.0

    for i, row in enumerate(rows[1:], start=2):
        if len(row) < 20 or row[19] != "OPEN":
            continue
        try:
            exp = datetime.strptime(row[9], "%Y-%m-%d").date()
            if exp >= today:
                continue
            ticker, strategy = row[2], row[4]
            contracts = int(row[11]) if row[11] else 1
            entry_credit = float(row[12]) if row[12] else 0
            max_loss = float(row[13]) if row[13] else 0
            short_k, long_k = parse_spread(strategy, row[10])
            S = close_on_or_before(ticker, exp)
            value, pnl = settle(strategy, short_k, long_k, S, entry_credit, contracts)
            pnl_pct = round(pnl / (max_loss * contracts * 100) * 100, 1) if max_loss > 0 else 0
            updates.append({
                "range": f"T{i}:X{i}",
                "values": [["CLOSED", f"{exp} 16:00", value, pnl, pnl_pct]],
            })
            total += pnl
            wins += pnl > 0
            losses += pnl <= 0
            print(f"row {i:<4} {ticker:<6} {strategy:<17} exp {exp} | {short_k:g}/{long_k:g} | "
                  f"underlying ${S:.2f} | spread worth ${value:.2f} | P&L ${pnl:+,.2f}")
        except Exception as e:
            failed.append((i, row[2], str(e)))
            print(f"row {i:<4} {row[2]:<6} COULD NOT SETTLE: {e}")

    print(f"\nExpired trades settled: {len(updates)} ({wins} wins / {losses} losses), "
          f"total P&L ${total:+,.2f}")
    if failed:
        print(f"Could not price {len(failed)} trades (left OPEN): " + ", ".join(f"row {r} {t}" for r, t, _ in failed))

    if not WRITE:
        print("\nDRY RUN: nothing was written to the sheet. Re-run with --write to apply.")
        return
    for k in range(0, len(updates), 40):
        opt.batch_update(updates[k:k + 40])
    print("\nWritten to the sheet.")


if __name__ == "__main__":
    main()
