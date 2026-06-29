import sys
import os
import time
import yfinance as yf
import gspread
from datetime import datetime
from google.oauth2.service_account import Credentials
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import TICKERS, SECTORS, STARTING_CAPITAL, NOTIFICATION_EMAIL, GMAIL_APP_PASSWORD
from agents.sentiment import get_regime
from agents.options_strategy import analyze_trade, STRATEGY_RULES
from agents.options_paper import log_trade
from agents.risk import check_correlation
from ml.predict import predict_win_probability
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Replaced by correlation-aware sizing + MAX_SECTOR_DOLLAR_EXPOSURE cap below
ML_PROBABILITY_FLOOR = 55
MAX_SECTOR_DOLLAR_EXPOSURE = STARTING_CAPITAL * 0.15  # cap total $ risk per sector per day
CORRELATION_THRESHOLD = 0.7


def clean(val):
    try:
        if val != val:
            return 0
        return round(float(val), 2)
    except:
        return 0


def get_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
    client = gspread.authorize(creds)
    return client.open("Trading Bot Log")


def get_already_alerted_today():
    try:
        sheet = get_sheets()
        try:
            tracker = sheet.worksheet("Daily Alerts Tracker")
        except gspread.exceptions.WorksheetNotFound:
            tracker = sheet.add_worksheet(title="Daily Alerts Tracker", rows=1000, cols=3)
            tracker.append_row(["Date", "Ticker", "Time"])
            return set()

        rows = tracker.get_all_values()
        today = datetime.now().strftime("%Y-%m-%d")
        alerted = set()
        keep_rows = [rows[0]] if rows else [["Date", "Ticker", "Time"]]

        for row in rows[1:]:
            if len(row) >= 2 and row[0] == today:
                alerted.add(row[1])
                keep_rows.append(row)
            # rows from previous days are simply dropped -- no longer relevant
            # for "already alerted today" and keeps the tab from growing forever

        if len(keep_rows) < len(rows):
            tracker.clear()
            tracker.update(values=keep_rows, range_name='A1')

        return alerted
    except Exception as e:
        print(f"Error reading alert tracker: {e}")
        return set()


def mark_alerted(ticker):
    try:
        sheet = get_sheets()
        tracker = sheet.worksheet("Daily Alerts Tracker")
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        today = datetime.now().strftime("%Y-%m-%d")
        tracker.append_row([today, ticker, now])
    except Exception as e:
        print(f"Error marking alert: {e}")


def get_todays_alerted_tickers_with_sector(target_sector):
    """Returns tickers already alerted today in the SAME sector, for correlation checking."""
    try:
        sheet = get_sheets()
        today = datetime.now().strftime("%Y-%m-%d")

        opt = sheet.worksheet("Options Paper Trades")
        opt_rows = opt.get_all_values()

        same_sector_today = []
        for row in opt_rows[1:]:
            if len(row) >= 4 and row[1].startswith(today) and row[3] == target_sector:
                same_sector_today.append(row[2])  # ticker column

        return same_sector_today
    except Exception as e:
        print(f"Error checking sector exposure: {e}")
        return []


def get_sector_dollar_exposure(sector_tickers):
    """Sum up total_risk already committed today for a list of tickers."""
    try:
        sheet = get_sheets()
        opt = sheet.worksheet("Options Paper Trades")
        rows = opt.get_all_values()
        today = datetime.now().strftime("%Y-%m-%d")

        total = 0.0
        for row in rows[1:]:
            if len(row) >= 15 and row[1].startswith(today) and row[2] in sector_tickers:
                try:
                    total += float(row[14])  # total_risk column
                except:
                    continue
        return total
    except Exception as e:
        print(f"Error summing sector exposure: {e}")
        return 0.0


def adjust_size_for_correlation(trade, sector_tickers_today):
    """
    If this new ticker is highly correlated with anything already alerted
    today in the same sector, scale down its position size to reflect that
    it's largely the SAME bet, not an independent one.
    """
    if not sector_tickers_today:
        return trade, None  # first in this sector today, no adjustment needed

    try:
        all_tickers = sector_tickers_today + [trade["ticker"]]
        corr_pairs = check_correlation(all_tickers)
        is_correlated = any(
            trade["ticker"] in (t1, t2) and val > CORRELATION_THRESHOLD
            for t1, t2, val in corr_pairs
        )
    except Exception:
        is_correlated = False

    note = None
    if is_correlated:
        cluster_size = len(sector_tickers_today) + 1
        scale_factor = 1 / cluster_size
        scale_factor = max(scale_factor, 0.25)

        original_risk = trade["total_risk"]
        original_contracts = trade["contracts"]
        trade["contracts"] = max(1, int(original_contracts * scale_factor))
        per_contract_risk = original_risk / max(original_contracts, 1)
        trade["total_risk"] = round(per_contract_risk * trade["contracts"], 2)
        trade["position_pct"] = round(trade["position_pct"] * scale_factor, 1)

        note = (f"Correlated with {', '.join(sector_tickers_today)} (same sector move) -- "
                f"position size reduced to {round(scale_factor*100)}% of normal")

    return trade, note


def quick_score_stock(ticker, sector, etf_return, vix_price):
    try:
        df = yf.Ticker(ticker).history(period="1y")
        if df.empty or len(df) < 200:
            return None

        closes = df["Close"].dropna()
        delta = closes.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / loss
        rsi = float(100 - (100 / (1 + rs.iloc[-1])))

        ma20 = closes.rolling(20).mean()
        bb_lower = ma20 - 2 * closes.rolling(20).std()
        bb_upper = ma20 + 2 * closes.rolling(20).std()

        ema12 = closes.ewm(span=12).mean()
        ema26 = closes.ewm(span=26).mean()
        macd = ema12 - ema26
        signal_line = macd.ewm(span=9).mean()

        ma50 = closes.rolling(50).mean()
        ma200 = closes.rolling(200).mean()
        vol_avg = df["Volume"].rolling(20).mean()

        price = float(closes.iloc[-1])
        bb_low = float(bb_lower.iloc[-1])
        ma50_val = float(ma50.iloc[-1])
        ma200_val = float(ma200.iloc[-1])
        macd_val = float(macd.iloc[-1])
        macd_sig = float(signal_line.iloc[-1])
        vol_now = float(df["Volume"].iloc[-1])
        vol_avg_val = float(vol_avg.iloc[-1])

        if any(v != v for v in [price, rsi, macd_val, macd_sig, bb_low, ma50_val, ma200_val]):
            return None

        volume_spike = vol_now > vol_avg_val

        lookback = min(20, len(closes) - 1)
        stock_return = (closes.iloc[-1] / closes.iloc[-lookback] - 1) * 100
        rel_strength = float(stock_return) - float(etf_return)
        if rel_strength != rel_strength:
            rel_strength = 0

        mr_score = 0
        if rsi < 35:
            mr_score += 0.5
        if price <= bb_low:
            mr_score += 0.5
        if macd_val > macd_sig:
            mr_score += 0.5

        trend_score = 0
        if ma50_val > ma200_val:
            trend_score += 1.0
        if price > ma50_val:
            trend_score += 1.0

        sector_score = 0
        if rel_strength > 0.02:
            sector_score = 1.5
        elif rel_strength > 0:
            sector_score = 0.75

        vol_score = 0.5 if volume_spike else 0

        if rsi < 40 and price <= bb_low:
            trade_mode = "MEAN_REVERSION"
            weighted = (mr_score * 1.5) + (trend_score * 0.5) + sector_score + vol_score
        elif ma50_val > ma200_val and price > ma50_val:
            trade_mode = "MOMENTUM"
            weighted = (mr_score * 0.5) + (trend_score * 1.5) + sector_score + vol_score
        else:
            trade_mode = "NEUTRAL"
            weighted = mr_score + trend_score + sector_score + vol_score

        score = round(min(weighted, 10), 2)

        return {
            "ticker": ticker,
            "sector": sector,
            "price": price,
            "score": score,
            "trend_score": trend_score,
            "sector_score": sector_score,
            "mr_score": mr_score,
            "vol_score": vol_score,
            "trade_mode": trade_mode,
            "rsi": rsi
        }
    except Exception:
        return None


def get_news_headlines(ticker, max_items=4):
    try:
        stock = yf.Ticker(ticker)
        news = stock.news[:max_items] if stock.news else []
        headlines = []
        for item in news:
            title = item.get("content", {}).get("title", "")
            link = item.get("content", {}).get("canonicalUrl", {}).get("url", "")
            if title:
                headlines.append({"title": title, "url": link})
        return headlines
    except Exception:
        return []


def send_alert_email(trade, ml_prob, headlines, regime, correlation_note=None):
    spread = trade["spread"]
    if trade["strategy"] == "SELL_PUT_SPREAD":
        spread_desc = f"Sell ${spread['short_strike']}P / Buy ${spread['long_strike']}P"
        credit_text = f"Credit: ${spread['net_credit']}"
        iv = spread.get("short_iv", 0)
    else:
        spread_desc = f"Buy ${spread['long_strike']}C / Sell ${spread['short_strike']}C"
        credit_text = f"Debit: ${spread['net_debit']}"
        iv = spread.get("long_iv", 0)

    news_html = ""
    if headlines:
        for h in headlines:
            news_html += f'<li style="margin-bottom:8px;"><a href="{h["url"]}" style="color:#5bb0ff;text-decoration:none;font-size:13px;">{h["title"]}</a></li>'
    else:
        news_html = '<li style="color:#666;font-size:13px;">No recent headlines found</li>'

    correlation_html = ""
    if correlation_note:
        correlation_html = f'''<div style="background:#2a1f0a;border:1px solid #5a4419;border-radius:8px;padding:12px 16px;margin-bottom:16px;">
      <p style="margin:0;color:#f0c674;font-size:13px;font-weight:600;">⚠️ Correlation Notice</p>
      <p style="margin:4px 0 0;color:#d4b483;font-size:12px;">{correlation_note}</p>
    </div>'''

    now = datetime.now().strftime("%B %d, %Y %I:%M %p CDT")

    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0f0f0f;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<div style="max-width:600px;margin:0 auto;padding:24px;">

  <div style="background:#1a1a1a;border-radius:12px;padding:24px;border:1px solid #2a2a2a;">
    <h1 style="margin:0 0 4px;color:#fff;font-size:20px;font-weight:700;">⚡ Intraday Signal — {trade['ticker']}</h1>
    <p style="margin:0 0 16px;color:#666;font-size:13px;">{now} | Regime: {regime}</p>

    <div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;">
      <div style="background:#111;border-radius:8px;padding:12px 16px;flex:1;text-align:center;">
        <p style="margin:0;color:#666;font-size:11px;">Score</p>
        <p style="margin:4px 0 0;color:#27ae60;font-size:18px;font-weight:700;">{trade['score']}</p>
      </div>
      <div style="background:#111;border-radius:8px;padding:12px 16px;flex:1;text-align:center;">
        <p style="margin:0;color:#666;font-size:11px;">ML Probability</p>
        <p style="margin:4px 0 0;color:#27ae60;font-size:18px;font-weight:700;">{ml_prob}%</p>
      </div>
      <div style="background:#111;border-radius:8px;padding:12px 16px;flex:1;text-align:center;">
        <p style="margin:0;color:#666;font-size:11px;">Confidence</p>
        <p style="margin:4px 0 0;color:#fff;font-size:18px;font-weight:700;">{trade['confidence']}</p>
      </div>
    </div>

    {correlation_html}

    <div style="background:#111;border-radius:8px;padding:16px;margin-bottom:16px;">
      <p style="margin:0 0 8px;color:#fff;font-size:14px;font-weight:600;">Trade Setup</p>
      <p style="margin:0;color:#aaa;font-size:13px;">Strategy: {trade['strategy'].replace('_',' ')}</p>
      <p style="margin:4px 0 0;color:#aaa;font-size:13px;">Spread: {spread_desc}</p>
      <p style="margin:4px 0 0;color:#27ae60;font-size:13px;font-weight:600;">{credit_text} | ROR: {spread['return_on_risk']}%</p>
      <p style="margin:4px 0 0;color:#aaa;font-size:13px;">Breakeven: ${spread['breakeven']} | IV: {iv}% | Exp: {spread['expiration']}</p>
      <p style="margin:4px 0 0;color:#aaa;font-size:13px;">Contracts: {trade['contracts']} | Total Risk: ${trade['total_risk']} | Size: {trade['position_pct']}% of portfolio</p>
    </div>

    <div style="background:#111;border-radius:8px;padding:16px;">
      <p style="margin:0 0 8px;color:#fff;font-size:14px;font-weight:600;">Recent News</p>
      <ul style="margin:0;padding-left:18px;">{news_html}</ul>
    </div>

    <p style="margin:16px 0 0;color:#444;font-size:11px;text-align:center;">Paper trade logged automatically. Trading Bot — Intraday Alert</p>
  </div>
</div>
</body>
</html>
"""

    try:
        msg = MIMEMultipart("alternative")
        msg['From'] = NOTIFICATION_EMAIL
        msg['To'] = NOTIFICATION_EMAIL
        msg['Subject'] = f"⚡ Trade Signal: {trade['ticker']} | {trade['confidence']} | {ml_prob}% ML prob"
        msg.attach(MIMEText(html, 'html'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(NOTIFICATION_EMAIL, GMAIL_APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"Alert email sent for {trade['ticker']}")
    except Exception as e:
        print(f"Error sending alert email: {e}")


def run_live_monitor():
    print(f"\n{'='*50}")
    print(f"LIVE MONITOR — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")

    print("Checking market regime...")
    regime_data = get_regime()
    regime = regime_data["regime"]
    vix_price = regime_data.get("vix", 20.0)

    already_alerted = get_already_alerted_today()
    print(f"Already alerted today: {already_alerted if already_alerted else 'none'}")

    print("Fetching sector ETF returns...")
    etf_returns = {}
    for sector, etf in SECTORS.items():
        try:
            df = yf.Ticker(etf).history(period="1mo")
            closes = df["Close"].dropna()
            if len(closes) > 20:
                ret = (closes.iloc[-1] / closes.iloc[-20] - 1) * 100
                etf_returns[sector] = float(ret) if ret == ret else 0
            else:
                etf_returns[sector] = 0
        except:
            etf_returns[sector] = 0

    new_alerts = 0
    checked = 0

    for sector, tickers in TICKERS.items():
        etf_ret = etf_returns.get(sector, 0)
        for ticker in tickers:
            if ticker in already_alerted:
                continue

            checked += 1
            sig = quick_score_stock(ticker, sector, etf_ret, vix_price)
            if sig is None:
                continue

            key = (sig["trade_mode"], regime)
            rule = STRATEGY_RULES.get(key)
            if not rule or rule["strategy"] == "NO_TRADE":
                continue

            # Only HIGH and MEDIUM confidence combos can ever trigger an
            # intraday alert. LOW and AVOID are skipped entirely -- the
            # deduplicated backtest showed those barely beat a coin flip.
            if rule["confidence"] not in ("HIGH", "MEDIUM"):
                continue
            if rule["confidence"] == "HIGH" and sig["score"] < 4.0:
                continue
            if rule["confidence"] == "MEDIUM" and sig["score"] < 4.5:
                continue

            try:
                ml_prob = predict_win_probability(
                    score=sig["score"], trend_score=sig["trend_score"],
                    sector_score=sig["sector_score"], mr_score=sig["mr_score"],
                    vol_score=sig["vol_score"], vix=vix_price,
                    sector=sector, mode=sig["trade_mode"], regime=regime
                )
            except Exception:
                ml_prob = 50.0

            if ml_prob < ML_PROBABILITY_FLOOR:
                continue

            print(f"\n>>> SIGNAL FOUND: {ticker} | Score {sig['score']} | ML {ml_prob}% | {sig['trade_mode']} + {regime} | {rule['confidence']}")

            trade = analyze_trade(ticker, sector, sig["score"], sig["trade_mode"], regime, sig["price"], STARTING_CAPITAL)
            if trade is None:
                print(f"    Could not build options trade for {ticker}, skipping alert")
                continue

            # Check existing sector exposure today -- hard dollar cap regardless
            # of correlation, prevents one sector from dominating the whole day
            sector_today_tickers = get_todays_alerted_tickers_with_sector(sector)
            current_exposure = get_sector_dollar_exposure(sector_today_tickers)

            if current_exposure >= MAX_SECTOR_DOLLAR_EXPOSURE:
                print(f"    SKIP — {sector} already at ${current_exposure:.0f} exposure today (cap: ${MAX_SECTOR_DOLLAR_EXPOSURE:.0f})")
                continue

            # Scale down size if correlated with something already alerted today
            trade, correlation_note = adjust_size_for_correlation(trade, sector_today_tickers)
            if correlation_note:
                print(f"    {correlation_note}")

            # Re-check the cap after sizing adjustment
            if current_exposure + trade["total_risk"] > MAX_SECTOR_DOLLAR_EXPOSURE:
                remaining = MAX_SECTOR_DOLLAR_EXPOSURE - current_exposure
                if remaining < 50:
                    print(f"    SKIP — {sector} exposure cap reached, no room remaining")
                    continue
                scale = remaining / trade["total_risk"]
                trade["contracts"] = max(1, int(trade["contracts"] * scale))
                trade["total_risk"] = round(trade["total_risk"] * scale, 2)
                trade["position_pct"] = round(trade["position_pct"] * scale, 1)
                extra_note = f"Further reduced to fit remaining ${remaining:.0f} sector cap"
                correlation_note = f"{correlation_note} | {extra_note}" if correlation_note else extra_note

            log_trade(trade)
            headlines = get_news_headlines(ticker)
            send_alert_email(trade, ml_prob, headlines, regime, correlation_note=correlation_note)
            mark_alerted(ticker)
            new_alerts += 1

            time.sleep(1.5)

    print(f"\n{'='*50}")
    print(f"LIVE MONITOR COMPLETE")
    print(f"Stocks checked: {checked}")
    print(f"New alerts sent: {new_alerts}")
    print(f"{'='*50}")


if __name__ == "__main__":
    run_live_monitor()
    