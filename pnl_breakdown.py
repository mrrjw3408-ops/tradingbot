from collections import defaultdict


def required_win_rate(strategy, desc, credit, max_loss):
    # Share of trades that must win just to break even, if wins pay the max profit and losses the max loss
    try:
        if strategy == "SELL_PUT_SPREAD":
            return max_loss / (max_loss + credit)
        long_k = float(desc.split("$")[1].split("C")[0])
        short_k = float(desc.split("$")[2].split("C")[0])
        debit = abs(credit)
        return debit / (short_k - long_k)
    except Exception:
        return None


def analyze(rows):
    trades = []
    for r in rows:
        if len(r) < 23 or r[19] != "CLOSED":
            continue
        try:
            pnl = float(r[22])
            req = required_win_rate(r[4], r[10], float(r[12]), float(r[13]))
        except Exception:
            continue
        trades.append({"strategy": r[4], "sector": r[3], "day": r[1][:10], "mode": r[6],
                       "regime": r[7], "pnl": pnl, "req": req})

    def show(title, keyfn):
        groups = defaultdict(list)
        for t in trades:
            groups[keyfn(t)].append(t)
        print(f"\n{title}")
        for k, v in sorted(groups.items(), key=lambda kv: sum(t["pnl"] for t in kv[1])):
            pnls = [t["pnl"] for t in v]
            wins = sum(p > 0 for p in pnls)
            reqs = [t["req"] for t in v if t["req"] is not None]
            need = f"  needed ~{sum(reqs)/len(reqs)*100:.0f}% to break even" if reqs else ""
            print(f"  {str(k):<24} n={len(v):<4} win {wins/len(v)*100:4.0f}%  "
                  f"total ${sum(pnls):+,.0f}  avg ${sum(pnls)/len(pnls):+,.0f}{need}")

    allp = [t["pnl"] for t in trades]
    print(f"ALL CLOSED: {len(trades)} trades, total ${sum(allp):+,.0f}, "
          f"win rate {sum(p > 0 for p in allp)/max(len(allp), 1)*100:.0f}%")
    show("By strategy", lambda t: t["strategy"])
    show("By sector", lambda t: t["sector"])
    show("By market regime at entry", lambda t: t["regime"])
    show("By trade mode", lambda t: t["mode"])

    days = defaultdict(list)
    for t in trades:
        days[t["day"]].append(t["pnl"])
    print("\nWorst 8 entry days (a whole day's trades usually move together):")
    for d, v in sorted(days.items(), key=lambda kv: sum(kv[1]))[:8]:
        print(f"  {d}  n={len(v):<3} total ${sum(v):+,.0f}")


if __name__ == "__main__":
    import gspread
    from google.oauth2.service_account import Credentials
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
    opt = gspread.authorize(creds).open("Trading Bot Log").worksheet("Options Paper Trades")
    analyze(opt.get_all_values()[1:])
