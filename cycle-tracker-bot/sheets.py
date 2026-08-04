import os
import json
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
SHEET_NAME = "CycleTracker"

HEADERS = [
    "date",
    "mood", "mood_note",
    "health", "health_note",
    "relationship", "relationship_note",
    "motivation", "motivation_note",
    "cycle_day",
    "notes",
]

def _get_sheet():
    # Локально — читає credentials.json, на Railway — з env змінної
    if os.path.exists("credentials.json"):
        creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    else:
        creds_json = json.loads(os.environ["GOOGLE_CREDENTIALS"])
        creds = Credentials.from_service_account_info(creds_json, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME).sheet1

def append_row(data: dict):
    sheet = _get_sheet()
    if not sheet.row_values(1):
        sheet.append_row(HEADERS)
    row = [data.get(h, "") for h in HEADERS]
    sheet.append_row(row)

def get_last_rows(n: int = 7) -> list[dict]:
    sheet = _get_sheet()
    all_rows = sheet.get_all_records()
    return all_rows[-n:] if len(all_rows) >= n else all_rows

def get_all_rows() -> list[dict]:
    sheet = _get_sheet()
    return sheet.get_all_records()
