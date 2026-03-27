# LINE OA Chat History Exporter

Export chat history from LINE Official Account (`chat.line.biz`) as CSV files.

Uses the per-chat `/download/{botId}/{chatId}/messages.csv` endpoint — same as the sidebar "Export Chat" button in the web UI, but automated for all chats.

## Setup

1. Install [uv](https://docs.astral.sh/uv/)
2. Copy `config.json.example` to `config.json` and fill in your cookies:

```json
{
  "botId": "Uxxxxxxxxx",
  "baseUrl": "https://chat.line.biz",
  "timezoneOffset": 420,
  "cookies": {
    "__Host-chat-ses": "...",
    "XSRF-TOKEN": "...",
    "chat-device-group": "519",
    "ses": "..."
  }
}
```

Get cookies from browser DevTools (Application > Cookies for `chat.line.biz`). Session expires ~24h.

## Usage

```bash
# Export all chats
uv run export.py

# Last 7 days only
uv run export.py --go-back-days 7

# First 10 chats only
uv run export.py --max-chats 10

# Combine
uv run export.py --go-back-days 1 --max-chats 100
```

Output goes to `output/{chatId}/messages.csv`.

## Notes

- Chat list API is limited to 25 per page — listing many chats takes time
- CSV format is LINE's native export format (Thai headers, UTF-8 with BOM)
- Script exits immediately if session cookies expire mid-run
