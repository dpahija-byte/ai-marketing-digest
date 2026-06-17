from __future__ import annotations

import logging
import os
import smtplib
from datetime import date, datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import requests

from .models import AppConfig, PublicArticle

LOGGER = logging.getLogger(__name__)


def write_public_article(
    article: PublicArticle,
    config: AppConfig,
    run_date: date | None = None,
    stats: dict[str, int] | None = None,
) -> Path:
    run_date = run_date or datetime.now(timezone.utc).date()
    config.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = config.output_dir / f"{run_date.isoformat()}.md"
    stats = stats or {}

    lines = [
        f"# {article.title}",
        "",
        article.subtitle,
        "",
    ]

    if article.image_path:
        image_ref = _relative_path(article.image_path, config.output_dir)
        lines.extend([f"![{article.title}]({image_ref})", ""])

    lines.extend(
        [
            article.body_markdown.strip(),
            "",
            "---",
            "",
        ]
    )

    if article.sources_markdown.strip():
        lines.extend(
            [
                "## Sources Consulted",
                "",
                article.sources_markdown.strip(),
                "",
                "---",
                "",
            ]
        )

    lines.extend(
        [
            "## Research Basis",
            "",
            f"- Sources scanned: {stats.get('sources', article.source_count)}",
            f"- Recent items reviewed: {stats.get('new', article.article_count)}",
            "- The article above is original analysis. Sources are used as research input and credited only after the article.",
            "",
        ]
    )

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def deliver_output(path: Path, config: AppConfig) -> None:
    body = path.read_text(encoding="utf-8")
    if config.email_enabled:
        send_email(path.name, body)
    if config.telegram_enabled:
        send_telegram(body)


def send_email(subject: str, body: str) -> None:
    required = ["SMTP_HOST", "SMTP_FROM", "SMTP_TO"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"Email delivery enabled but missing env vars: {', '.join(missing)}")

    host = os.environ["SMTP_HOST"].strip()
    port = int(os.getenv("SMTP_PORT") or "587")
    username = (os.getenv("SMTP_USERNAME") or "").strip() or None
    password = (os.getenv("SMTP_PASSWORD") or "").strip() or None
    sender = _single_email(os.environ["SMTP_FROM"], "SMTP_FROM")
    recipient = _single_email(os.environ["SMTP_TO"], "SMTP_TO")
    allowed_to = os.getenv("EMAIL_ALLOWED_TO")
    if allowed_to and recipient.lower() != _single_email(allowed_to, "EMAIL_ALLOWED_TO").lower():
        raise RuntimeError("SMTP_TO does not match EMAIL_ALLOWED_TO; refusing to send")
    use_tls = os.getenv("SMTP_TLS", "true").lower() in {"1", "true", "yes", "on"}

    message = EmailMessage()
    message["Subject"] = f"AI Marketing Digest: {subject}"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)

    with smtplib.SMTP(host, port, timeout=30) as smtp:
        if use_tls:
            smtp.starttls()
        if username and password:
            smtp.login(username, password)
        smtp.send_message(message)
    LOGGER.info("Email delivery completed")


def send_telegram(body: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("Telegram delivery enabled but TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for chunk in _chunks(body, 3500):
        response = requests.post(
            url,
            json={"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True},
            timeout=30,
        )
        response.raise_for_status()
    LOGGER.info("Telegram delivery completed")


def _chunks(text: str, size: int) -> list[str]:
    return [text[index : index + size] for index in range(0, len(text), size)]


def _relative_path(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def _single_email(value: str, env_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise RuntimeError(f"{env_name} cannot be empty")
    if any(separator in cleaned for separator in [",", ";", "\n", "\r"]):
        raise RuntimeError(f"{env_name} must contain exactly one email address")
    if "@" not in cleaned:
        raise RuntimeError(f"{env_name} does not look like an email address")
    return cleaned
