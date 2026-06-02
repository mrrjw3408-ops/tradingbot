import yfinance as yf
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

print("Starting...")

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
print("Credentials loaded...")

client = gspread.authorize(creds)
print("Google client authorized...")

sheet = client.open("Trading Bot Log").sheet1
print("Sheet opened...")

print("All good! Google Sheets connected!")

