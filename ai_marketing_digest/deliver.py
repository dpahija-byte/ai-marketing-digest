from __future__ import annotations

import logging
import os
import smtplib
from datetime import date, datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import requests

from .models import AppConfig, DraftPost
from .relevance import ScoredArticle

LOGGER = logging.getLogger(__name__)


def write_digest(
    posts: list[DraftPost],
    config: AppConfig,
    run_date: date | None = None,
    stats: dict[str, int] | None = None,
) -> Path:
    run_date = run_date or datetime.now(timezone.utc).date()
    config.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = config.output_dir / f"{run_date.isoformat()}.md"
    stats = stats or {}

    lines = [
        f"# AI Marketing Digest - {run_date.isoformat()}",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Sources analyzed: {stats.get('sources', 0)}",
        f"Articles found: {stats.get('fetched', 0)}",
        f"New articles: {stats.get('new', 0)}",
        f"Selected articles: {len(posts)}",
        "",
    ]

    if not posts:
        lines.extend(
            [
                "Nessun nuovo articolo rilevante trovato nella finestra configurata.",
                "",
            ]
        )
    for index, post in enumerate(posts, start=1):
        article = post.article
        lines.extend(
            [
                f"## {index}. {article.title}",
                "",
                f"- Source: {article.source}",
                f"- URL: {article.url}",
                f"- Author: {article.author or 'not specified'}",
                f"- Date: {article.published_at.isoformat() if article.published_at else 'not available'}",
                "",
                post.content.strip(),
                "",
                "---",
                "",
            ]
        )

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def write_newsletter(
    scored_articles: list[ScoredArticle],
    draft_posts: list[DraftPost],
    config: AppConfig,
    run_date: date | None = None,
    stats: dict[str, int] | None = None,
) -> Path:
    run_date = run_date or datetime.now(timezone.utc).date()
    config.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = config.output_dir / f"{run_date.isoformat()}.md"
    stats = stats or {}

    lines = [
        f"# AI Marketing Digest - {run_date.isoformat()}",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Sources analyzed: {stats.get('sources', 0)}",
        f"Articles found: {stats.get('fetched', 0)}",
        f"New articles considered: {stats.get('new', 0)}",
        f"Articles in newsletter: {len(scored_articles)}",
        f"LinkedIn draft posts: {len(draft_posts)}",
        "",
        "## Source Intelligence",
        "",
    ]

    if not scored_articles:
        lines.extend(
            [
                "No new articles found in the configured time window.",
                "",
            ]
        )
    else:
        lines.append(
            "Editorial note: articles are not treated as scripts. They are inputs for analysis, "
            "claim discipline, and original LinkedIn angles."
        )
        lines.append("")

    for index, item in enumerate(scored_articles, start=1):
        article = item.article
        excerpt = article.excerpt or article.text[:420]
        ai_hits = ", ".join(item.ai_hits) if item.ai_hits else "none explicit"
        marketing_hits = ", ".join(item.marketing_hits) if item.marketing_hits else "none explicit"
        lines.extend(
            [
                f"### {index}. {article.title}",
                "",
                f"- Source: {article.source}",
                f"- URL: {article.url}",
                f"- Author: {article.author or 'not specified'}",
                f"- Date: {article.published_at.isoformat() if article.published_at else 'not available'}",
                f"- Automatic priority: {item.score}",
                f"- AI signals: {ai_hits}",
                f"- Marketing signals: {marketing_hits}",
                "",
                excerpt.strip(),
                "",
            ]
        )

    lines.extend(["## LinkedIn draft posts", ""])
    if draft_posts:
        for index, draft in enumerate(draft_posts, start=1):
            article = draft.article
            lines.extend(
                [
                    f"### Post {index}: {article.title}",
                    "",
                    f"- Anchor source: {article.source}",
                    f"- Anchor URL: {article.url}",
                    f"- Anchor author: {article.author or 'not specified'}",
                    "",
                    draft.content.strip(),
                    "",
                    "---",
                    "",
                ]
            )
    else:
        lines.extend(
            [
                "No LinkedIn drafts generated because no articles were available.",
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


def _single_email(value: str, env_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise RuntimeError(f"{env_name} cannot be empty")
    if any(separator in cleaned for separator in [",", ";", "\n", "\r"]):
        raise RuntimeError(f"{env_name} must contain exactly one email address")
    if "@" not in cleaned:
        raise RuntimeError(f"{env_name} does not look like an email address")
    return cleaned
