import json

from google.oauth2 import service_account
from googleapiclient.discovery import build

import config

_creds = None
_calendar = None
_sheets = None


def get_credentials():
    global _creds
    if _creds is None:
        if config.GOOGLE_SERVICE_ACCOUNT_JSON:
            info = json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON)
            _creds = service_account.Credentials.from_service_account_info(
                info, scopes=config.SCOPES
            )
        else:
            _creds = service_account.Credentials.from_service_account_file(
                config.SERVICE_ACCOUNT_FILE,
                scopes=config.SCOPES,
            )
    return _creds


def get_calendar_service():
    global _calendar
    if _calendar is None:
        _calendar = build("calendar", "v3", credentials=get_credentials())
    return _calendar


def get_sheets_service():
    global _sheets
    if _sheets is None:
        _sheets = build("sheets", "v4", credentials=get_credentials())
    return _sheets
