from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .models import AppConfig, SourceConfig


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value not in (None, "") else default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value not in (None, "") else default


def _format_editorial_voice(path: Path) -> str:
    data = _read_yaml(path)
    if not data:
        return ""

    sections: list[str] = []
    for key, value in data.items():
        title = str(key).replace("_", " ").title()
        if isinstance(value, list):
            body = "\n".join(f"- {item}" for item in value)
        elif isinstance(value, dict):
            body = "\n".join(f"- {sub_key}: {sub_value}" for sub_key, sub_value in value.items())
        else:
            body = str(value)
        sections.append(f"{title}:\n{body}")
    return "\n\n".join(sections)


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    config_path = Path(path)
    load_dotenv(dotenv_path=config_path.parent / ".env")

    data = _read_yaml(config_path)
    fetch = data.get("fetch", {}) or {}
    paths = data.get("paths", {}) or {}
    llm = data.get("llm", {}) or {}
    image = data.get("image", {}) or {}
    delivery = data.get("delivery", {}) or {}
    email = delivery.get("email", {}) or {}
    telegram = delivery.get("telegram", {}) or {}

    sources_file = Path(os.getenv("SOURCES_FILE", paths.get("sources_file", "sources.yaml")))
    voice_file = Path(os.getenv("VOICE_FILE", paths.get("voice_file", "voice.yaml")))
    output_dir = Path(os.getenv("OUTPUT_DIR", paths.get("output_dir", "output")))
    db_path = Path(os.getenv("DB_PATH", paths.get("db_path", "data/digest.sqlite3")))
    static_image_value = os.getenv("IMAGE_STATIC_PATH", str(image.get("static_path", "") or "")).strip()
    image_static_path = Path(static_image_value) if static_image_value else None

    return AppConfig(
        window_hours=_env_int("WINDOW_HOURS", int(fetch.get("window_hours", 48))),
        max_articles=_env_int("MAX_ARTICLES", int(fetch.get("max_articles", 5))),
        max_newsletter_articles=_env_int(
            "MAX_NEWSLETTER_ARTICLES", int(fetch.get("max_newsletter_articles", 20))
        ),
        sources_file=sources_file,
        voice_file=voice_file,
        output_dir=output_dir,
        db_path=db_path,
        user_agent=os.getenv(
            "USER_AGENT",
            str(fetch.get("user_agent", "ai-marketing-digest/0.1 (+https://example.com/bot)")),
        ),
        request_timeout=_env_int("REQUEST_TIMEOUT", int(fetch.get("request_timeout", 20))),
        max_links_per_source=_env_int(
            "MAX_LINKS_PER_SOURCE", int(fetch.get("max_links_per_source", 20))
        ),
        include_undated=_env_bool("INCLUDE_UNDATED", bool(fetch.get("include_undated", False))),
        min_article_chars=_env_int("MIN_ARTICLE_CHARS", int(fetch.get("min_article_chars", 400))),
        log_level=os.getenv("LOG_LEVEL", str(data.get("log_level", "INFO"))),
        llm_provider=os.getenv("LLM_PROVIDER", str(llm.get("provider", "auto"))).lower(),
        openai_model=os.getenv("OPENAI_MODEL", str(llm.get("openai_model", "gpt-4o-mini"))),
        anthropic_model=os.getenv(
            "ANTHROPIC_MODEL", str(llm.get("anthropic_model", "claude-3-5-haiku-latest"))
        ),
        llm_temperature=_env_float("LLM_TEMPERATURE", float(llm.get("temperature", 0.4))),
        use_llm_ranking=_env_bool("USE_LLM_RANKING", bool(llm.get("use_ranking", False))),
        max_post_chars=_env_int("MAX_POST_CHARS", int(llm.get("max_post_chars", 1300))),
        image_enabled=_env_bool("IMAGE_ENABLED", bool(image.get("enabled", True))),
        image_model=os.getenv("IMAGE_MODEL", str(image.get("model", "gpt-image-1"))),
        image_size=os.getenv("IMAGE_SIZE", str(image.get("size", "1536x1024"))),
        image_quality=os.getenv("IMAGE_QUALITY", str(image.get("quality", "medium"))),
        image_static_path=image_static_path,
        email_enabled=_env_bool("EMAIL_ENABLED", bool(email.get("enabled", False))),
        telegram_enabled=_env_bool("TELEGRAM_ENABLED", bool(telegram.get("enabled", False))),
        editorial_voice=_format_editorial_voice(voice_file),
        raw=data,
    )


def load_sources(path: str | Path) -> list[SourceConfig]:
    sources_path = Path(path)
    data = _read_yaml(sources_path)
    rows = data.get("sources", [])
    if not isinstance(rows, list):
        raise ValueError(f"{sources_path} must contain a 'sources' list")

    sources: list[SourceConfig] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each source entry must be a YAML mapping")
        source = SourceConfig(
            name=str(row["name"]),
            blog_url=str(row["blog_url"]),
            feed_url=row.get("feed_url") or None,
            enabled=bool(row.get("enabled", True)),
            article_selector=row.get("article_selector") or None,
            notes=row.get("notes") or None,
        )
        if source.enabled:
            sources.append(source)
    return sources
