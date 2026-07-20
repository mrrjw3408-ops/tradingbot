import gspread
from google.oauth2.service_account import Credentials

scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
client = gspread.authorize(creds)
sheet = client.open('Trading Bot Log')
opt = sheet.worksheet('Options Paper Trades')
rows = opt.get_all_values()

duplicate_ids = ["OPT-20260706165313", "OPT-20260706165321"]

rows_to_delete = []
for i, row in enumerate(rows[1:], start=2):
    if row[0] in duplicate_ids:
        rows_to_delete.append((i, row[0], row[2]))

print("Rows found to delete:")
for r in rows_to_delete:
    print(f"  Row {r[0]}: {r[1]} ({r[2]})")

for row_num, trade_id, ticker in sorted(rows_to_delete, key=lambda x: -x[0]):
    opt.delete_rows(row_num)
    print(f"Deleted row {row_num}: {trade_id} ({ticker})")
