import smtplib
import sys
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import NOTIFICATION_EMAIL, GMAIL_APP_PASSWORD

def send_report(regime_data, strong_signals, watchlist, approved_trades, portfolio_value=100000):
    print("Building report...")

    now = datetime.now().strftime("%B %d, %Y %I:%M %p")
    regime = regime_data["regime"]
    regime_score = regime_data["score"]

    # Build email body
    body = f"""
TRADING BOT DAILY REPORT
{now}

{'='*50}
MARKET REGIME: {regime} ({regime_score}/5)
{'='*50}
VIX:            {regime_data.get('vix', 'N/A')}
SPY:            ${regime_data.get('spy', 'N/A')}
Breadth:        {regime_data.get('breadth', 'N/A')}%
Sector:         {regime_data.get('rotation', 'N/A')}
Yield Curve:    {regime_data.get('yield_curve', 'N/A')}%

{'='*50}
APPROVED TRADES ({len(approved_trades)})
{'='*50}
"""

    if approved_trades:
        for trade in approved_trades:
            body += f"""
{trade['ticker']} ({trade['sector']})
  Score:     {trade['score']}/10
  Position:  ${trade['position_size']:,.0f} ({trade['position_pct']}% of portfolio)
  Action:    PAPER BUY — awaiting your approval
"""
    else:
        body += "\nNo trades meet criteria today.\n"

    body += f"""
{'='*50}
WATCH LIST ({len(watchlist[:5])})
{'='*50}
"""
    for s in watchlist[:5]:
        body += f"  {s['ticker']} ({s['sector']}): {s['score']}/10\n"

    body += f"""
{'='*50}
PORTFOLIO
{'='*50}
Current Value: ${portfolio_value:,.0f}

Reply YES to approve all trades or specify tickers.
{'='*50}
Trading Bot
"""

    # Send email
    try:
        msg = MIMEMultipart()
        msg['From'] = NOTIFICATION_EMAIL
        msg['To'] = NOTIFICATION_EMAIL
        msg['Subject'] = f"Trading Bot Report — {regime} Regime — {len(approved_trades)} Signals — {now}"
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
    # Test with sample data
    test_regime = {
        "regime": "NEUTRAL",
        "score": 1,
        "threshold_adjustment": 1,
        "vix": 21.5,
        "spy": 737.55,
        "breadth": 60,
        "rotation": "Growth leading",
        "yield_curve": 0.91
    }
    test_signals = [
        {"ticker": "CRWD", "sector": "Backdoor Tech", "score": 8.5, "position_size": 8800, "position_pct": 8.8},
        {"ticker": "ARM", "sector": "Semiconductors", "score": 7.5, "position_size": 8000, "position_pct": 8.0}
    ]
    test_watchlist = [
        {"ticker": "NVDA", "sector": "Semiconductors", "score": 6.5},
        {"ticker": "MS", "sector": "Finance", "score": 6.0}
    ]
    send_report(test_regime, test_signals, test_watchlist, test_signals)
