from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

from .models import AppConfig, Article

LOGGER = logging.getLogger(__name__)


class LLMClient(ABC):
    @abstractmethod
    def generate_post(self, article: Article) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_digest_post(self, articles: list[Article]) -> str:
        raise NotImplementedError

    def rank_articles(self, articles: list[Article], limit: int) -> list[Article]:
        return articles[:limit]


class OpenAIClient(LLMClient):
    def __init__(self, config: AppConfig) -> None:
        from openai import OpenAI

        self.config = config
        self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    def generate_post(self, article: Article) -> str:
        response = self.client.chat.completions.create(
            model=self.config.openai_model,
            temperature=self.config.llm_temperature,
            max_tokens=1200,
            messages=[
                {"role": "system", "content": _system_prompt(self.config)},
                {"role": "user", "content": _article_prompt(article)},
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("OpenAI returned an empty generation")
        return content.strip()

    def generate_digest_post(self, articles: list[Article]) -> str:
        response = self.client.chat.completions.create(
            model=self.config.openai_model,
            temperature=self.config.llm_temperature,
            max_tokens=1200,
            messages=[
                {"role": "system", "content": _digest_system_prompt(self.config)},
                {"role": "user", "content": _digest_prompt(articles)},
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("OpenAI returned an empty digest generation")
        return content.strip()

    def rank_articles(self, articles: list[Article], limit: int) -> list[Article]:
        response = self.client.chat.completions.create(
            model=self.config.openai_model,
            temperature=0,
            messages=[
                {"role": "system", "content": _ranking_system_prompt(limit)},
                {"role": "user", "content": _ranking_prompt(articles)},
            ],
        )
        content = response.choices[0].message.content or ""
        return _rank_from_json(content, articles, limit)


class AnthropicClient(LLMClient):
    def __init__(self, config: AppConfig) -> None:
        from anthropic import Anthropic

        self.config = config
        self.client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def generate_post(self, article: Article) -> str:
        response = self.client.messages.create(
            model=self.config.anthropic_model,
            max_tokens=1200,
            temperature=self.config.llm_temperature,
            system=_system_prompt(self.config),
            messages=[{"role": "user", "content": _article_prompt(article)}],
        )
        return _anthropic_text(response).strip()

    def generate_digest_post(self, articles: list[Article]) -> str:
        response = self.client.messages.create(
            model=self.config.anthropic_model,
            max_tokens=1200,
            temperature=self.config.llm_temperature,
            system=_digest_system_prompt(self.config),
            messages=[{"role": "user", "content": _digest_prompt(articles)}],
        )
        return _anthropic_text(response).strip()

    def rank_articles(self, articles: list[Article], limit: int) -> list[Article]:
        response = self.client.messages.create(
            model=self.config.anthropic_model,
            max_tokens=400,
            temperature=0,
            system=_ranking_system_prompt(limit),
            messages=[{"role": "user", "content": _ranking_prompt(articles)}],
        )
        return _rank_from_json(_anthropic_text(response), articles, limit)


class TemplateClient(LLMClient):
    """Deterministic fallback for dry runs and CI checks without API keys."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def generate_post(self, article: Article) -> str:
        author = article.author or "redazione"
        excerpt = article.excerpt or article.text[:260]
        body = (
            f"{article.title}\n\n"
            "The useful question is not whether marketers should use AI.\n"
            "That question is already old.\n\n"
            "The sharper question is: which part of the marketing system should AI touch first?\n\n"
            f"This piece points to one signal: {excerpt[:260].strip()}\n\n"
            "My take: the strongest teams will not use AI to make more content. "
            "They will use it to make better decisions before content exists: sharper briefs, "
            "cleaner audience assumptions, faster testing loops, and more honest post-mortems.\n\n"
            "A practical way to start:\n"
            "1. Pick one recurring marketing decision, not one writing task.\n"
            "2. Feed the model the actual inputs your team uses.\n"
            "3. Ask for tradeoffs, risks, and what evidence would change the recommendation.\n"
            "4. Let a human make the final call.\n\n"
            f"Source: {article.url}\n"
            f"Credit: {author}\n\n"
            "#AIMarketing #MarketingStrategy #MarTech #ContentMarketing"
        )
        return body[: self.config.max_post_chars]

    def generate_digest_post(self, articles: list[Article]) -> str:
        titles = [article.title for article in articles[:3]]
        fallback_titles = [
            "AI is moving upstream from content production to marketing judgment",
            "SEO and content teams need stronger decision systems, not just faster drafts",
            "Human review matters most where positioning and evidence are weak",
        ]
        source_line = ", ".join(article.source for article in articles[:5])
        first_url = articles[0].url if articles else ""
        body = (
            "I do not think the next marketing advantage is 'more AI content'.\n\n"
            "The advantage is knowing where AI should challenge the thinking before anything gets published.\n\n"
            "A few signals from today's marketing and AI reading list point in that direction:\n"
            f"- {titles[0] if len(titles) > 0 else fallback_titles[0]}\n"
            f"- {titles[1] if len(titles) > 1 else fallback_titles[1]}\n"
            f"- {titles[2] if len(titles) > 2 else fallback_titles[2]}\n\n"
            "What feels solid: AI is becoming part of the operating layer of marketing, especially in search, "
            "commerce, brand interpretation, and content workflows.\n\n"
            "What I would not overstate yet: that automation alone creates better marketing. It usually creates "
            "more output first. Quality only improves if the team uses AI to test assumptions, evidence, and timing.\n\n"
            "A better question for a marketing team this week:\n"
            "What is one decision we keep making with weak inputs?\n\n"
            "That might be a campaign angle, a product feed structure, a content brief, a positioning claim, or a "
            "customer objection we keep hand-waving away.\n\n"
            "Use AI there. Not to replace the team, but to make bad thinking harder to hide.\n\n"
            f"Sources that sparked the thought: {source_line}\n"
            f"Starting link: {first_url}\n\n"
            "#AIMarketing #MarketingStrategy #MarTech #ContentMarketing"
        )
        return body[: self.config.max_post_chars]


def create_llm_client(config: AppConfig, dry_run: bool = False) -> LLMClient:
    if dry_run or config.llm_provider == "mock":
        return TemplateClient(config)

    provider = config.llm_provider
    if provider == "auto":
        if os.getenv("OPENAI_API_KEY"):
            provider = "openai"
        elif os.getenv("ANTHROPIC_API_KEY"):
            provider = "anthropic"

    if provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        return OpenAIClient(config)
    if provider == "anthropic":
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
        return AnthropicClient(config)

    raise RuntimeError(
        "No LLM provider configured. Set OPENAI_API_KEY or ANTHROPIC_API_KEY, "
        "or run with --dry-run."
    )


def _system_prompt(config: AppConfig) -> str:
    return (
        "You are a sharp senior marketing strategist writing in English for LinkedIn. "
        "Turn recent AI/marketing articles into a personal, useful, opinionated post. "
        "Do not summarize mechanically. Choose one specific angle, make a clear argument, "
        "and give readers a practical way to think or act differently. Write in first person "
        "when it helps, but do not invent personal achievements or private experiences. "
        "Avoid generic claims like 'AI is changing marketing' unless immediately followed "
        "by a specific, non-obvious point. Include source link and author credit. Use 3-5 "
        f"hashtags. Aim for a strong, substantive post under about {config.max_post_chars} characters."
        f"{_voice_block(config)}"
    )


def _digest_system_prompt(config: AppConfig) -> str:
    return (
        "You are a sharp senior marketing strategist writing in English for LinkedIn. "
        "You receive recent articles about AI, marketing, SEO, content, advertising, "
        "customer behavior, and martech. Create ONE personal, useful LinkedIn post that "
        "uses the sources as inspiration for a real point of view. Do not create a generic "
        "news recap. Do not cover every article. Pick one narrow, specific topic that matters "
        "to marketers right now, build a strong argument, and make it practical.\n\n"
        "Style rules:\n"
        "- English only.\n"
        "- Personal and direct, but not fake-confessional.\n"
        "- Strong hook in the first 1-2 lines.\n"
        "- One clear thesis, not a list of unrelated trends.\n"
        "- Specific examples, mechanisms, or decisions marketers actually face.\n"
        "- Useful to operators, founders, marketers, or content/SEO teams.\n"
        "- Never banal. Avoid phrases like 'AI is changing everything', 'game changer', "
        "'in today's fast-paced world', and empty hype.\n"
        "- Mention that the sources/news sparked the thought, but the post should stand "
        "as its own insight.\n"
        "- End with a practical takeaway or question worth discussing.\n"
        "- Add 3-5 relevant hashtags.\n"
        "- Internally perform a claim audit before writing: identify what the sources actually support, "
        "what is only an inference, and what may be hype or uncertainty. In the final post, make this "
        "discernment visible when useful, without turning the post into a formal fact-check.\n"
        "- The reader should feel they are getting a considered point of view, not recycled news.\n"
        f"Keep it substantial but under about {config.max_post_chars} characters."
        f"{_voice_block(config)}"
    )


def _article_prompt(article: Article) -> str:
    published = article.published_at.isoformat() if article.published_at else "data non disponibile"
    return (
        f"Fonte: {article.source}\n"
        f"Titolo: {article.title}\n"
        f"URL: {article.url}\n"
        f"Data: {published}\n"
        f"Autore: {article.author or 'non indicato'}\n"
        f"Estratto: {article.excerpt}\n\n"
        f"Testo disponibile:\n{article.text[:6000]}"
    )


def _digest_prompt(articles: list[Article]) -> str:
    rows: list[dict[str, Any]] = []
    for index, article in enumerate(articles[:10], start=1):
        rows.append(
            {
                "id": index,
                "source": article.source,
                "title": article.title,
                "url": article.url,
                "author": article.author,
                "published_at": article.published_at.isoformat() if article.published_at else None,
                "excerpt": (article.excerpt or article.text[:600])[:900],
            }
        )
    return (
        "Write one LinkedIn post in English using these articles as raw material. "
        "Article id 1 is the anchor: use it as the main spark for this specific post. "
        "The other articles are context only, useful for pattern recognition and contrast. "
        "First study the sources. Decide what is actually supported, what is probably true but inferred, "
        "and what should be treated carefully. Then choose the strongest specific angle connected to the anchor. "
        "Write a post that feels like a real practitioner's point of view, not a digest. The post should be "
        "a bit long, specific, and strong for the marketing sector. It should be useful even to someone who "
        "never opens the links. The reader should understand the issue through the author's thinking, not through "
        "the original sites' framing. Do not invent facts beyond the excerpts. Credit the main sources briefly "
        "near the end.\n\n"
        + json.dumps(rows, ensure_ascii=False)
    )


def _voice_block(config: AppConfig) -> str:
    if not config.editorial_voice:
        return ""
    return (
        "\n\nEditorial voice and point of view to follow. Treat this as the author's thinking, "
        "not as optional style decoration:\n"
        f"{config.editorial_voice}\n"
    )


def _ranking_system_prompt(limit: int) -> str:
    return (
        "Sei un editor per una newsletter LinkedIn su AI applicata al marketing. "
        f"Scegli i {limit} articoli piu' utili, recenti e concreti. Rispondi solo con JSON "
        'nel formato {"ids": [0, 2, 1]}.'
    )


def _ranking_prompt(articles: list[Article]) -> str:
    rows: list[dict[str, Any]] = []
    for index, article in enumerate(articles):
        rows.append(
            {
                "id": index,
                "source": article.source,
                "title": article.title,
                "published_at": article.published_at.isoformat() if article.published_at else None,
                "excerpt": (article.excerpt or article.text[:500])[:700],
            }
        )
    return json.dumps(rows, ensure_ascii=False)


def _rank_from_json(content: str, articles: list[Article], limit: int) -> list[Article]:
    try:
        start = content.index("{")
        end = content.rindex("}") + 1
        payload = json.loads(content[start:end])
        ids = payload.get("ids", [])
    except (ValueError, json.JSONDecodeError, AttributeError):
        LOGGER.warning("Could not parse LLM ranking response; using keyword ranking")
        return articles[:limit]

    ranked: list[Article] = []
    seen: set[int] = set()
    for item in ids:
        try:
            index = int(item)
        except (TypeError, ValueError):
            continue
        if 0 <= index < len(articles) and index not in seen:
            ranked.append(articles[index])
            seen.add(index)
        if len(ranked) >= limit:
            break
    for index, article in enumerate(articles):
        if len(ranked) >= limit:
            break
        if index not in seen:
            ranked.append(article)
    return ranked


def _anthropic_text(response: Any) -> str:
    chunks = []
    for block in response.content:
        text = getattr(block, "text", None)
        if text:
            chunks.append(text)
    return "\n".join(chunks)
