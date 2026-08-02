# telegram-call-bot

Production-oriented Telegram bot and example backend for placing outbound calls through a backend-controlled trunk provider.

## Features

- Telegram-based user registration/login using Telegram identity
- User profile, selected caller ID, and credit tracking stored with SQLAlchemy
- Backend-driven available number list and caller ID selection
- Outbound call placement, live status polling, call ending, and recent call history
- Example Flask backend endpoints for auth, numbers, call routing, status, and history logging
- `.env` driven configuration, structured logging, and SQLite-friendly local setup

## Project structure

```text
.
├── app/
│   ├── api_client.py
│   ├── backend.py
│   ├── bot.py
│   ├── config.py
│   ├── database.py
│   ├── logging_config.py
│   ├── models.py
│   └── repository.py
├── tests/
│   └── test_backend.py
├── .env.example
├── main.py
└── requirements.txt
```

## Requirements

- Python 3.11+
- A Telegram bot token from BotFather

## Deployment

### Option 1 — Docker Compose (recommended for VPS)

Requires [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/).

```bash
cp .env.example .env
# Edit .env and set TELEGRAM_BOT_TOKEN (and any other values you want to change)
docker compose up -d
```

Both the backend and bot start automatically. The SQLite database is stored in a
named Docker volume (`db_data`) so data survives restarts and container rebuilds.

To view logs:

```bash
docker compose logs -f
```

To stop:

```bash
docker compose down
```

### Option 2 — Railway

1. Push this repository to GitHub.
2. Go to [railway.app](https://railway.app) and create a **New Project → Deploy from GitHub repo**.
3. Create **two services** from the same repo:
   - **backend** — set *Start Command* to `python -m app.backend`
   - **bot** — set *Start Command* to `python main.py`
4. In the **backend** service, add a *Public Domain* so the bot can reach it. Copy that URL.
5. Set the following environment variables on **both** services (Railway Dashboard → Variables):

   | Variable | Value |
   | --- | --- |
   | `TELEGRAM_BOT_TOKEN` | your token from BotFather |
   | `DATABASE_URL` | Railway PostgreSQL URL (add a PostgreSQL plugin) |
   | `BACKEND_API_BASE_URL` | `https://<your-backend-domain>/api` (bot service only) |
   | `BACKEND_HOST` | `0.0.0.0` (backend service only) |

6. Click **Deploy**. Railway detects the `Dockerfile` automatically via `railway.toml`.

### Option 3 — Local development

1. Create and activate a virtual environment.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy the example environment file and update values:

   ```bash
   cp .env.example .env
   ```

4. Start the example backend:

   ```bash
   python -m app.backend
   ```

5. Start the Telegram bot in a second terminal:

   ```bash
   python main.py
   ```

## Telegram bot commands

- `/start` — register/login the user against the backend
- `/profile` — view stored profile details and caller ID selection
- `/balance` — show current credit balance
- `/numbers` — list provisioned outbound numbers
- `/call` — prompt for a destination number and place a call
- `/status` — refresh active call statuses
- `/history` — show recent calls
- `/end` — disconnect the latest active call
- `/cancel` — cancel the current call entry flow

## Environment variables

| Variable | Description |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token used by `python-telegram-bot` |
| `BACKEND_API_BASE_URL` | Base URL for the backend API used by the bot |
| `DATABASE_URL` | SQLAlchemy database URL for user and call persistence |
| `REQUEST_TIMEOUT` | HTTP timeout in seconds for backend API requests |
| `STATUS_POLL_INTERVAL` | Seconds between call status refresh attempts |
| `DEFAULT_USER_CREDITS` | Starting credit balance assigned by the example backend |
| `AVAILABLE_NUMBERS` | Comma-separated list of provisioned outbound numbers |
| `TRUNK_PROVIDER_NAME` | Backend-owned trunk/provider label shown to users |
| `BACKEND_HOST` | Bind host for the example Flask backend |
| `BACKEND_PORT` | Bind port for the example Flask backend |
| `LOG_LEVEL` | Application log level |

## Example backend API

### Authenticate/register a Telegram user

```http
POST /api/auth/telegram
Content-Type: application/json

{
  "telegram_id": 42,
  "username": "alice",
  "first_name": "Alice",
  "last_name": "Caller"
}
```

### Get available numbers

```http
GET /api/numbers
```

### Save a selected number

```http
POST /api/users/<telegram_id>/selected-number
Content-Type: application/json

{
  "selected_number": "+12025550111"
}
```

### Place a call

```http
POST /api/calls
Content-Type: application/json

{
  "telegram_id": 42,
  "source_number": "+12025550111",
  "destination_number": "+12025550199"
}
```

### Get live call status

```http
GET /api/calls/<call_id>
```

### End a call

```http
POST /api/calls/<call_id>/end
```

### Read call history

```http
GET /api/users/<telegram_id>/calls
```

## Notes

- The Flask backend simulates call progression so the bot can demonstrate real-time updates without an external telephony vendor.
- Replace the example backend implementation in `app/backend.py` with your production routing logic and trunk integrations when ready.
- The bot stores local user and call records so history and account state survive restarts when using a persistent database.
