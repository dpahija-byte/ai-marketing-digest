from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from calendar import timegm
from typing import Any
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from .models import AppConfig, Article, SourceConfig
from .sources import RobotsGuard, discover_feed_url, normalize_url, same_site

LOGGER = logging.getLogger(__name__)


class Fetcher:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": config.user_agent})
        self.robots = RobotsGuard(self.session, config.user_agent, config.request_timeout)

    def fetch_all(self, sources: list[SourceConfig]) -> list[Article]:
        articles: list[Article] = []
        for source in sources:
            try:
                source_articles = self.fetch_source(source)
                LOGGER.info("[%s] fetched %d recent articles", source.name, len(source_articles))
                articles.extend(source_articles)
            except Exception:
                LOGGER.exception("[%s] source failed; continuing with remaining sources", source.name)
        return articles

    def fetch_source(self, source: SourceConfig) -> list[Article]:
        feed_url = discover_feed_url(
            source,
            self.session,
            self.robots,
            self.config.user_agent,
            self.config.request_timeout,
        )
        if feed_url:
            return self._fetch_from_feed(source, feed_url)
        return self._scrape_blog(source)

    def _fetch_from_feed(self, source: SourceConfig, feed_url: str) -> list[Article]:
        if not self.robots.can_fetch(feed_url):
            LOGGER.warning("[%s] Feed blocked by robots.txt: %s", source.name, feed_url)
            return []
        try:
            response = self.session.get(feed_url, timeout=self.config.request_timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            LOGGER.warning("[%s] Feed fetch failed: %s (%s)", source.name, feed_url, exc)
            LOGGER.debug("[%s] feed fetch error details", source.name, exc_info=True)
            return []

        parsed = feedparser.parse(response.content)
        articles: list[Article] = []
        for entry in parsed.entries:
            article = self._article_from_feed_entry(source, entry)
            if not article:
                continue
            if not self._within_window(article.published_at):
                continue
            if len(article.text) < self.config.min_article_chars:
                title, full_text, excerpt, author, published_at = self._fetch_article_details(article.url)
                article = Article(
                    source=article.source,
                    title=title or article.title,
                    url=article.url,
                    published_at=article.published_at or published_at,
                    author=article.author or author,
                    excerpt=article.excerpt or excerpt,
                    text=full_text or article.text,
                )
            articles.append(article)
        return articles

    def _article_from_feed_entry(self, source: SourceConfig, entry: Any) -> Article | None:
        url = getattr(entry, "link", None)
        title = _clean_text(getattr(entry, "title", ""))
        if not url or not title:
            return None

        published_at = _entry_datetime(entry)
        author = _clean_text(getattr(entry, "author", "")) or None
        excerpt = _html_to_text(getattr(entry, "summary", "") or getattr(entry, "description", ""))
        content_chunks: list[str] = []
        for content in getattr(entry, "content", []) or []:
            value = content.get("value") if isinstance(content, dict) else getattr(content, "value", "")
            if value:
                content_chunks.append(_html_to_text(value))
        text = "\n\n".join(chunk for chunk in content_chunks if chunk).strip() or excerpt
        return Article(
            source=source.name,
            title=title,
            url=normalize_url(url),
            published_at=published_at,
            author=author,
            excerpt=excerpt,
            text=text,
        )

    def _scrape_blog(self, source: SourceConfig) -> list[Article]:
        if not self.robots.can_fetch(source.blog_url):
            LOGGER.warning("[%s] Blog page blocked by robots.txt: %s", source.name, source.blog_url)
            return []
        try:
            response = self.session.get(source.blog_url, timeout=self.config.request_timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            LOGGER.warning("[%s] Blog scrape failed: %s (%s)", source.name, source.blog_url, exc)
            LOGGER.debug("[%s] blog scrape error details", source.name, exc_info=True)
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        urls = self._extract_article_urls(source, soup)
        articles: list[Article] = []
        for url in urls[: self.config.max_links_per_source]:
            title, text, excerpt, author, published_at = self._fetch_article_details(url)
            if not title or not text:
                continue
            if not self._within_window(published_at):
                continue
            articles.append(
                Article(
                    source=source.name,
                    title=title,
                    url=normalize_url(url),
                    published_at=published_at,
                    author=author,
                    excerpt=excerpt,
                    text=text,
                )
            )
        return articles

    def _extract_article_urls(self, source: SourceConfig, soup: BeautifulSoup) -> list[str]:
        selectors = [source.article_selector] if source.article_selector else []
        selectors.extend(["article a[href]", "h1 a[href]", "h2 a[href]", "h3 a[href]", "a[href]"])
        urls: list[str] = []
        seen: set[str] = set()
        for selector in selectors:
            if not selector:
                continue
            for link in soup.select(selector):
                href = link.get("href")
                if not href:
                    continue
                absolute = normalize_url(urljoin(source.blog_url, href))
                if absolute in seen or not same_site(absolute, source.blog_url):
                    continue
                if _looks_like_article_url(absolute):
                    seen.add(absolute)
                    urls.append(absolute)
        return urls

    def _fetch_article_details(
        self, url: str
    ) -> tuple[str | None, str | None, str, str | None, datetime | None]:
        if not self.robots.can_fetch(url):
            LOGGER.info("Article blocked by robots.txt: %s", url)
            return None, None, "", None, None
        try:
            response = self.session.get(url, timeout=self.config.request_timeout)
            response.raise_for_status()
        except requests.RequestException:
            LOGGER.debug("Article fetch failed: %s", url, exc_info=True)
            return None, None, "", None, None

        soup = BeautifulSoup(response.text, "html.parser")
        title = _meta_content(soup, "property", "og:title") or _page_title(soup)
        excerpt = (
            _meta_content(soup, "name", "description")
            or _meta_content(soup, "property", "og:description")
            or ""
        )
        author = _extract_author(soup)
        published_at = _extract_published_at(soup)
        text = _extract_article_text(soup)
        return title, text, excerpt, author, published_at

    def _within_window(self, published_at: datetime | None) -> bool:
        if published_at is None:
            return self.config.include_undated
        now = datetime.now(timezone.utc)
        since = now - timedelta(hours=self.config.window_hours)
        return since <= published_at <= now + timedelta(hours=3)


def _entry_datetime(entry: Any) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        value = getattr(entry, attr, None)
        if value:
            return datetime.fromtimestamp(timegm(value), timezone.utc)
    for attr in ("published", "updated", "created"):
        value = getattr(entry, attr, None)
        parsed = _parse_datetime(value)
        if parsed:
            return parsed
    return None


def _extract_published_at(soup: BeautifulSoup) -> datetime | None:
    candidates = [
        _meta_content(soup, "property", "article:published_time"),
        _meta_content(soup, "property", "og:published_time"),
        _meta_content(soup, "name", "publish-date"),
        _meta_content(soup, "name", "date"),
        _meta_content(soup, "itemprop", "datePublished"),
    ]
    for time_tag in soup.find_all("time"):
        candidates.append(time_tag.get("datetime"))
        candidates.append(time_tag.get_text(" ", strip=True))
    for candidate in candidates:
        parsed = _parse_datetime(candidate)
        if parsed:
            return parsed
    return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        try:
            parsed = date_parser.parse(value, fuzzy=True)
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_author(soup: BeautifulSoup) -> str | None:
    candidates = [
        _meta_content(soup, "name", "author"),
        _meta_content(soup, "property", "article:author"),
        _meta_content(soup, "itemprop", "author"),
    ]
    for selector in (".author", ".byline", "[rel=author]", "[class*=author]", "[class*=byline]"):
        node = soup.select_one(selector)
        if node:
            candidates.append(node.get_text(" ", strip=True))
    for candidate in candidates:
        cleaned = _clean_text(candidate or "")
        if cleaned:
            return cleaned
    return None


def _extract_article_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    container = soup.find("article") or soup.find("main") or soup.body or soup
    paragraphs: list[str] = []
    for node in container.find_all(["p", "li"]):
        text = _clean_text(node.get_text(" ", strip=True))
        if len(text) >= 40:
            paragraphs.append(text)
    return "\n\n".join(paragraphs)


def _page_title(soup: BeautifulSoup) -> str | None:
    h1 = soup.find("h1")
    if h1:
        title = _clean_text(h1.get_text(" ", strip=True))
        if title:
            return title
    if soup.title and soup.title.string:
        return _clean_text(soup.title.string)
    return None


def _meta_content(soup: BeautifulSoup, attr: str, value: str) -> str | None:
    node = soup.find("meta", attrs={attr: value})
    if not node:
        return None
    content = node.get("content")
    return _clean_text(content) if content else None


def _html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    return _clean_text(soup.get_text(" ", strip=True))


def _clean_text(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _looks_like_article_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    blocked_fragments = (
        "/tag/",
        "/category/",
        "/author/",
        "/page/",
        "/search",
        "/newsletter",
        "/contact",
        "/about",
        "/privacy",
        "/terms",
    )
    if any(fragment in path for fragment in blocked_fragments):
        return False
    return bool(re.search(r"/\d{4}/|/[a-z0-9][a-z0-9-]{12,}/?$", path))
