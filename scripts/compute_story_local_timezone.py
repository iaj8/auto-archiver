#!/usr/bin/env python
# coding: utf-8

from google.oauth2 import service_account

import gspread
from gspread.exceptions import APIError

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from timezonefinder import TimezoneFinder

from datetime import datetime

import pytz

SCOPES = ['https://www.googleapis.com/auth/drive']


def compute_and_enter_story_local_timezone(service_account_path, sheet_id, worksheet_name):
    creds = service_account.Credentials.from_service_account_file(service_account_path, scopes=SCOPES)
    gsheet_client = gspread.authorize(creds)

    spreadsheet = gsheet_client.open_by_key(sheet_id)
    sheet = spreadsheet.worksheet(worksheet_name)

    lat_long = sheet.acell("F2").value

    if lat_long.strip() == "":
        return
    
    sheet.update_acell("H2", "Timezone not found for the given coordinates.")

    [latitude, longitude] = lat_long.split(",")
    
    latitude = float(latitude.strip())
    longitude = float(longitude.strip())

    # Get the timezone
    tf = TimezoneFinder()
    timezone_name = tf.timezone_at(lat=latitude, lng=longitude)  # Returns the timezone name

    if timezone_name:
        # Get the timezone object
        timezone = pytz.timezone(timezone_name)
        
        # Get the current time in the timezone
        now = datetime.now(timezone)
        
        # Calculate the UTC offset
        utc_offset = now.utcoffset().total_seconds() / 3600  # Convert seconds to hours
        
        # Format as UTC+X or UTC-X
        sheet.update_acell("H2", f"UTC{'+' if utc_offset >= 0 else ''}{utc_offset:.2f}")
    else:
        sheet.update_acell("H2", "Timezone not found for the given coordinates.")