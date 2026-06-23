import smtplib
import sys
import os
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import NOTIFICATION_EMAIL, GMAIL_APP_PASSWORD


def get_sector_performance():
    import time as _time
    from config import SECTORS as sector_etfs
    results = {}
    for sector, etf in sector_etfs.items():
        for attempt in range(3):
            try:
                df = yf.Ticker(etf).history(period="3mo")
                closes = df["Close"].dropna()
                if len(closes) < 10:
                    raise ValueError("insufficient data")
                lookback = min(20, len(closes) - 1)
                last = closes.iloc[-1]
                prev = closes.iloc[-lookback]
                if last > 0 and prev > 0:
                    ret = round((last / prev - 1) * 100, 2)
                    results[sector] = ret
                break
            except Exception:
                _time.sleep(1.5)
    return dict(sorted(results.items(), key=lambda x: x[1], reverse=True))


def get_portfolio_stats():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open("Trading Bot Log")

        scan_log = sheet.worksheet("Scan Log")
        rows = scan_log.get_all_values()
        today = datetime.now().strftime("%Y-%m-%d")
        today_rows = [r for r in rows[1:] if r and len(r) > 2 and r[0].startswith(today)]
        total_scans = len(today_rows)

        outcomes = sheet.worksheet("Outcomes")
        outcome_rows = outcomes.get_all_values()
        wins = sum(1 for r in outcome_rows[1:] if len(r) > 9 and r[9] == "WIN")
        losses = sum(1 for r in outcome_rows[1:] if len(r) > 9 and r[9] == "LOSS")
        total_trades = wins + losses
        win_rate = round(wins / total_trades * 100) if total_trades > 0 else 0

        scored = []
        sector_scores = {}
        sector_counts = {}

        for row in today_rows:
            try:
                if len(row) < 13 or not row[1] or not row[2] or not row[12]:
                    continue
                score = float(row[12])
                if score < 0 or score > 10:
                    continue
                sector = row[2]
                ticker = row[1]
                breakdown = row[13] if len(row) > 13 else ""
                scored.append({
                    "ticker": ticker,
                    "sector": sector,
                    "score": score,
                    "breakdown": breakdown
                })
                sector_scores[sector] = sector_scores.get(sector, 0) + score
                sector_counts[sector] = sector_counts.get(sector, 0) + 1
            except:
                continue

        scored.sort(key=lambda x: x["score"], reverse=True)
        sector_averages = {}
        for s in sector_scores:
            if sector_counts[s] > 0:
                sector_averages[s] = round(sector_scores[s] / sector_counts[s], 2)
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
        print(f"Portfolio stats error: {e}")
        return {
            "total_scans": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0,
            "top_signals": [],
            "sector_averages": {}
        }


def regime_color(regime):
    if regime == "BULL":
        return "#27ae60"
    elif regime == "BEAR":
        return "#e74c3c"
    return "#f39c12"


def score_color(score):
    if score >= 4:
        return "#27ae60"
    elif score >= 2.5:
        return "#f39c12"
    return "#e74c3c"


def ret_color(ret):
    if ret > 2:
        return "#27ae60"
    elif ret < 0:
        return "#e74c3c"
    return "#f39c12"


def bar_html(value, max_val=5, width=100):
    try:
        if value != value or max_val == 0:
            return ""
        pct = min(abs(value) / max_val * width, width)
        color = "#27ae60" if value >= 0 else "#e74c3c"
        return f'<div style="background:#2c2c2c;border-radius:4px;height:8px;width:{width}px;display:inline-block;vertical-align:middle;"><div style="background:{color};height:8px;border-radius:4px;width:{pct:.0f}px;"></div></div>'
    except:
        return ""


def build_options_html(options_trades, options_summary):
    if not options_trades and not options_summary:
        return '<p style="color:#444;font-size:13px;">No options trades today</p>'

    html = ""

    if options_summary and options_summary.get("closed", 0) > 0:
        pnl = options_summary.get("total_pnl", 0)
        pnl_color = "#27ae60" if pnl >= 0 else "#e74c3c"
        html += f"""
        <div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;">
            <div style="background:#111;border-radius:8px;padding:10px 16px;flex:1;text-align:center;">
                <p style="margin:0;color:#666;font-size:11px;">Win Rate</p>
                <p style="margin:4px 0 0;color:#27ae60;font-size:18px;font-weight:700;">{options_summary.get('win_rate', 0)}%</p>
            </div>
            <div style="background:#111;border-radius:8px;padding:10px 16px;flex:1;text-align:center;">
                <p style="margin:0;color:#666;font-size:11px;">Total P&L</p>
                <p style="margin:4px 0 0;color:{pnl_color};font-size:18px;font-weight:700;">${pnl:+,.2f}</p>
            </div>
            <div style="background:#111;border-radius:8px;padding:10px 16px;flex:1;text-align:center;">
                <p style="margin:0;color:#666;font-size:11px;">Open</p>
                <p style="margin:4px 0 0;color:#fff;font-size:18px;font-weight:700;">{options_summary.get('open', 0)}</p>
            </div>
            <div style="background:#111;border-radius:8px;padding:10px 16px;flex:1;text-align:center;">
                <p style="margin:0;color:#666;font-size:11px;">Closed</p>
                <p style="margin:4px 0 0;color:#fff;font-size:18px;font-weight:700;">{options_summary.get('closed', 0)}</p>
            </div>
        </div>"""

    if options_trades:
        html += '<table style="width:100%;border-collapse:collapse;">'
        html += '''<tr style="border-bottom:1px solid #2a2a2a;">
            <th style="padding:8px 12px;color:#666;font-size:11px;text-align:left;">Ticker</th>
            <th style="padding:8px 12px;color:#666;font-size:11px;text-align:left;">Strategy</th>
            <th style="padding:8px 12px;color:#666;font-size:11px;text-align:left;">Spread</th>
            <th style="padding:8px 12px;color:#666;font-size:11px;text-align:left;">Credit</th>
            <th style="padding:8px 12px;color:#666;font-size:11px;text-align:left;">ROR</th>
            <th style="padding:8px 12px;color:#666;font-size:11px;text-align:left;">Confidence</th>
        </tr>'''

        for trade in options_trades:
            spread = trade["spread"]
            conf_color = "#27ae60" if trade["confidence"] == "HIGH" else "#f39c12" if trade["confidence"] == "MEDIUM" else "#e74c3c"
            if trade["strategy"] == "SELL_PUT_SPREAD":
                spread_desc = f"Sell ${spread['short_strike']}P / Buy ${spread['long_strike']}P"
                credit = f"+${spread['net_credit']}"
            else:
                spread_desc = f"Buy ${spread['long_strike']}C / Sell ${spread['short_strike']}C"
                credit = f"-${spread['net_debit']}"

            html += f'''<tr style="border-bottom:1px solid #2a2a2a;">
                <td style="padding:10px 12px;color:#fff;font-weight:600;">{trade['ticker']}</td>
                <td style="padding:10px 12px;color:#aaa;font-size:12px;">{trade['strategy'].replace('_', ' ')}</td>
                <td style="padding:10px 12px;color:#aaa;font-size:12px;">{spread_desc}</td>
                <td style="padding:10px 12px;color:#27ae60;font-weight:600;">{credit}</td>
                <td style="padding:10px 12px;color:#aaa;font-size:12px;">{spread['return_on_risk']}%</td>
                <td style="padding:10px 12px;color:{conf_color};font-weight:600;">{trade['confidence']}</td>
            </tr>'''
        html += '</table>'
    else:
        html += '<p style="color:#666;font-size:13px;">No new options trades today</p>'

    return html


def send_report(regime_data, strong_signals, watchlist, approved_trades, portfolio_value=10000, options_trades=None, options_summary=None):
    print("Building HTML report...")

    from datetime import timezone, timedelta
    cst = timezone(timedelta(hours=-5))
    now = datetime.now(cst).strftime("%B %d, %Y %I:%M %p CST")
    regime = regime_data["regime"]
    regime_score = regime_data["score"]
    rcolor = regime_color(regime)

    sector_perf = get_sector_performance()
    stats = get_portfolio_stats()
    options_html = build_options_html(options_trades or [], options_summary or {})

    sector_perf_rows = ""
    for sector, ret in sector_perf.items():
        rc = ret_color(ret)
        direction = "▲ Leading" if ret > 2 else "▼ Lagging" if ret < 0 else "→ Neutral"
        bar = bar_html(ret, max_val=15)
        sector_perf_rows += f"""
        <tr>
            <td style="padding:8px 12px;color:#ccc;font-size:13px;">{sector}</td>
            <td style="padding:8px 12px;">{bar}</td>
            <td style="padding:8px 12px;color:{rc};font-weight:600;font-size:13px;">{ret:+.2f}%</td>
            <td style="padding:8px 12px;color:{rc};font-size:12px;">{direction}</td>
        </tr>"""

    sector_signal_rows = ""
    for sector, avg in stats["sector_averages"].items():
        sc = score_color(avg)
        bar = bar_html(avg, max_val=5)
        sector_signal_rows += f"""
        <tr>
            <td style="padding:8px 12px;color:#ccc;font-size:13px;">{sector}</td>
            <td style="padding:8px 12px;">{bar}</td>
            <td style="padding:8px 12px;color:{sc};font-weight:600;font-size:13px;">{avg}/5.0</td>
        </tr>"""

    if not sector_signal_rows:
        sector_signal_rows = '<tr><td colspan="3" style="padding:12px;color:#666;font-size:13px;">No scan data yet today</td></tr>'

    signal_rows = ""
    for i, s in enumerate(stats["top_signals"][:10], 1):
        sc = score_color(s["score"])
        breakdown = s["breakdown"].replace("|", "  &nbsp;|&nbsp;  ")
        signal_rows += f"""
        <tr style="border-bottom:1px solid #2a2a2a;">
            <td style="padding:10px 12px;color:#aaa;font-size:12px;">{i}</td>
            <td style="padding:10px 12px;color:#fff;font-weight:600;font-size:14px;">{s['ticker']}</td>
            <td style="padding:10px 12px;color:#aaa;font-size:12px;">{s['sector']}</td>
            <td style="padding:10px 12px;color:{sc};font-weight:700;font-size:14px;">{s['score']}</td>
            <td style="padding:10px 12px;color:#666;font-size:11px;">{breakdown}</td>
        </tr>"""

    if not signal_rows:
        signal_rows = '<tr><td colspan="5" style="padding:12px;color:#666;font-size:13px;">No signals logged today yet</td></tr>'

    trade_rows = ""
    for trade in approved_trades:
        sc = score_color(trade["score"])
        trade_rows += f"""
        <tr style="border-bottom:1px solid #2a2a2a;">
            <td style="padding:10px 12px;color:#fff;font-weight:600;">{trade['ticker']}</td>
            <td style="padding:10px 12px;color:#aaa;font-size:12px;">{trade['sector']}</td>
            <td style="padding:10px 12px;color:{sc};font-weight:700;">{trade['score']}/10</td>
            <td style="padding:10px 12px;color:#27ae60;font-weight:600;">${trade['position_size']:,.0f}</td>
            <td style="padding:10px 12px;color:#aaa;font-size:12px;">{trade['position_pct']}%</td>
        </tr>"""

    if not trade_rows:
        trade_rows = '<tr><td colspan="5" style="padding:12px;color:#666;font-size:13px;">No trades meet entry threshold today</td></tr>'

    watch_items = ""
    for s in watchlist[:8]:
        sc = score_color(s["score"])
        watch_items += f'<span style="display:inline-block;background:#1e1e1e;border:1px solid #333;border-radius:6px;padding:6px 12px;margin:4px;color:{sc};font-size:13px;font-weight:600;">{s["ticker"]} {s["score"]}</span>'

    if not watch_items:
        watch_items = '<span style="color:#666;font-size:13px;">No watch list stocks today</span>'

    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0f0f0f;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<div style="max-width:700px;margin:0 auto;padding:24px;">

  <div style="background:#1a1a1a;border-radius:12px;padding:24px;margin-bottom:16px;border:1px solid #2a2a2a;">
    <div style="display:flex;justify-content:space-between;align-items:center;">
      <div>
        <h1 style="margin:0;color:#fff;font-size:20px;font-weight:700;">Trading Bot Report</h1>
        <p style="margin:6px 0 0;color:#666;font-size:13px;">{now}</p>
      </div>
      <div style="text-align:right;">
        <span style="background:{rcolor};color:#fff;padding:6px 16px;border-radius:20px;font-size:13px;font-weight:700;">{regime} REGIME</span>
        <p style="margin:6px 0 0;color:#666;font-size:12px;">{regime_score}/5 signals bullish</p>
      </div>
    </div>
    <div style="display:flex;gap:12px;margin-top:16px;flex-wrap:wrap;">
      <div style="background:#111;border-radius:8px;padding:10px 16px;flex:1;min-width:100px;">
        <p style="margin:0;color:#666;font-size:11px;">VIX</p>
        <p style="margin:4px 0 0;color:#fff;font-size:16px;font-weight:700;">{regime_data.get('vix', 0):.1f}</p>
      </div>
      <div style="background:#111;border-radius:8px;padding:10px 16px;flex:1;min-width:100px;">
        <p style="margin:0;color:#666;font-size:11px;">SPY</p>
        <p style="margin:4px 0 0;color:#fff;font-size:16px;font-weight:700;">${regime_data.get('spy', 0):.2f}</p>
      </div>
      <div style="background:#111;border-radius:8px;padding:10px 16px;flex:1;min-width:100px;">
        <p style="margin:0;color:#666;font-size:11px;">Breadth</p>
        <p style="margin:4px 0 0;color:#fff;font-size:16px;font-weight:700;">{regime_data.get('breadth', 0):.0f}%</p>
      </div>
      <div style="background:#111;border-radius:8px;padding:10px 16px;flex:1;min-width:100px;">
        <p style="margin:0;color:#666;font-size:11px;">Yield Curve</p>
        <p style="margin:4px 0 0;color:#fff;font-size:16px;font-weight:700;">{regime_data.get('yield_curve', 0):.2f}%</p>
      </div>
      <div style="background:#111;border-radius:8px;padding:10px 16px;flex:1;min-width:100px;">
        <p style="margin:0;color:#666;font-size:11px;">Portfolio</p>
        <p style="margin:4px 0 0;color:#27ae60;font-size:16px;font-weight:700;">${portfolio_value:,.0f}</p>
      </div>
    </div>
  </div>

  <div style="background:#1a1a1a;border-radius:12px;padding:20px;margin-bottom:16px;border:1px solid #2a2a2a;">
    <h2 style="margin:0 0 16px;color:#fff;font-size:15px;font-weight:600;">Portfolio Performance</h2>
    <div style="display:flex;gap:12px;flex-wrap:wrap;">
      <div style="background:#111;border-radius:8px;padding:12px 16px;flex:1;min-width:80px;text-align:center;">
        <p style="margin:0;color:#666;font-size:11px;">Scanned</p>
        <p style="margin:4px 0 0;color:#fff;font-size:20px;font-weight:700;">{stats['total_scans']}</p>
      </div>
      <div style="background:#111;border-radius:8px;padding:12px 16px;flex:1;min-width:80px;text-align:center;">
        <p style="margin:0;color:#666;font-size:11px;">Win Rate</p>
        <p style="margin:4px 0 0;color:#27ae60;font-size:20px;font-weight:700;">{stats['win_rate']}%</p>
      </div>
      <div style="background:#111;border-radius:8px;padding:12px 16px;flex:1;min-width:80px;text-align:center;">
        <p style="margin:0;color:#666;font-size:11px;">Wins</p>
        <p style="margin:4px 0 0;color:#27ae60;font-size:20px;font-weight:700;">{stats['wins']}</p>
      </div>
      <div style="background:#111;border-radius:8px;padding:12px 16px;flex:1;min-width:80px;text-align:center;">
        <p style="margin:0;color:#666;font-size:11px;">Losses</p>
        <p style="margin:4px 0 0;color:#e74c3c;font-size:20px;font-weight:700;">{stats['losses']}</p>
      </div>
      <div style="background:#111;border-radius:8px;padding:12px 16px;flex:1;min-width:80px;text-align:center;">
        <p style="margin:0;color:#666;font-size:11px;">Open</p>
        <p style="margin:4px 0 0;color:#fff;font-size:20px;font-weight:700;">{len(approved_trades)}</p>
      </div>
    </div>
  </div>

  <div style="background:#1a1a1a;border-radius:12px;padding:20px;margin-bottom:16px;border:1px solid #2a2a2a;">
    <h2 style="margin:0 0 16px;color:#fff;font-size:15px;font-weight:600;">Sector Performance <span style="color:#666;font-size:12px;font-weight:400;">(20 Day Return)</span></h2>
    <table style="width:100%;border-collapse:collapse;">
      {sector_perf_rows if sector_perf_rows else '<tr><td style="color:#666;padding:12px;">Sector data unavailable</td></tr>'}
    </table>
  </div>

  <div style="background:#1a1a1a;border-radius:12px;padding:20px;margin-bottom:16px;border:1px solid #2a2a2a;">
    <h2 style="margin:0 0 16px;color:#fff;font-size:15px;font-weight:600;">Sector Signal Strength <span style="color:#666;font-size:12px;font-weight:400;">(Avg Score Today)</span></h2>
    <table style="width:100%;border-collapse:collapse;">
      {sector_signal_rows}
    </table>
  </div>

  <div style="background:#1a1a1a;border-radius:12px;padding:20px;margin-bottom:16px;border:1px solid #2a2a2a;">
    <h2 style="margin:0 0 16px;color:#fff;font-size:15px;font-weight:600;">Top Signals Today</h2>
    <table style="width:100%;border-collapse:collapse;">
      <tr style="border-bottom:1px solid #2a2a2a;">
        <th style="padding:8px 12px;color:#666;font-size:11px;text-align:left;">#</th>
        <th style="padding:8px 12px;color:#666;font-size:11px;text-align:left;">Ticker</th>
        <th style="padding:8px 12px;color:#666;font-size:11px;text-align:left;">Sector</th>
        <th style="padding:8px 12px;color:#666;font-size:11px;text-align:left;">Score</th>
        <th style="padding:8px 12px;color:#666;font-size:11px;text-align:left;">Breakdown</th>
      </tr>
      {signal_rows}
    </table>
  </div>

  <div style="background:#1a1a1a;border-radius:12px;padding:20px;margin-bottom:16px;border:1px solid #2a2a2a;">
    <h2 style="margin:0 0 16px;color:#fff;font-size:15px;font-weight:600;">Approved Stock Signals <span style="color:#666;font-size:12px;font-weight:400;">({len(approved_trades)} today)</span></h2>
    <table style="width:100%;border-collapse:collapse;">
      <tr style="border-bottom:1px solid #2a2a2a;">
        <th style="padding:8px 12px;color:#666;font-size:11px;text-align:left;">Ticker</th>
        <th style="padding:8px 12px;color:#666;font-size:11px;text-align:left;">Sector</th>
        <th style="padding:8px 12px;color:#666;font-size:11px;text-align:left;">Score</th>
        <th style="padding:8px 12px;color:#666;font-size:11px;text-align:left;">Position</th>
        <th style="padding:8px 12px;color:#666;font-size:11px;text-align:left;">% of Portfolio</th>
      </tr>
      {trade_rows}
    </table>
  </div>

  <div style="background:#1a1a1a;border-radius:12px;padding:20px;margin-bottom:16px;border:1px solid #2a2a2a;">
    <h2 style="margin:0 0 16px;color:#fff;font-size:15px;font-weight:600;">Paper Options Trades</h2>
    {options_html}
  </div>

  <div style="background:#1a1a1a;border-radius:12px;padding:20px;margin-bottom:16px;border:1px solid #2a2a2a;">
    <h2 style="margin:0 0 12px;color:#fff;font-size:15px;font-weight:600;">Watch List</h2>
    <div>{watch_items}</div>
  </div>

  <div style="background:#1a1a1a;border-radius:12px;padding:20px;margin-bottom:16px;border:1px solid #2a2a2a;">
    <h2 style="margin:0 0 8px;color:#fff;font-size:15px;font-weight:600;">News & Catalysts</h2>
    <p style="margin:0;color:#444;font-size:13px;">News agent coming in Phase 3 — earnings calendar integration coming soon.</p>
  </div>

  <div style="text-align:center;padding:16px;">
    <p style="color:#444;font-size:12px;margin:0;">Trading Bot — Automated Report | Reply YES to approve all trades</p>
  </div>

</div>
</body>
</html>
"""

    try:
        msg = MIMEMultipart("alternative")
        msg['From'] = NOTIFICATION_EMAIL
        msg['To'] = NOTIFICATION_EMAIL
        msg['Subject'] = f"Trading Bot | {regime} {regime_score}/5 | {len(stats['top_signals'])} Signals | {now}"

        msg.attach(MIMEText(html, 'html'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(NOTIFICATION_EMAIL, GMAIL_APP_PASSWORD)
        server.send_message(msg)
        server.quit()

        print(f"HTML report sent to {NOTIFICATION_EMAIL}")
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
    