# SMTP-to-SMS Telegram Bot

A production-ready Telegram bot that lets approved users send consent-based SMS notifications through SMTP-to-SMS carrier email gateways.

> ⚠️ **Important:** SMS delivery via SMTP-to-SMS gateways is controlled by mobile carriers and is not guaranteed. Messages may be delayed, filtered, blocked, or discontinued at any time. This platform is designed exclusively for sending messages to recipients who have **explicitly opted in**.

---

## Features

- 📧 **SMTP integration** — Gmail, Outlook, Zoho, or any custom SMTP server with app passwords
- 📱 **Carrier gateway support** — Verizon, AT&T, T-Mobile, Metro, Boost, Cricket, US Cellular, Consumer Cellular, Google Fi, and more
- ✅ **Consent tracking** — All recipients must be individually confirmed as opted-in
- ⛔ **Opt-out management** — Mark recipients as opted out to permanently block future messages
- 📊 **Rate limiting** — 5/min · 50/hr · 250/day per user (configurable)
- 🔒 **Encrypted credentials** — All SMTP passwords are encrypted at rest with Fernet
- 🔄 **Background queue** — Messages sent via ARQ worker with retry and exponential backoff
- 🛡️ **Admin panel** — User management, stats, audit logs, suspend/unsuspend via Telegram commands
- 🩺 **Health check** — HTTP endpoint at `/health` for monitoring
- 🐳 **Docker Compose** — One command to deploy the full stack

---

## Architecture

```
telegram-call-bot/
├── app/
│   ├── handlers/              # aiogram 3 routers
│   │   ├── __init__.py
│   │   ├── admin_handler.py   # Admin commands (/admin)
│   │   ├── keyboards.py       # Shared inline keyboard builders
│   │   ├── menu.py            # /start, /help, main menu
│   │   ├── middleware.py      # User upsert middleware
│   │   ├── recipient_handler.py
│   │   ├── send_handler.py
│   │   ├── settings_handler.py
│   │   └── smtp_handler.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── rate_limiter.py    # Redis-backed rate limits
│   │   └── smtp_service.py    # SMTP connection test + send
│   ├── workers/
│   │   ├── __init__.py
│   │   └── sms_worker.py      # ARQ background worker
│   ├── bot.py                 # aiogram bot entry point
│   ├── carriers.py            # Carrier gateway config (update here!)
│   ├── config.py              # Pydantic settings
│   ├── database.py            # Async SQLAlchemy engine
│   ├── encryption.py          # Fernet encrypt/decrypt
│   ├── logging_config.py      # Structured logging with redaction
│   ├── models.py              # ORM models
│   ├── repository.py          # Async DB helpers
│   └── web.py                 # Health check HTTP server
├── migrations/                # Alembic migrations
│   └── versions/
│       └── 0001_initial.py
├── nginx/
│   └── default.conf
├── scripts/
│   ├── backup.sh
│   ├── deploy.sh
│   └── setup.sh
├── tests/
│   ├── test_carriers.py
│   ├── test_encryption.py
│   ├── test_rate_limiter.py
│   └── test_recipient_utils.py
├── .env.example
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── main.py
├── pytest.ini
└── requirements.txt
```

---

## Quick Start (Docker)

### 1. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
```

### 2. Clone and configure

```bash
git clone <your-repo-url> /opt/smsbot
cd /opt/smsbot
cp .env.example .env
```

### 3. Edit `.env`

```bash
nano .env
```

Fill in at minimum:

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | From [@BotFather](https://t.me/BotFather) |
| `ADMIN_TELEGRAM_IDS` | Your Telegram user ID (get from [@userinfobot](https://t.me/userinfobot)) |
| `DATABASE_URL` | PostgreSQL connection URL |
| `ENCRYPTION_KEY` | Generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `POSTGRES_PASSWORD` | Password for the PostgreSQL container |

### 4. Deploy

```bash
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

This will:
1. Build Docker images
2. Start PostgreSQL and Redis
3. Run Alembic database migrations
4. Start the bot, ARQ worker, and health check server

### 5. Verify

```bash
# Check all containers are running
docker compose ps

# Check health endpoint
curl http://localhost:8080/health

# View bot logs
docker compose logs -f bot
```

---

## Local Development (without Docker)

### Requirements

- Python 3.12+
- PostgreSQL 14+
- Redis 7+

### Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env with your values

# Run migrations
alembic upgrade head

# Start the bot
python main.py

# In a second terminal, start the worker
python -m arq app.workers.sms_worker.WorkerSettings
```

---

## Bot Usage

### User Flow

1. `/start` — Opens the main menu
2. **Account Settings** → **SMTP Accounts** → **Add SMTP Account**
   - Enter SMTP host, port, username, password, encryption type
   - Bot tests the connection before saving
3. **Add Recipient** — Enter name, phone, carrier, and confirm consent
4. **Send Message** — Select SMTP account → select recipients → compose → preview → confirm

### SMTP Providers

| Provider | Host | Port | Encryption |
|---|---|---|---|
| Gmail (App Password) | `smtp.gmail.com` | 587 | TLS |
| Outlook / Microsoft 365 | `smtp.office365.com` | 587 | TLS |
| Zoho | `smtp.zoho.com` | 587 | TLS |
| Custom | Your host | Your port | TLS or SSL |

> For Gmail, use an **App Password** (not your regular password): [Google App Passwords](https://myaccount.google.com/apppasswords)

### Rate Limits

- 5 messages per minute
- 50 messages per hour
- 250 messages per day (resets at midnight in `APP_TIMEZONE`)

---

## Admin Commands

Send `/admin` to the bot (must be in `ADMIN_TELEGRAM_IDS`):

- **System Stats** — Total users, messages today, failed today
- **Users** — List users, view details, suspend/unsuspend, change limits
- **Audit Logs** — Recent action log

---

## Carrier Gateway Configuration

Carrier gateways are in `app/carriers.py`. To add or update a carrier:

```python
"mycarrier": CarrierGateway(
    key="mycarrier",
    display_name="My Carrier",
    sms_gateway="sms.mycarrier.com",
    mms_gateway="mms.mycarrier.com",
),
```

No code changes needed elsewhere — the bot reads this config at runtime.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | required | Telegram bot token |
| `ADMIN_TELEGRAM_IDS` | `[]` | Comma-separated admin Telegram IDs |
| `DATABASE_URL` | SQLite fallback | PostgreSQL connection URL |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `ENCRYPTION_KEY` | required | Fernet 32-byte base64 key |
| `APP_TIMEZONE` | `America/Detroit` | Timezone for daily limit reset |
| `DAILY_MESSAGE_LIMIT` | `250` | Max messages per user per day |
| `HOURLY_MESSAGE_LIMIT` | `50` | Max messages per user per hour |
| `MINUTE_MESSAGE_LIMIT` | `5` | Max messages per user per minute |
| `LOG_LEVEL` | `INFO` | Logging level |
| `WEB_ADMIN_PORT` | `8080` | Health check HTTP port |

---

## Database Backup

```bash
# Backup PostgreSQL
./scripts/backup.sh

# Backups saved to /opt/smsbot/backups/ (keeps last 30)
```

---

## Restart / Update

```bash
# Restart all services
docker compose restart

# Update to latest code
git pull
docker compose build
docker compose up -d

# Rollback: check out previous tag
git checkout v1.0.0
docker compose build
docker compose up -d
```

---

## Testing

```bash
pip install pytest pytest-asyncio
pytest
```

---

## Limitations

- SMS delivery through SMTP-to-SMS gateways is **not guaranteed**. Carriers may filter, delay, or block messages without notice.
- Carriers can change or discontinue their gateway addresses at any time. Update `app/carriers.py` as needed.
- This platform is designed exclusively for **consent-based** notifications. Do not use it for unsolicited bulk messaging.
- The messaging layer is designed so SMTP-to-SMS can be replaced with Twilio, Telnyx, Sinch, or another SMS provider by modifying `app/services/smtp_service.py` and the worker without rewriting the Telegram bot.

---

## License

MIT

