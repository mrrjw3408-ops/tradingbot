import gspread
from collections import Counter
from datetime import datetime
from google.oauth2.service_account import Credentials

scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
client = gspread.authorize(creds)
opt = client.open('Trading Bot Log').worksheet('Options Paper Trades')
rows = opt.get_all_values()[1:]

today = datetime.now().date()
status = Counter(r[19] for r in rows if len(r) >= 20)
print("Status counts:", dict(status))

open_rows = [r for r in rows if len(r) >= 20 and r[19] == 'OPEN']
past_expiry = 0
by_day = Counter()
for r in open_rows:
    try:
        if datetime.strptime(r[9], '%Y-%m-%d').date() < today:
            past_expiry += 1
    except Exception:
        pass
    by_day[r[0][4:12]] += 1

print(f"Open: {len(open_rows)} | already past expiration: {past_expiry}")
print("Open trades by day opened (from trade ID):")
for d in sorted(by_day):
    print(f"  {d}: {by_day[d]}")
