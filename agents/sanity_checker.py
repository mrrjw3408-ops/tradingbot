import gspread
import sys
import os
from datetime import datetime, timedelta
from collections import defaultdict
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from google.oauth2.service_account import Credentials
from config import NOTIFICATION_EMAIL, GMAIL_APP_PASSWORD
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def get_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
    client = gspread.authorize(creds)
    return client.open("Trading Bot Log")


def load_closed_trades():
    sheet = get_sheets()
    opt = sheet.worksheet("Options Paper Trades")
    rows = opt.get_all_values()

    trades = []
    for row in rows[1:]:
        if len(row) < 24 or row[19] != "CLOSED":
            continue
        try:
            entry_date = datetime.strptime(row[1][:10], "%Y-%m-%d")
            exit_date = datetime.strptime(row[20][:10], "%Y-%m-%d") if row[20] else None
            trades.append({
                "trade_id": row[0],
                "ticker": row[2],
                "sector": row[3],
                "strategy": row[4],
                "entry_date": entry_date,
                "exit_date": exit_date,
                "credit_debit": float(row[12]) if row[12] else 0,
                "max_loss": float(row[13]) if row[13] else 0,
                "total_risk": float(row[14]) if row[14] else 0,
                "contracts": int(row[11]) if row[11] else 1,
                "pnl": float(row[22]) if row[22] else 0,
                "pnl_pct": float(row[23]) if row[23] else 0,
            })
        except Exception:
            continue
    return trades


def check_fast_closes(trades, max_days=2):
    """Flag trades that closed suspiciously fast for an options spread."""
    flagged = []
    for t in trades:
        if t["exit_date"] is None:
            continue
        days_held = (t["exit_date"] - t["entry_date"]).days
        if 0 <= days_held <= max_days:
            flagged.append((t, days_held))
    return flagged


def check_win_streak(trades, min_sample=5):
    """Flag if win rate is suspiciously perfect across enough trades."""
    if len(trades) < min_sample:
        return None
    wins = sum(1 for t in trades if t["pnl"] > 0)
    win_rate = wins / len(trades) * 100
    if win_rate >= 95:
        return {"win_rate": round(win_rate, 1), "wins": wins, "total": len(trades)}
    return None


def check_pnl_math(trades):
    """
    Verify reported PnL is mathematically possible given credit/debit and
    max_loss logged at entry. Catches the exact class of bug from before --
    PnL exceeding what the spread could ever actually pay out.
    """
    flagged = []
    for t in trades:
        max_possible_profit = abs(t["credit_debit"]) * t["contracts"] * 100
        max_possible_loss = t["max_loss"] * t["contracts"] * 100

        # Reported PnL should never exceed max possible profit (for a credit
        # spread) or be worse than max possible loss
        if t["pnl"] > max_possible_profit * 1.05:  # 5% tolerance for rounding
            flagged.append((t, "PnL exceeds max possible profit", max_possible_profit))
        elif t["pnl"] < -max_possible_loss * 1.05:
            flagged.append((t, "PnL exceeds max possible loss", -max_possible_loss))
    return flagged


def check_clustered_timing(trades, window_minutes=10):
    """
    Flag if many trades opened or closed within the same tight window --
    the fingerprint of one correlated sector event being mistaken for
    independent signals, not a bug per se, but worth surfacing.
    """
    by_exit_window = defaultdict(list)
    for t in trades:
        if t["exit_date"] is None:
            continue
        key = t["exit_date"].strftime("%Y-%m-%d")
        by_exit_window[key].append(t)

    clusters = []
    for date, group in by_exit_window.items():
        if len(group) >= 5:
            sectors = set(t["sector"] for t in group)
            clusters.append({
                "date": date,
                "count": len(group),
                "sectors_involved": len(sectors),
                "tickers": [t["ticker"] for t in group]
            })
    return clusters


def check_uniform_pnl_pct(trades, tolerance=3.0):
    """Flag if multiple trades closed with nearly identical PnL% -- another
    bug fingerprint, since real independent positions rarely converge this tightly."""
    flagged_groups = []
    sorted_trades = sorted(trades, key=lambda x: x["pnl_pct"])
    i = 0
    while i < len(sorted_trades):
        group = [sorted_trades[i]]
        j = i + 1
        while j < len(sorted_trades) and abs(sorted_trades[j]["pnl_pct"] - sorted_trades[i]["pnl_pct"]) <= tolerance:
            group.append(sorted_trades[j])
            j += 1
        if len(group) >= 5:
            flagged_groups.append(group)
        i = j if j > i + 1 else i + 1
    return flagged_groups


def build_report(trades):
    issues = []

    fast_closes = check_fast_closes(trades)
    if fast_closes:
        issues.append({
            "severity": "HIGH",
            "title": f"{len(fast_closes)} trade(s) closed suspiciously fast (≤2 days)",
            "detail": [f"{t['ticker']} closed in {d} day(s), PnL ${t['pnl']:+.2f} ({t['pnl_pct']:+.1f}%)" for t, d in fast_closes[:10]]
        })

    win_streak = check_win_streak(trades)
    if win_streak:
        issues.append({
            "severity": "HIGH",
            "title": f"Suspiciously high win rate: {win_streak['win_rate']}% ({win_streak['wins']}/{win_streak['total']})",
            "detail": ["Your backtest showed 53-65% win rates even in your best combinations. A win rate this high across this many trades is not statistically plausible and likely indicates a pricing/valuation bug."]
        })

    pnl_math_issues = check_pnl_math(trades)
    if pnl_math_issues:
        issues.append({
            "severity": "CRITICAL",
            "title": f"{len(pnl_math_issues)} trade(s) with IMPOSSIBLE PnL math",
            "detail": [f"{t['ticker']}: {reason} (max possible: ${max_val:+.2f}, reported: ${t['pnl']:+.2f})" for t, reason, max_val in pnl_math_issues[:10]]
        })

    clusters = check_clustered_timing(trades)
    if clusters:
        for c in clusters:
            severity = "MEDIUM" if c["sectors_involved"] <= 2 else "LOW"
            issues.append({
                "severity": severity,
                "title": f"{c['count']} trades closed same day ({c['date']}) across only {c['sectors_involved']} sector(s)",
                "detail": [f"Tickers: {', '.join(c['tickers'])}", "This is likely ONE correlated sector move counted as multiple independent results."]
            })

    uniform_groups = check_uniform_pnl_pct(trades)
    if uniform_groups:
        for g in uniform_groups:
            issues.append({
                "severity": "MEDIUM",
                "title": f"{len(g)} trades closed with nearly identical PnL% (within 3%)",
                "detail": [f"{t['ticker']}: {t['pnl_pct']:+.1f}%" for t in g[:10]]
            })

    return issues


def send_sanity_report(issues, total_trades_checked):
    severity_color = {"CRITICAL": "#e74c3c", "HIGH": "#f39c12", "MEDIUM": "#f1c40f", "LOW": "#888"}
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    issues_sorted = sorted(issues, key=lambda x: severity_order.get(x["severity"], 9))

    now = datetime.now().strftime("%B %d, %Y %I:%M %p CDT")

    if not issues:
        subject = f"✅ Sanity Check Passed — {total_trades_checked} closed trades reviewed"
        body_intro = f'<p style="color:#27ae60;font-size:14px;">No suspicious patterns found across {total_trades_checked} closed trades. Results look statistically plausible.</p>'
    else:
        critical_count = sum(1 for i in issues if i["severity"] == "CRITICAL")
        subject = f"{'🚨' if critical_count else '⚠️'} Sanity Check: {len(issues)} issue(s) flagged"
        body_intro = f'<p style="color:#f39c12;font-size:14px;">{len(issues)} issue(s) found across {total_trades_checked} closed trades reviewed. Review before trusting these results.</p>'

    issues_html = ""
    for issue in issues_sorted:
        color = severity_color.get(issue["severity"], "#888")
        detail_html = "".join(f'<li style="color:#aaa;font-size:13px;margin-bottom:4px;">{d}</li>' for d in issue["detail"])
        issues_html += f"""
        <div style="background:#111;border-left:3px solid {color};border-radius:6px;padding:14px 16px;margin-bottom:12px;">
          <p style="margin:0 0 8px;color:{color};font-size:13px;font-weight:700;">{issue['severity']} — {issue['title']}</p>
          <ul style="margin:0;padding-left:18px;">{detail_html}</ul>
        </div>"""

    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0f0f0f;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<div style="max-width:650px;margin:0 auto;padding:24px;">
  <div style="background:#1a1a1a;border-radius:12px;padding:24px;border:1px solid #2a2a2a;">
    <h1 style="margin:0 0 4px;color:#fff;font-size:20px;font-weight:700;">🔍 Sanity Check Report</h1>
    <p style="margin:0 0 16px;color:#666;font-size:13px;">{now}</p>
    {body_intro}
    {issues_html}
    <p style="margin:16px 0 0;color:#444;font-size:11px;text-align:center;">Trading Bot — Automated Sanity Check</p>
  </div>
</div>
</body>
</html>
"""

    try:
        msg = MIMEMultipart("alternative")
        msg['From'] = NOTIFICATION_EMAIL
        msg['To'] = NOTIFICATION_EMAIL
        msg['Subject'] = subject
        msg.attach(MIMEText(html, 'html'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(NOTIFICATION_EMAIL, GMAIL_APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"Sanity check report sent: {subject}")
    except Exception as e:
        print(f"Error sending sanity report: {e}")


def get_last_check_time():
    try:
        sheet = get_sheets()
        try:
            tracker = sheet.worksheet("Sanity Check Log")
        except gspread.exceptions.WorksheetNotFound:
            tracker = sheet.add_worksheet(title="Sanity Check Log", rows=500, cols=4)
            tracker.append_row(["Timestamp", "Trades Checked", "Issues Found", "Emailed"])
            return None
        rows = tracker.get_all_values()
        if len(rows) < 2:
            return None
        last_ts = rows[-1][0]
        return datetime.strptime(last_ts, "%Y-%m-%d %H:%M")
    except Exception:
        return None


def log_check_run(trades_checked, issues_found, emailed):
    try:
        sheet = get_sheets()
        tracker = sheet.worksheet("Sanity Check Log")
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        tracker.append_row([now, trades_checked, issues_found, str(emailed)])
    except Exception as e:
        print(f"Error logging sanity check run: {e}")


def run_sanity_check(send_email=True, force_email=False):
    """
    Always runs the checks and prints to console. Email logic:
      - Never emails if there are zero closed trades yet (nothing to check)
      - Always emails immediately if any issue is found, regardless of severity
      - If no issues found, only emails once per ~24 hours (a quiet daily
        "all clear" rather than spamming every single scheduled run)
      - force_email=True overrides the 24h throttle (used for manual runs)
    """
    print("=" * 50)
    print("RUNNING SANITY CHECK ON CLOSED TRADES")
    print("=" * 50)

    trades = load_closed_trades()
    print(f"Loaded {len(trades)} closed trades")

    if not trades:
        print("No closed trades to check yet -- nothing to validate.")
        print("=" * 50)
        return

    issues = build_report(trades)

    print(f"\nFound {len(issues)} issue(s):\n")
    for issue in issues:
        print(f"[{issue['severity']}] {issue['title']}")
        for d in issue["detail"]:
            print(f"    {d}")
        print()

    if not issues:
        print("No suspicious patterns detected. Results look statistically plausible.")

    should_email = False
    if send_email:
        if issues:
            should_email = True  # always alert immediately on any flagged issue
        elif force_email:
            should_email = True
        else:
            last_check = get_last_check_time()
            if last_check is None or (datetime.now() - last_check) > timedelta(hours=24):
                should_email = True

    if should_email:
        send_sanity_report(issues, len(trades))
        log_check_run(len(trades), len(issues), True)
    else:
        print("Skipping email (no issues found, checked recently).")
        log_check_run(len(trades), len(issues), False)

    print("=" * 50)
    print("SANITY CHECK COMPLETE")
    print("=" * 50)


if __name__ == "__main__":
    run_sanity_check()
