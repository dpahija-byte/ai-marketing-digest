from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Article
from .sources import normalize_url


class DedupStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "DedupStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.close()

    def is_processed(self, url: str) -> bool:
        normalized = normalize_url(url)
        row = self.conn.execute(
            "select status from processed_articles where url = ?",
            (normalized,),
        ).fetchone()
        if row is None:
            return False
        return row["status"] in {"generated", "newslettered", "filtered"}

    def record(
        self,
        article: Article,
        status: str,
        reason: str | None = None,
        draft_path: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        published_at = article.published_at.isoformat() if article.published_at else None
        self.conn.execute(
            """
            insert into processed_articles (
                url, source, title, author, published_at, status, reason,
                draft_path, first_seen_at, last_seen_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(url) do update set
                source = excluded.source,
                title = excluded.title,
                author = excluded.author,
                published_at = excluded.published_at,
                status = excluded.status,
                reason = excluded.reason,
                draft_path = excluded.draft_path,
                last_seen_at = excluded.last_seen_at
            """,
            (
                normalize_url(article.url),
                article.source,
                article.title,
                article.author,
                published_at,
                status,
                reason,
                draft_path,
                now,
                now,
            ),
        )
        self.conn.commit()

    def _init_db(self) -> None:
        self.conn.execute(
            """
            create table if not exists processed_articles (
                url text primary key,
                source text not null,
                title text not null,
                author text,
                published_at text,
                status text not null,
                reason text,
                draft_path text,
                first_seen_at text not null,
                last_seen_at text not null
            )
            """
        )
        self.conn.execute(
            "create index if not exists idx_processed_articles_status on processed_articles(status)"
        )
        self.conn.commit()
