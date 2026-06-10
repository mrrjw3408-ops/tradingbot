import smtplib
import sys
import os
import gspread
from google.oauth2.service_account import Credentials
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import NOTIFICATION_EMAIL, GMAIL_APP_PASSWORD

def get_sector_performance():
    try:
        import yfinance as yf
        sector_etfs = {
            "Semiconductors": "SOXX",
            "Backdoor Tech": "XLK",
            "Health": "XLV",
            "Finance": "XLF",
            "Energy": "XLE",
            "Infrastructure": "PAVE"
        }
        results = {}
        for sector, etf in sector_etfs.items():
            df = yf.Ticker(etf).history(period="3mo")
            if not df.empty:
             if len(df) < 10:
              continue
             lookback = min(20, len(df) - 1)
             ret = (df["Close"].iloc[-1] / df["Close"].iloc[-lookback] - 1) * 100    
                results[sector] = round(ret, 2)
        return dict(sorted(results.items(), key=lambda x: x[1], reverse=True))
    except:
        return {}

def get_portfolio_stats():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open("Trading Bot Log")

        # Get scan log stats
        scan_log = sheet.worksheet("Scan Log")
        rows = scan_log.get_all_values()
        today = datetime.now().strftime("%Y-%m-%d")
        today_rows = [r for r in rows[1:] if r and r[0].startswith(today)]
        total_scans = len(today_rows)

        # Get outcomes stats
        outcomes = sheet.worksheet("Outcomes")
        outcome_rows = outcomes.get_all_values()
        wins = sum(1 for r in outcome_rows[1:] if len(r) > 9 and r[9] == "WIN")
        losses = sum(1 for r in outcome_rows[1:] if len(r) > 9 and r[9] == "LOSS")
        total_trades = wins + losses
        win_rate = round(wins / total_trades * 100) if total_trades > 0 else 0

        # Get top scores today
        scored = []
        for row in today_rows:
            if len(row) >= 14 and row[12]:
                try:
                    scored.append({
                        "ticker": row[1],
                        "sector": row[2],
                        "score": float(row[12]),
                        "breakdown": row[13] if len(row) > 13 else ""
                    })
                except:
                    continue
        scored.sort(key=lambda x: x["score"], reverse=True)

        # Get sector averages today
        sector_scores = {}
        sector_counts = {}
        for row in today_rows:
            if len(row) >= 13 and row[2] and row[12]:
                try:
                    sector = row[2]
                    score = float(row[12])
                    sector_scores[sector] = sector_scores.get(sector, 0) + score
                    sector_counts[sector] = sector_counts.get(sector, 0) + 1
                except:
                    continue
        sector_averages = {s: round(sector_scores[s] / sector_counts[s], 2) for s in sector_scores}
        sector_averages = dict(sorted(sector_averages.items(), key=lambda x: x[1], reverse=True))

        return {
            "total_scans": total_scans,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "top_signals": scored[:10],
            "sector_averages": sector_averages
        }
    except Exception as e:
        return {
            "total_scans": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0,
            "top_signals": [],
            "sector_averages": {}
        }

def build_bar(value, max_val=10, width=10):
    try:
        if max_val == 0 or value != value:  # NaN check
            return "░" * width
        filled = int((abs(value) / max_val) * width)
        filled = min(filled, width)
        return "█" * filled + "░" * (width - filled)
    except:
        return "░" * width
    
def send_report(regime_data, strong_signals, watchlist, approved_trades, portfolio_value=100000):
    print("Building report...")

    now = datetime.now().strftime("%B %d, %Y %I:%M %p")
    regime = regime_data["regime"]
    regime_score = regime_data["score"]

    # Get additional data
    sector_perf = get_sector_performance()
    stats = get_portfolio_stats()

    divider = "━" * 49

    body = f"""
TRADING BOT DAILY REPORT
{now}
{divider}

MARKET REGIME: {regime} ({regime_score}/5)
VIX: {regime_data.get('vix', 'N/A'):.1f}  |  SPY: ${regime_data.get('spy', 0):.2f}  |  Breadth: {regime_data.get('breadth', 0):.0f}%
Rotation: {regime_data.get('rotation', 'N/A')}
Yield Curve: {regime_data.get('yield_curve', 0):.2f}%

{divider}
SECTOR PERFORMANCE (20 Day Return)
{divider}
"""

    for sector, ret in sector_perf.items():
        bar = build_bar(ret, max_val=15, width=10)
        direction = "▲ LEADING" if ret > 2 else "▼ LAGGING" if ret < 0 else "→ NEUTRAL"
        body += f"{sector:<20} {bar}  {ret:+.2f}%  {direction}\n"

    body += f"""
{divider}
SECTOR SIGNAL STRENGTH TODAY (Avg Score)
{divider}
"""
    for sector, avg in stats["sector_averages"].items():
        bar = build_bar(avg, max_val=5, width=10)
        body += f"{sector:<20} {bar}  {avg}/5.0\n"

    body += f"""
{divider}
PORTFOLIO PERFORMANCE
{divider}
Portfolio Value:    ${portfolio_value:>12,.0f}
Open Positions:     {len(approved_trades):>12}
Stocks Scanned:     {stats['total_scans']:>12}
Completed Trades:   {stats['wins'] + stats['losses']:>12}
Win Rate:           {stats['win_rate']:>11}%
Wins / Losses:      {stats['wins']:>5}W / {stats['losses']}L

{divider}
TOP SIGNALS TODAY
{divider}
"""

    if stats["top_signals"]:
        for i, s in enumerate(stats["top_signals"][:10], 1):
            breakdown = s['breakdown'].replace('|', '  ')
            body += f"{i:>2}. {s['ticker']:<6} {s['sector']:<20} Score: {s['score']}\n"
            body += f"    {breakdown}\n\n"
    else:
        body += "No signals logged today yet.\n"

    body += f"""
{divider}
APPROVED TRADES ({len(approved_trades)})
{divider}
"""
    if approved_trades:
        for trade in approved_trades:
            body += f"{trade['ticker']} ({trade['sector']})\n"
            body += f"  Score: {trade['score']}/10  |  Position: ${trade['position_size']:,.0f} ({trade['position_pct']}%)\n\n"
    else:
        body += "No trades meet entry threshold today.\n"

    body += f"""
{divider}
WATCH LIST
{divider}
"""
    if watchlist:
        for s in watchlist[:8]:
            body += f"  {s['ticker']:<6} ({s['sector']})  Score: {s['score']}\n"
    else:
        body += "No watch list stocks today.\n"

    body += f"""
{divider}
NEWS & CATALYSTS
{divider}
[News agent coming in Phase 3]
Earnings calendar integration coming soon.
{divider}

Trading Bot — Automated Report
Reply YES to approve all trades or specify tickers.
"""

    # Send email
    try:
        msg = MIMEMultipart()
        msg['From'] = NOTIFICATION_EMAIL
        msg['To'] = NOTIFICATION_EMAIL
        msg['Subject'] = f"Trading Bot | {regime} Regime | {len(stats['top_signals'])} Signals | {now}"
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(NOTIFICATION_EMAIL, GMAIL_APP_PASSWORD)
        server.send_message(msg)
        server.quit()

        print(f"Report sent to {NOTIFICATION_EMAIL}")
        return True

    except Exception as e:
        print(f"Email error: {e}")
        return False

if __name__ == "__main__":
    test_regime = {
        "regime": "BULL",
        "score": 4,
        "threshold_adjustment": 0,
        "vix": 18.9,
        "spy": 739.22,
        "breadth": 75,
        "rotation": "Growth leading",
        "yield_curve": 0.92
    }
    send_report(test_regime, [], [], [])
    