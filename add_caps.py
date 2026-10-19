p = "agents/options_paper.py"
s = open(p).read()
anchor = '        options_sheet = sheet.worksheet("Options Paper Trades")\n        spread = trade["spread"]\n'
if "already has an open paper options position" in s:
    raise SystemExit("Already patched - nothing changed")
if s.count(anchor) != 1:
    raise SystemExit("Could not find the expected lines in log_trade - nothing changed")
guard = anchor + '''
        try:
            from config import MAX_POSITIONS, MAX_SECTOR_POSITIONS
        except Exception:
            MAX_POSITIONS, MAX_SECTOR_POSITIONS = 10, 2
        open_rows = [r for r in options_sheet.get_all_values()[1:] if len(r) > 19 and r[19] == "OPEN"]
        if any(r[2] == trade["ticker"] for r in open_rows):
            print(f"Skipped {trade['ticker']}: already has an open paper options position")
            return None
        if len(open_rows) >= MAX_POSITIONS:
            print(f"Skipped {trade['ticker']}: {len(open_rows)} open positions (max {MAX_POSITIONS})")
            return None
        if sum(1 for r in open_rows if r[3] == trade["sector"]) >= MAX_SECTOR_POSITIONS:
            print(f"Skipped {trade['ticker']}: sector {trade['sector']} already at {MAX_SECTOR_POSITIONS} open positions")
            return None
'''
open(p, "w").write(s.replace(anchor, guard))
print("Patched: options trades now respect one-per-ticker, MAX_POSITIONS and MAX_SECTOR_POSITIONS")
