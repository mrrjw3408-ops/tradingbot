import yfinance as yf
import gspread
import time
import sys
import os
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import STARTING_CAPITAL

def get_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open("Trading Bot Log")
    return sheet

def log_trade(trade):
    try:
        sheet = get_sheets()
        options_sheet = sheet.worksheet("Options Paper Trades")
        spread = trade["spread"]

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        trade_id = f"OPT-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        if trade["strategy"] == "SELL_PUT_SPREAD":
            short_strike = spread["short_strike"]
            long_strike = spread["long_strike"]
            credit_debit = spread["net_credit"]
            max_loss = spread["max_loss"]
            breakeven = spread["breakeven"]
            ror = spread["return_on_risk"]
            spread_desc = f"Sell ${short_strike}P / Buy ${long_strike}P"
        else:
            short_strike = spread["short_strike"]
            long_strike = spread["long_strike"]
            credit_debit = -spread["net_debit"]
            max_loss = spread["max_loss"]
            breakeven = spread["breakeven"]
            ror = spread["return_on_risk"]
            spread_desc = f"Buy ${long_strike}C / Sell ${short_strike}C"

        row = [
            trade_id,
            now,
            trade["ticker"],
            trade["sector"],
            trade["strategy"],
            trade["confidence"],
            trade["trade_mode"],
            trade["regime"],
            round(trade["price"], 2),
            spread["expiration"],
            spread_desc,
            trade["contracts"],
            round(credit_debit, 2),
            round(max_loss, 2),
            round(trade["total_risk"], 2),
            round(trade["total_credit"], 2),
            round(ror, 1),
            round(breakeven, 2),
            trade["score"],
            "OPEN",
            "",  # exit date
            "",  # exit price
            "",  # pnl
            "",  # pnl pct
            trade["earnings_date"]
        ]

        options_sheet.append_row(row)
        print(f"Logged paper trade: {trade_id} — {trade['ticker']} {spread_desc}")
        return trade_id

    except Exception as e:
        print(f"Error logging trade: {e}")
        return None

def check_open_trades():
    try:
        sheet = get_sheets()
        options_sheet = sheet.worksheet("Options Paper Trades")
        rows = options_sheet.get_all_values()

        if len(rows) < 2:
            print("No open trades to check")
            return

        print(f"\nChecking {len(rows)-1} paper options trades...")
        today = datetime.now().date()

        for i, row in enumerate(rows[1:], start=2):
            try:
                if len(row) < 20 or row[19] != "OPEN":
                    continue

                trade_id = row[0]
                ticker = row[2]
                strategy = row[4]
                contracts = int(row[11]) if row[11] else 1
                entry_credit = float(row[12]) if row[12] else 0
                max_loss = float(row[13]) if row[13] else 0
                expiration = row[9]
                exp_date = datetime.strptime(expiration, '%Y-%m-%d').date()
                days_to_exp = (exp_date - today).days

                # Get current stock price
                stock = yf.Ticker(ticker)
                current_price = stock.fast_info.last_price

                # Parse spread details
                spread_desc = row[10]
                breakeven = float(row[17]) if row[17] else 0

                # Pull the REAL current options chain for this expiration
                # instead of estimating with a linear approximation
                stock_obj = yf.Ticker(ticker)
                try:
                    chain = stock_obj.option_chain(expiration)
                except Exception as e:
                    print(f"  Could not fetch live chain for {ticker}: {e}")
                    continue

                if strategy == "SELL_PUT_SPREAD":
                    short_strike = float(spread_desc.split('$')[1].split('P')[0])
                    long_strike = float(spread_desc.split('$')[2].split('P')[0])
                    puts = chain.puts

                    short_row = puts[puts['strike'] == short_strike]
                    long_row = puts[puts['strike'] == long_strike]

                    if short_row.empty or long_row.empty:
                        print(f"  Could not find current quotes for {ticker} strikes, skipping")
                        continue

                    short_now = round((short_row.iloc[0]['bid'] + short_row.iloc[0]['ask']) / 2, 2)
                    long_now = round((long_row.iloc[0]['bid'] + long_row.iloc[0]['ask']) / 2, 2)
                    current_spread_value = round(short_now - long_now, 2)

                    current_pnl = round((entry_credit - current_spread_value) * contracts * 100, 2)
                    max_profit = round(entry_credit * contracts * 100, 2)

                else:
                    long_strike = float(spread_desc.split('$')[1].split('C')[0])
                    short_strike = float(spread_desc.split('$')[2].split('C')[0])
                    entry_debit = abs(entry_credit)
                    calls = chain.calls

                    long_row = calls[calls['strike'] == long_strike]
                    short_row = calls[calls['strike'] == short_strike]

                    if long_row.empty or short_row.empty:
                        print(f"  Could not find current quotes for {ticker} strikes, skipping")
                        continue

                    long_now = round((long_row.iloc[0]['bid'] + long_row.iloc[0]['ask']) / 2, 2)
                    short_now = round((short_row.iloc[0]['bid'] + short_row.iloc[0]['ask']) / 2, 2)
                    current_spread_value = round(long_now - short_now, 2)

                    current_pnl = round((current_spread_value - entry_debit) * contracts * 100, 2)
                    max_profit = round((short_strike - long_strike - entry_debit) * contracts * 100, 2)

                pnl_pct = round(current_pnl / (max_loss * contracts * 100) * 100, 1) if max_loss > 0 else 0

                print(f"\n{ticker} ({trade_id})")
                print(f"  Strategy: {strategy}")
                print(f"  Current Price: ${current_price:.2f} | Breakeven: ${breakeven:.2f}")
                print(f"  Days to Expiration: {days_to_exp}")
                print(f"  Current P&L: ${current_pnl:+.2f} ({pnl_pct:+.1f}%)")

                # Check exit conditions
                should_exit = False
                exit_reason = ""

                # 50% profit target
                if max_profit > 0 and current_pnl >= max_profit * 0.5:
                    should_exit = True
                    exit_reason = "50% PROFIT TARGET HIT"

                # 100% loss stop
                if current_pnl <= -(max_loss * contracts * 100):
                    should_exit = True
                    exit_reason = "STOP LOSS HIT"

                # Expiration within 7 days
                if days_to_exp <= 7:
                    should_exit = True
                    exit_reason = "EXPIRATION APPROACHING"

                if should_exit:
                    now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    options_sheet.update_cell(i, 20, "CLOSED")
                    options_sheet.update_cell(i, 21, now)
                    options_sheet.update_cell(i, 23, current_pnl)
                    options_sheet.update_cell(i, 24, pnl_pct)
                    print(f"  CLOSING — {exit_reason}")
                    print(f"  Final P&L: ${current_pnl:+.2f}")
                else:
                    print(f"  Status: HOLD — {days_to_exp} days remaining")

                time.sleep(1)

            except Exception as e:
                print(f"  Error checking row {i}: {e}")
                continue

    except Exception as e:
        print(f"Error checking trades: {e}")

def get_portfolio_summary():
    try:
        sheet = get_sheets()
        options_sheet = sheet.worksheet("Options Paper Trades")
        rows = options_sheet.get_all_values()

        open_trades = []
        closed_trades = []
        total_pnl = 0
        wins = 0
        losses = 0

        for row in rows[1:]:
            if len(row) < 20:
                continue
            status = row[19]
            if status == "OPEN":
                open_trades.append(row)
            elif status == "CLOSED":
                closed_trades.append(row)
                pnl = float(row[22]) if row[22] else 0
                total_pnl += pnl
                if pnl > 0:
                    wins += 1
                else:
                    losses += 1

        total_closed = wins + losses
        win_rate = round(wins / total_closed * 100) if total_closed > 0 else 0

        print("\n" + "="*50)
        print("OPTIONS PAPER PORTFOLIO SUMMARY")
        print("="*50)
        print(f"Open Trades:     {len(open_trades)}")
        print(f"Closed Trades:   {total_closed}")
        print(f"Win Rate:        {win_rate}%  ({wins}W / {losses}L)")
        print(f"Total P&L:       ${total_pnl:+,.2f}")
        print(f"Starting Capital: ${STARTING_CAPITAL:,.0f}")
        print(f"Return:          {round(total_pnl/STARTING_CAPITAL*100, 2)}%")
        print("="*50)

        if open_trades:
            print("\nOPEN POSITIONS:")
            for row in open_trades:
                print(f"  {row[2]:<6} {row[10]:<35} Exp: {row[9]}")

        return {
            "open": len(open_trades),
            "closed": total_closed,
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "wins": wins,
            "losses": losses
        }

    except Exception as e:
        print(f"Error getting summary: {e}")
        return {}

if __name__ == "__main__":
    check_open_trades()
    get_portfolio_summary()
    