#!/usr/bin/env python3
"""
fetch.py — Pull new Bloomberg emails from Gmail and archive them as .txt files.

Fetches emails from the past LOOKBACK_DAYS days (default 4, so weekend gaps
are always covered). Already-archived IDs in saved_ids.txt are skipped.
"""

import os
import re
import base64
import argparse
from datetime import datetime, timedelta
from email.utils import parsedate
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")
CREDS_PATH = os.path.join(BASE_DIR, "credentials.json")
INDEX_PATH = os.path.join(BASE_DIR, "saved_ids.txt")

LOOKBACK_DAYS = 4  # Mon run catches Fri; Sat run still covered


def get_service():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_PATH, "w") as f:
                f.write(creds.to_json())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(TOKEN_PATH, "w") as f:
                f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def fetch_message_ids(service, query: str) -> list[str]:
    """Return all message IDs matching query, handling pagination."""
    ids = []
    page_token = None
    while True:
        kwargs = {"userId": "me", "q": query, "maxResults": 500}
        if page_token:
            kwargs["pageToken"] = page_token
        resp = service.users().messages().list(**kwargs).execute()
        ids.extend(m["id"] for m in resp.get("messages", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return ids


def extract_body(payload: dict) -> str:
    if "parts" in payload:
        for part in payload["parts"]:
            if part["mimeType"] == "text/plain" and "data" in part.get("body", {}):
                return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
    if "data" in payload.get("body", {}):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
    return ""


def main():
    parser = argparse.ArgumentParser(description="Fetch Bloomberg emails from Gmail.")
    parser.add_argument("--days", type=int, default=LOOKBACK_DAYS,
                        help="How many days back to search (default: %(default)s)")
    args = parser.parse_args()

    service = get_service()

    after_date = (datetime.now() - timedelta(days=args.days)).strftime("%Y/%m/%d")
    query = f"from:bloomberg.com after:{after_date}"
    print(f"Query: {query}")

    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH) as f:
            saved_ids = set(f.read().splitlines())
    else:
        saved_ids = set()

    all_ids = fetch_message_ids(service, query)
    new_ids = [i for i in all_ids if i not in saved_ids]
    print(f"Found {len(all_ids)} emails in window, {len(new_ids)} new")

    saved = 0
    for msg_id in new_ids:
        msg = service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()

        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        subject = headers.get("Subject", "no_subject")
        date_str = headers.get("Date", "")

        try:
            parsed_date = datetime(*parsedate(date_str)[:6])
        except Exception:
            parsed_date = datetime.now()

        day_folder = os.path.join(
            BASE_DIR,
            parsed_date.strftime("%Y"),
            parsed_date.strftime("%m"),
            parsed_date.strftime("%d"),
        )
        os.makedirs(day_folder, exist_ok=True)

        slug = re.sub(r'[^a-zA-Z0-9]+', '_', subject).strip('_').lower()[:60]
        filepath = os.path.join(day_folder, f"{msg_id}_{slug}.txt")
        body = extract_body(msg["payload"])
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"Subject: {subject}\nDate: {date_str}\n\n{body}")

        with open(INDEX_PATH, "a") as f:
            f.write(msg_id + "\n")

        saved += 1

    print(f"{datetime.now()} — saved {saved} new emails")


if __name__ == "__main__":
    main()