from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from .models import Article, PublicArticle
from .sources import normalize_url


@dataclass(frozen=True)
class QualityResult:
    passed: bool
    reasons: tuple[str, ...]


def validate_public_article(article: PublicArticle, source_articles: list[Article]) -> QualityResult:
    reasons: list[str] = []
    known_urls = {normalize_url(item.url) for item in source_articles if item.url}
    source_urls = _extract_urls(article.sources_markdown)

    if not source_articles:
        reasons.append("No source articles were retrieved in this run.")
    if not source_urls:
        reasons.append("Sources Consulted contains no source links.")

    unknown_urls = sorted(url for url in source_urls if normalize_url(url) not in known_urls)
    if unknown_urls:
        reasons.append("Sources Consulted includes links that were not retrieved in this run: " + ", ".join(unknown_urls[:5]))

    invalid_urls = sorted(url for url in source_urls if not _valid_http_url(url))
    if invalid_urls:
        reasons.append("Sources Consulted includes invalid source URLs: " + ", ".join(invalid_urls[:5]))

    combined_text = "\n".join([article.title, article.subtitle, article.body_markdown])
    if re.search(r"https?://", article.body_markdown):
        reasons.append("The article body contains raw URLs; source links must stay in Sources Consulted.")
    if "—" in combined_text or "–" in combined_text:
        reasons.append("The article contains long dashes; use plain punctuation instead.")
    if _starts_with_generic_opener(article.body_markdown):
        reasons.append("The article opens with a generic banned phrase.")

    long_quotes = _long_quotes(article.body_markdown)
    if long_quotes:
        reasons.append("The article contains a quote longer than 15 words.")
    if len(_all_quotes(article.body_markdown)) > max(1, len(source_urls)):
        reasons.append("The article contains more quoted passages than credited sources.")

    return QualityResult(passed=not reasons, reasons=tuple(reasons))


def _extract_urls(markdown: str) -> set[str]:
    urls = set(re.findall(r"\[[^\]]+\]\((https?://[^)\s]+)\)", markdown))
    urls.update(re.findall(r"(?<!\()https?://[^\s<>)]+", markdown))
    return urls


def _valid_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _starts_with_generic_opener(body: str) -> bool:
    first_line = body.strip().splitlines()[0].strip().lower() if body.strip() else ""
    banned = (
        "in today's world",
        "in today’s world",
        "in today's fast-paced",
        "in today’s fast-paced",
        "in the fast-paced world",
        "in an era where",
        "in the age of ai",
        "ai is changing everything",
    )
    return any(first_line.startswith(item) for item in banned)


def _long_quotes(text: str) -> list[str]:
    return [quote for quote in _all_quotes(text) if len(re.findall(r"\b\w+\b", quote)) > 15]


def _all_quotes(text: str) -> list[str]:
    straight = re.findall(r'"([^"]+)"', text)
    curly = re.findall(r"“([^”]+)”", text)
    return straight + curly
