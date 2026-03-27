#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""LINE OA per-chat CSV export via /download endpoint."""

import argparse
import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

import httpx

CONFIG_PATH = Path(__file__).parent / "config.json"
OUTPUT_DIR = Path(__file__).parent / "output"


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def make_client(config):
    cookies = config["cookies"]
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    xsrf = cookies["XSRF-TOKEN"]

    return httpx.Client(
        timeout=60,
        follow_redirects=False,
        headers={
            "Cookie": cookie_str,
            "X-XSRF-TOKEN": xsrf,
            "Referer": f"{config['baseUrl']}/{config['botId']}/chat/",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
            "Accept": "*/*",
        },
    )


def list_chats(client, config, limit=25, cutoff_ms=None, max_chats=None):
    """Fetch chats, paginating. Stops at cutoff_ms or max_chats."""
    bot_id = config["botId"]
    base = config["baseUrl"]
    all_chats = []
    url = f"{base}/api/v2/bots/{bot_id}/chats?limit={limit}"
    done = False

    while url and not done:
        resp = client.get(url)
        if resp.status_code != 200:
            print(f"[ERROR] list_chats: {resp.status_code} {resp.text[:300]}", flush=True)
            sys.exit(1)
        data = resp.json()
        for chat in data.get("list", []):
            if cutoff_ms and chat.get("updatedAt", 0) < cutoff_ms:
                done = True
                break
            all_chats.append(chat)
            if max_chats and len(all_chats) >= max_chats:
                done = True
                break
        cursor = data.get("next")
        if cursor and not done:
            url = f"{base}/api/v2/bots/{bot_id}/chats?limit={limit}&next={cursor}"
        else:
            url = None
        time.sleep(0.2)

    return all_chats


def download_chat_csv(client, config, chat_id):
    """Download CSV for a single chat via /download endpoint."""
    bot_id = config["botId"]
    base = config["baseUrl"]
    tz = config.get("timezoneOffset", 420)
    url = f"{base}/download/{bot_id}/{chat_id}/messages.csv?timezoneOffset=-{tz}"

    resp = client.get(url)
    if resp.status_code in (401, 302):
        print(f"\n[ERROR] Session expired. Refresh cookies in config.json.", flush=True)
        sys.exit(1)
    if resp.status_code != 200:
        print(f"  [ERROR] {resp.status_code} {resp.text[:200]}", flush=True)
        return None
    return resp.text


def main():
    parser = argparse.ArgumentParser(description="Export LINE OA chat history")
    parser.add_argument("--go-back-days", type=int, default=None,
                        help="Only export chats updated in the last N days")
    parser.add_argument("--max-chats", type=int, default=None,
                        help="Max number of chats to export")
    args = parser.parse_args()

    config = load_config()
    client = make_client(config)

    if not config["cookies"].get("__Host-chat-ses"):
        print("ERROR: cookies not set in config.json.")
        sys.exit(1)

    cutoff_ms = None
    if args.go_back_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=args.go_back_days)
        cutoff_ms = int(cutoff.timestamp() * 1000)
        print(f"Filtering to last {args.go_back_days} days (since {cutoff.strftime('%Y-%m-%d %H:%M UTC')})", flush=True)

    print("Fetching chat list...", flush=True)
    chats = list_chats(client, config, cutoff_ms=cutoff_ms, max_chats=args.max_chats)
    print(f"Found {len(chats)} chats\n", flush=True)

    if not chats:
        print("No chats found.")
        sys.exit(0)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for i, chat in enumerate(chats, 1):
        chat_id = chat["chatId"]
        name = chat.get("profile", {}).get("name", chat_id)
        print(f"[{i}/{len(chats)}] {name} ({chat_id})", flush=True)

        csv_data = download_chat_csv(client, config, chat_id)
        if csv_data:
            chat_dir = OUTPUT_DIR / chat_id
            chat_dir.mkdir(parents=True, exist_ok=True)
            with open(chat_dir / "messages.csv", "w", encoding="utf-8") as f:
                f.write(csv_data)
            lines = csv_data.count("\n")
            print(f"  saved {lines} lines", flush=True)
        time.sleep(0.2)

    print("\nDone.", flush=True)


if __name__ == "__main__":
    main()
