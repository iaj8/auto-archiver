#!/usr/bin/env python
# coding: utf-8

from google.oauth2 import service_account

import gspread
from gspread.exceptions import APIError

from time import sleep


SCOPES = ['https://www.googleapis.com/auth/drive']

DUP_HIGHLIGHT_COLOR = {
    "red": 0.9,
    "green": 0.4,
    "blue": 0.4
}


def flag_duplicates(service_account_path, sheet_id, worksheet_name):
    creds = service_account.Credentials.from_service_account_file(service_account_path, scopes=SCOPES)
    gsheet_client = gspread.authorize(creds)

    spreadsheet = gsheet_client.open_by_key(sheet_id)
    sheet = spreadsheet.worksheet(worksheet_name)

    while True:
        try:
            all_values = sheet.get_all_values()
            break
        except APIError:
            sleep(60)
    
    headers = all_values[0]

    existing_hashes = set()

    for i, values in enumerate(all_values):
        if values[headers.index("Hash")].strip() == "":
            continue

        if values[headers.index("Hash")] not in existing_hashes:
            existing_hashes.add(values[headers.index("Hash")])
        else:
            # Highlight the entire row
            sheet.format(f"{i+1}:{i+1}", {
                "backgroundColor": DUP_HIGHLIGHT_COLOR
            })