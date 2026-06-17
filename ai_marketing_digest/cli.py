from __future__ import annotations

import argparse
import logging
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from .config import load_config, load_sources
from .dedup import DedupStore
from .deliver import deliver_output, write_newsletter
from .fetch import Fetcher
from .generate import LLMClient, TemplateClient, create_llm_client
from .models import AppConfig, Article, DraftPost
from .relevance import score_articles
from .site import build_site


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        config = load_config(args.config)
        if args.sources:
            config = _replace_sources_file(config, args.sources)
        if args.window_hours:
            config = _replace_window_hours(config, args.window_hours)
        if args.max_articles:
            config = _replace_max_articles(config, args.max_articles)
        setup_logging(config.log_level)
        run(
            config,
            dry_run=args.dry_run,
            no_delivery=args.no_delivery,
            include_seen=args.include_seen,
        )
        if args.build_site:
            build_site(config.output_dir, args.site_dir)
        return 0

    if args.command == "site":
        config = load_config(args.config)
        build_site(config.output_dir, args.site_dir)
        return 0

    parser.print_help()
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-marketing-digest")
    subparsers = parser.add_subparsers(dest="command")
    run_parser = subparsers.add_parser("run", help="Fetch articles and generate LinkedIn draft posts")
    run_parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    run_parser.add_argument("--sources", help="Path to sources.yaml")
    run_parser.add_argument("--window-hours", type=int, help="Override fetch window")
    run_parser.add_argument("--max-articles", type=int, help="Override max selected articles")
    run_parser.add_argument("--dry-run", action="store_true", help="Use deterministic local generation")
    run_parser.add_argument("--no-delivery", action="store_true", help="Skip email/Telegram delivery")
    run_parser.add_argument("--build-site", action="store_true", help="Build the public static site after running")
    run_parser.add_argument("--site-dir", type=Path, default=Path("site"), help="Static site output directory")
    run_parser.add_argument(
        "--include-seen",
        action="store_true",
        help="Include articles already present in the SQLite database",
    )
    site_parser = subparsers.add_parser("site", help="Build the public static website from output/*.md")
    site_parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    site_parser.add_argument("--site-dir", type=Path, default=Path("site"), help="Static site output directory")
    return parser


def run(
    config: AppConfig,
    dry_run: bool = False,
    no_delivery: bool = False,
    include_seen: bool = False,
) -> None:
    sources = load_sources(config.sources_file)
    logging.info("Loaded %d enabled sources", len(sources))

    fetcher = Fetcher(config)
    fetched = fetcher.fetch_all(sources)
    fetched = _dedupe_in_memory(fetched)

    with DedupStore(config.db_path) as store:
        new_articles = fetched if include_seen else [
            article for article in fetched if not store.is_processed(article.url)
        ]
        duplicate_count = len(fetched) - len(new_articles)
        logging.info("Fetched=%d, new=%d, already_processed=%d", len(fetched), len(new_articles), duplicate_count)

        scored = score_articles(new_articles)
        newsletter_items = scored[: config.max_newsletter_articles]
        draft_candidates = [item.article for item in scored[: config.max_articles]]

        llm = None
        draft_articles = draft_candidates
        if draft_candidates:
            llm = _create_llm_or_template(config, dry_run=dry_run)
            if config.use_llm_ranking:
                draft_articles = llm.rank_articles(draft_candidates, config.max_articles)

        draft_posts: list[DraftPost] = []
        if draft_articles:
            if llm is None:
                llm = _create_llm_or_template(config, dry_run=dry_run)
            for article in draft_articles[: config.max_articles]:
                try:
                    context = _post_context(article, draft_articles)
                    content = llm.generate_digest_post(context)
                    draft_posts.append(DraftPost(article=article, content=content))
                except Exception:
                    logging.exception("LinkedIn post generation failed for %s", article.url)

        output_path = write_newsletter(
            newsletter_items,
            draft_posts,
            config,
            run_date=datetime.now(timezone.utc).date(),
            stats={
                "sources": len(sources),
                "fetched": len(fetched),
                "new": len(new_articles),
            },
        )

        for item in newsletter_items:
            store.record(item.article, "newslettered", item.reason, str(output_path))

    logging.info("Digest written to %s", output_path)
    if not no_delivery:
        deliver_output(output_path, config)


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def _dedupe_in_memory(articles: list[Article]) -> list[Article]:
    seen: set[str] = set()
    unique: list[Article] = []
    for article in articles:
        if article.url in seen:
            continue
        seen.add(article.url)
        unique.append(article)
    return unique


def _replace_sources_file(config: AppConfig, path: str) -> AppConfig:
    return replace(config, sources_file=Path(path))


def _replace_window_hours(config: AppConfig, value: int) -> AppConfig:
    return replace(config, window_hours=value)


def _replace_max_articles(config: AppConfig, value: int) -> AppConfig:
    return replace(config, max_articles=value)


def _post_context(anchor: Article, articles: list[Article], limit: int = 6) -> list[Article]:
    context = [anchor]
    for article in articles:
        if article.url == anchor.url:
            continue
        context.append(article)
        if len(context) >= limit:
            break
    return context


def _create_llm_or_template(config: AppConfig, dry_run: bool) -> LLMClient:
    try:
        return create_llm_client(config, dry_run=dry_run)
    except RuntimeError as exc:
        logging.warning("%s Falling back to local template generation.", exc)
        return TemplateClient(config)
