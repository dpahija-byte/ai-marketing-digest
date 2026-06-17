from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

from .models import AppConfig, Article, PublicArticle

LOGGER = logging.getLogger(__name__)


class LLMClient(ABC):
    @abstractmethod
    def generate_post(self, article: Article) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_digest_post(self, articles: list[Article]) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_public_article(self, articles: list[Article], source_count: int) -> PublicArticle:
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

    def generate_public_article(self, articles: list[Article], source_count: int) -> PublicArticle:
        response = self.client.chat.completions.create(
            model=self.config.openai_model,
            temperature=self.config.llm_temperature,
            max_tokens=2600,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _public_article_system_prompt(self.config)},
                {"role": "user", "content": _public_article_prompt(articles, source_count)},
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("OpenAI returned an empty public article")
        return _public_article_from_json(content, articles, source_count)

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

    def generate_public_article(self, articles: list[Article], source_count: int) -> PublicArticle:
        response = self.client.messages.create(
            model=self.config.anthropic_model,
            max_tokens=2600,
            temperature=self.config.llm_temperature,
            system=_public_article_system_prompt(self.config),
            messages=[{"role": "user", "content": _public_article_prompt(articles, source_count)}],
        )
        return _public_article_from_json(_anthropic_text(response), articles, source_count)

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

    def generate_public_article(self, articles: list[Article], source_count: int) -> PublicArticle:
        title = "The Real AI Marketing Advantage Is Not More Content"
        subtitle = "A daily editorial take on why the next edge belongs to teams that use AI to pressure-test judgment before they publish."
        body = (
            "Most AI marketing discussions still start in the wrong place: output.\n\n"
            "More posts. More ads. More landing page variants. More emails. More everything.\n\n"
            "But if everyone can produce more, volume stops being an advantage very quickly. "
            "The real advantage moves upstream: into judgment.\n\n"
            "The useful question is not whether a marketer can generate content faster. "
            "The useful question is whether the team can make better decisions before content exists.\n\n"
            "That is where today's research signals point. Search behavior is being reshaped by AI answers. "
            "Commerce flows are becoming more agentic. Brand reputation is increasingly interpreted by systems "
            "that summarize, rank, and compress what the market already believes. None of that is solved by asking "
            "for ten more post ideas.\n\n"
            "What feels solid: AI is becoming part of the marketing operating layer. It is touching briefs, feeds, "
            "search visibility, customer journeys, and the way brands are interpreted before a human ever lands on a website.\n\n"
            "What I would treat carefully: the idea that automation automatically creates better marketing. "
            "It usually creates more marketing first. Better only happens when the team uses AI to expose weak assumptions.\n\n"
            "A practical test for any marketing team:\n\n"
            "Before asking AI to write the asset, ask it to challenge the decision behind the asset.\n\n"
            "- What assumption are we making about the buyer?\n"
            "- What claim sounds generic?\n"
            "- What proof is missing?\n"
            "- What would a skeptical customer reject?\n"
            "- Which channel would punish this idea fastest?\n\n"
            "That is not glamorous. But it is where the leverage is.\n\n"
            "AI should not become the machine that helps us publish weak thinking faster. "
            "It should become the pressure system that makes weak thinking harder to ship."
        )
        image_prompt = (
            "Editorial hero image for an AI marketing strategy article. A modern strategy desk with layered research notes, "
            "abstract signal maps, search/commercial flows, and a calm human decision-maker. Sophisticated, realistic, "
            "not futuristic cliche, no text, no logos, no robot."
        )
        return PublicArticle(
            title=title,
            subtitle=subtitle,
            body_markdown=body,
            sources_markdown=_default_sources_note(articles),
            image_prompt=image_prompt,
            source_count=source_count,
            article_count=len(articles),
        )


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


def _public_article_system_prompt(config: AppConfig) -> str:
    return (
        "You are writing the daily public article for an independent AI marketing publication. "
        "Your job is not to summarize or promote the sources. Your job is to study them, extract the strongest "
        "signals, separate supported claims from hype, and write one original article that follows the author's "
        "point of view.\n\n"
        "Output must be valid JSON with exactly these keys:\n"
        '- "title": strong article title, not clickbait.\n'
        '- "subtitle": one-sentence promise for the reader.\n'
        '- "body_markdown": the full article in Markdown.\n'
        '- "sources_markdown": a compact Markdown source note with 5-10 selected source links.\n'
        '- "image_prompt": prompt for an AI-generated editorial hero image.\n\n'
        "Article requirements:\n"
        "- English only.\n"
        "- 900-1400 words if there is enough material.\n"
        "- One clear thesis, not a roundup.\n"
        "- Personal, analytical, useful, and specific. It must read like the author's own article.\n"
        "- Do not imitate the wording or structure of source sites.\n"
        "- Do not send readers away with source-led paragraphs or a list of external links.\n"
        "- Do not mention source names, URLs, or authors inside body_markdown unless absolutely necessary for accuracy.\n"
        "- Keep all source credits in sources_markdown, after the article.\n"
        "- Make your reasoning visible: what seems solid, what is inferred, what may be overhyped.\n"
        "- Give the reader a practical decision rule, framework, or operational takeaway.\n"
        "- Avoid generic LinkedIn language and motivational fluff.\n"
        "- Do not invent facts beyond the source excerpts.\n"
        "- Do not include raw URLs in body_markdown. In sources_markdown, use Markdown links.\n"
        "- The hero image prompt must request no text, no logos, no UI screenshots, no robots, and no brand names.\n"
        f"{_voice_block(config)}"
    )


def _public_article_prompt(articles: list[Article], source_count: int) -> str:
    rows: list[dict[str, Any]] = []
    for index, article in enumerate(articles[:40], start=1):
        rows.append(
            {
                "id": index,
                "source": article.source,
                "title": article.title,
                "url": article.url,
                "author": article.author,
                "published_at": article.published_at.isoformat() if article.published_at else None,
                "excerpt": (article.excerpt or article.text[:900])[:1200],
            }
        )
    return (
        f"You reviewed {len(articles)} recent articles from {source_count} sources. "
        "Use the following research material to create one original daily article. "
        "The public article should feel like it belongs to the author's publication, not to the source sites. "
        "Do not output a listicle of sources. Create one strong angle. "
        "Prioritize the newest material, but treat repeated patterns across sources as stronger evidence than one isolated article. "
        "Use source URLs only in sources_markdown at the end, never inside body_markdown.\n\n"
        + json.dumps(rows, ensure_ascii=False)
    )


def _public_article_from_json(content: str, articles: list[Article], source_count: int) -> PublicArticle:
    try:
        start = content.index("{")
        end = content.rindex("}") + 1
        payload = json.loads(content[start:end])
    except (ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Could not parse public article JSON") from exc

    title = str(payload.get("title") or "AI Marketing Daily")
    subtitle = str(payload.get("subtitle") or "A daily analysis of the most useful signals in AI and marketing.")
    body = str(payload.get("body_markdown") or "").strip()
    sources_markdown = str(payload.get("sources_markdown") or "").strip()
    image_prompt = str(payload.get("image_prompt") or "").strip()
    if not body:
        raise RuntimeError("Generated public article body is empty")
    if not sources_markdown or "http" not in sources_markdown:
        sources_markdown = _default_sources_note(articles)
    if not image_prompt:
        image_prompt = (
            "Editorial hero image for a thoughtful AI marketing strategy article. Sophisticated, realistic, "
            "abstract research desk, signal maps, no text, no logos, no robots."
        )
    return PublicArticle(
        title=title,
        subtitle=subtitle,
        body_markdown=body,
        sources_markdown=sources_markdown,
        image_prompt=image_prompt,
        source_count=source_count,
        article_count=len(articles),
    )


def _default_sources_note(articles: list[Article]) -> str:
    if not articles:
        return "- No recent source links were available for this run."

    lines: list[str] = []
    seen: set[str] = set()
    for article in articles:
        if article.url in seen:
            continue
        seen.add(article.url)
        author = f", {article.author}" if article.author else ""
        label = _escape_markdown(f"{article.source}{author}: {article.title}")
        lines.append(f"- [{label}]({article.url})")
        if len(lines) >= 10:
            break
    return "\n".join(lines)


def _escape_markdown(text: str) -> str:
    return text.replace("[", "\\[").replace("]", "\\]")


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
