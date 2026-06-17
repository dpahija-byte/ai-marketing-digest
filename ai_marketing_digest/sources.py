from __future__ import annotations

import logging
import urllib.robotparser
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import feedparser
import requests
from bs4 import BeautifulSoup

from .models import SourceConfig

LOGGER = logging.getLogger(__name__)

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "ref",
    "ref_src",
}


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key in TRACKING_QUERY_KEYS or any(key.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES):
            continue
        query_items.append((key, value))
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            "",
            urlencode(query_items),
            "",
        )
    )


def same_site(url: str, base_url: str) -> bool:
    return urlparse(url).netloc.lower().removeprefix("www.") == urlparse(
        base_url
    ).netloc.lower().removeprefix("www.")


@dataclass
class RobotsGuard:
    session: requests.Session
    user_agent: str
    timeout: int

    def __post_init__(self) -> None:
        self._cache: dict[str, urllib.robotparser.RobotFileParser] = {}

    def can_fetch(self, url: str) -> bool:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False
        origin = f"{parsed.scheme}://{parsed.netloc}"
        parser = self._cache.get(origin)
        if parser is None:
            parser = self._load_parser(origin)
            self._cache[origin] = parser
        try:
            return parser.can_fetch(self.user_agent, url)
        except Exception:
            LOGGER.warning("robots.txt check failed for %s; skipping", url, exc_info=True)
            return False

    def _load_parser(self, origin: str) -> urllib.robotparser.RobotFileParser:
        robots_url = urljoin(origin, "/robots.txt")
        parser = urllib.robotparser.RobotFileParser(robots_url)
        try:
            response = self.session.get(
                robots_url,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
            )
            if response.status_code >= 400:
                parser.parse([])
            else:
                parser.parse(response.text.splitlines())
        except requests.RequestException:
            LOGGER.info("Could not read robots.txt at %s; allowing by default", robots_url)
            parser.parse([])
        return parser


def discover_feed_url(
    source: SourceConfig,
    session: requests.Session,
    robots: RobotsGuard,
    user_agent: str,
    timeout: int,
) -> str | None:
    candidates: list[str] = []
    if source.feed_url:
        candidates.append(source.feed_url)

    html = _fetch_blog_html(source, session, robots, user_agent, timeout)
    if html:
        candidates.extend(_extract_feed_links(html, source.blog_url))

    candidates.extend(_common_feed_candidates(source.blog_url))

    for candidate in _unique(candidates):
        if not robots.can_fetch(candidate):
            LOGGER.info("[%s] Feed blocked by robots.txt: %s", source.name, candidate)
            continue
        if _is_valid_feed(candidate, session, user_agent, timeout):
            LOGGER.info("[%s] Using feed: %s", source.name, candidate)
            return candidate

    LOGGER.info("[%s] No valid RSS/Atom feed discovered", source.name)
    return None


def _fetch_blog_html(
    source: SourceConfig,
    session: requests.Session,
    robots: RobotsGuard,
    user_agent: str,
    timeout: int,
) -> str | None:
    if not robots.can_fetch(source.blog_url):
        LOGGER.warning("[%s] Blog page blocked by robots.txt: %s", source.name, source.blog_url)
        return None
    try:
        response = session.get(
            source.blog_url,
            headers={"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml"},
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        LOGGER.warning("[%s] Could not fetch blog page for feed discovery: %s", source.name, exc)
        LOGGER.debug("[%s] feed discovery error details", source.name, exc_info=True)
        return None
    return response.text


def _extract_feed_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for link in soup.find_all("link"):
        rel = " ".join(link.get("rel", [])).lower()
        mime = str(link.get("type", "")).lower()
        href = link.get("href")
        if not href:
            continue
        if "alternate" in rel and (
            "rss" in mime or "atom" in mime or "feed" in mime or "json" in mime
        ):
            urls.append(urljoin(base_url, href))
    return urls


def _common_feed_candidates(blog_url: str) -> list[str]:
    parsed = urlparse(blog_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    blog_path = parsed.path or "/"
    if not blog_path.endswith("/"):
        blog_path = f"{blog_path}/"
    blog_base = urljoin(origin, blog_path)
    return [
        urljoin(blog_base, "feed/"),
        urljoin(blog_base, "rss/"),
        urljoin(blog_base, "atom/"),
        urljoin(origin, "/feed/"),
        urljoin(origin, "/rss/"),
        urljoin(origin, "/rss.xml"),
        urljoin(origin, "/feed.xml"),
        urljoin(origin, "/atom.xml"),
    ]


def _is_valid_feed(url: str, session: requests.Session, user_agent: str, timeout: int) -> bool:
    try:
        response = session.get(
            url,
            headers={"User-Agent": user_agent, "Accept": "application/rss+xml,application/atom+xml,text/xml,*/*"},
            timeout=timeout,
        )
        if response.status_code >= 400:
            return False
    except requests.RequestException:
        return False

    parsed = feedparser.parse(response.content)
    if parsed.bozo and not parsed.entries:
        return False
    return bool(parsed.entries or parsed.feed)


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = normalize_url(value)
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(value)
    return result
