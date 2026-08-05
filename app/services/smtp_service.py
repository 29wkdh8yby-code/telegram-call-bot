"""SMTP sending service with connection test and email dispatch."""
from __future__ import annotations

from dataclasses import dataclass
from email.mime.text import MIMEText

import aiosmtplib

from app.encryption import decrypt
from app.models import SmtpAccount, SmtpEncryption


@dataclass
class SmtpConfig:
    host: str
    port: int
    username: str
    smtp_password: str
    encryption: SmtpEncryption
    sender_name: str | None = None


def smtp_config_from_account(account: SmtpAccount) -> SmtpConfig:
    return SmtpConfig(
        host=account.host,
        port=account.port,
        username=account.username,
        smtp_password=decrypt(account.encrypted_password),
        encryption=account.encryption,
        sender_name=account.sender_name,
    )


async def test_smtp_connection(config: SmtpConfig) -> tuple[bool, str]:
    """
    Test SMTP connectivity.
    Returns (success, message).
    """
    try:
        smtp = aiosmtplib.SMTP(
            hostname=config.host,
            port=config.port,
            use_tls=(config.encryption == SmtpEncryption.SSL),
        )
        await smtp.connect()
        if config.encryption == SmtpEncryption.TLS:
            await smtp.starttls()
        await smtp.login(config.username, config.smtp_password)
        await smtp.quit()
        return True, "Connection successful."
    except aiosmtplib.SMTPAuthenticationError:
        return False, "Authentication failed. Check your username and password."
    except aiosmtplib.SMTPConnectError as exc:
        return False, f"Could not connect to {config.host}:{config.port} — {exc}"
    except Exception as exc:  # noqa: BLE001
        return False, f"SMTP error: {exc}"


async def send_sms_via_smtp(
    config: SmtpConfig,
    to_address: str,
    subject: str,
    body: str,
) -> tuple[bool, str]:
    """
    Send a single email to a carrier gateway address.
    Returns (success, error_message_or_empty).
    """
    from_name = config.sender_name or config.username
    from_addr = config.username

    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = f"{from_name} <{from_addr}>"
    msg["To"] = to_address
    msg["Subject"] = subject

    try:
        smtp = aiosmtplib.SMTP(
            hostname=config.host,
            port=config.port,
            use_tls=(config.encryption == SmtpEncryption.SSL),
        )
        await smtp.connect()
        if config.encryption == SmtpEncryption.TLS:
            await smtp.starttls()
        await smtp.login(config.username, config.smtp_password)
        await smtp.sendmail(from_addr, [to_address], msg.as_string())
        await smtp.quit()
        return True, ""
    except aiosmtplib.SMTPRecipientsRefused:
        return False, f"Recipient refused: {to_address}"
    except aiosmtplib.SMTPAuthenticationError:
        return False, "SMTP authentication failed."
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
