#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""LINE Official Account chat history exporter."""

import json
import csv
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
        timeout=30,
        follow_redirects=False,
        headers={
            "Cookie": cookie_str,
            "X-XSRF-TOKEN": xsrf,
            "Referer": f"{config['baseUrl']}/{config['botId']}/chat/",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
            "Accept": "application/json",
        },
    )


def list_chats(client, config, limit=25):
    """Fetch all chats, paginating through the full list."""
    bot_id = config["botId"]
    base = config["baseUrl"]
    all_chats = []
    url = f"{base}/api/v2/bots/{bot_id}/chats?limit={limit}"

    while url:
        print(f"  GET {url.replace(base, '')}", flush=True)
        resp = client.get(url)
        if resp.status_code != 200:
            print(f"[ERROR] list_chats: {resp.status_code} {resp.text[:300]}", flush=True)
            sys.exit(1)
        data = resp.json()
        all_chats.extend(data.get("list", []))
        cursor = data.get("next")
        if cursor:
            url = f"{base}/api/v2/bots/{bot_id}/chats?limit={limit}&next={cursor}"
        else:
            url = None
        time.sleep(0.2)

    return all_chats


def fetch_messages(client, config, chat_id):
    """Fetch all messages for a chat, paginating backward to the beginning."""
    bot_id = config["botId"]
    base = config["baseUrl"]
    all_messages = []
    url = f"{base}/api/v3/bots/{bot_id}/chats/{chat_id}/messages?limit=50"

    page = 0
    while url:
        resp = client.get(url)
        if resp.status_code != 200:
            print(f"[ERROR] fetch_messages: {resp.status_code} {resp.text[:300]}", flush=True)
            break
        data = resp.json()
        messages = data.get("list", [])
        all_messages.extend(messages)
        page += 1
        print(f"  page {page}: {len(messages)} events (total {len(all_messages)})", flush=True)

        cursor = data.get("backward")
        if cursor:
            url = f"{base}/api/v3/bots/{bot_id}/chats/{chat_id}/messages?limit=50&backward={cursor}"
        else:
            url = None
        time.sleep(0.05)

    # Reverse so oldest messages come first
    all_messages.reverse()
    return all_messages


def ts_to_str(ts_ms, tz_offset_min):
    """Convert millisecond timestamp to readable string."""
    tz = timezone(timedelta(minutes=tz_offset_min))
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=tz)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def save_chat(config, chat_meta, messages):
    """Save messages as JSON and CSV."""
    chat_id = chat_meta["chatId"]
    name = chat_meta.get("profile", {}).get("name", chat_id)
    tz_offset = config.get("timezoneOffset", 420)
    chat_dir = OUTPUT_DIR / chat_id
    chat_dir.mkdir(parents=True, exist_ok=True)

    # JSON
    with open(chat_dir / "messages.json", "w", encoding="utf-8") as f:
        json.dump({"chatId": chat_id, "name": name, "messages": messages}, f, ensure_ascii=False, indent=2)

    # CSV — flatten to readable rows
    rows = []
    for evt in messages:
        evt_type = evt.get("type", "")
        ts = evt.get("timestamp")
        ts_str = ts_to_str(ts, tz_offset) if ts else ""
        msg = evt.get("message", {})
        msg_type = msg.get("type", "")
        text = msg.get("text", "")

        if evt_type == "message":
            direction = "received"
        elif evt_type == "messageSent":
            direction = "sent"
        else:
            direction = evt_type

        # For non-text messages, note the type
        if msg_type and msg_type != "text" and not text:
            text = f"[{msg_type}]"

        rows.append({
            "timestamp": ts_str,
            "timestamp_ms": ts or "",
            "direction": direction,
            "message_type": msg_type,
            "text": text,
            "message_id": msg.get("id", ""),
            "event_type": evt_type,
        })

    with open(chat_dir / "messages.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "timestamp_ms", "direction", "message_type", "text", "message_id", "event_type"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"  saved {len(messages)} events → {chat_dir}/", flush=True)


def main():
    config = load_config()
    client = make_client(config)

    # Check cookies are set
    if not config["cookies"].get("__Host-chat-ses"):
        print("ERROR: cookies not set in config.json. Paste your session cookies first.")
        sys.exit(1)

    # Fetch just the first page to get one chat for testing
    print("Fetching first page of chats...", flush=True)
    bot_id = config["botId"]
    base = config["baseUrl"]
    resp = client.get(f"{base}/api/v2/bots/{bot_id}/chats?limit=25")
    if resp.status_code != 200:
        print(f"[ERROR] {resp.status_code} {resp.text[:300]}", flush=True)
        sys.exit(1)
    data = resp.json()
    chats = data.get("list", [])
    print(f"Got {len(chats)} chats on first page\n", flush=True)

    if not chats:
        print("No chats found. Check cookies / botId.")
        sys.exit(1)

    target = chats[:1]

    for chat in target:
        chat_id = chat["chatId"]
        name = chat.get("profile", {}).get("name", chat_id)
        print(f"Exporting: {name} ({chat_id})", flush=True)
        messages = fetch_messages(client, config, chat_id)
        save_chat(config, chat, messages)
        print(flush=True)

    print("Done.", flush=True)


if __name__ == "__main__":
    main()
