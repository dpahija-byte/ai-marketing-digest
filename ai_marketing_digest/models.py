from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SourceConfig:
    name: str
    blog_url: str
    feed_url: str | None = None
    enabled: bool = True
    article_selector: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class AppConfig:
    window_hours: int
    max_articles: int
    max_newsletter_articles: int
    sources_file: Path
    voice_file: Path
    output_dir: Path
    db_path: Path
    user_agent: str
    request_timeout: int
    max_links_per_source: int
    include_undated: bool
    min_article_chars: int
    log_level: str
    llm_provider: str
    openai_model: str
    anthropic_model: str
    llm_temperature: float
    use_llm_ranking: bool
    max_post_chars: int
    image_enabled: bool
    image_model: str
    image_size: str
    image_quality: str
    email_enabled: bool
    telegram_enabled: bool
    editorial_voice: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class Article:
    source: str
    title: str
    url: str
    published_at: datetime | None
    author: str | None
    excerpt: str
    text: str


@dataclass(frozen=True)
class DraftPost:
    article: Article
    content: str


@dataclass(frozen=True)
class PublicArticle:
    title: str
    subtitle: str
    body_markdown: str
    image_prompt: str
    source_count: int
    article_count: int
    image_path: Path | None = None
