from __future__ import annotations

from dataclasses import dataclass

from .models import Article

AI_KEYWORDS = {
    "ai",
    "a.i.",
    "artificial intelligence",
    "generative ai",
    "genai",
    "llm",
    "large language model",
    "chatgpt",
    "claude",
    "copilot",
    "gemini",
    "machine learning",
    "automation",
    "automated",
    "prompt",
    "prompting",
    "agent",
    "agentic",
    "chatbot",
    "predictive",
    "personalization",
    "synthetic",
}

MARKETING_KEYWORDS = {
    "marketing",
    "marketer",
    "content",
    "seo",
    "search",
    "paid search",
    "advertising",
    "ads",
    "campaign",
    "brand",
    "social media",
    "linkedin",
    "email",
    "newsletter",
    "customer",
    "consumer",
    "lead",
    "conversion",
    "demand generation",
    "crm",
    "ecommerce",
    "sales",
    "funnel",
    "copywriting",
}


@dataclass(frozen=True)
class ScoredArticle:
    article: Article
    score: int
    ai_hits: tuple[str, ...]
    marketing_hits: tuple[str, ...]

    @property
    def is_relevant(self) -> bool:
        return bool(self.ai_hits and self.marketing_hits and self.score >= 4)

    @property
    def reason(self) -> str:
        if self.is_relevant:
            return f"score={self.score}; ai={','.join(self.ai_hits)}; marketing={','.join(self.marketing_hits)}"
        missing = []
        if not self.ai_hits:
            missing.append("AI keyword")
        if not self.marketing_hits:
            missing.append("marketing keyword")
        if self.score < 4:
            missing.append("score<4")
        return "; ".join(missing)


def score_articles(articles: list[Article]) -> list[ScoredArticle]:
    scored = [score_article(article) for article in articles]
    return sorted(scored, key=lambda item: item.score, reverse=True)


def score_article(article: Article) -> ScoredArticle:
    title = article.title.lower()
    excerpt = article.excerpt.lower()
    text = article.text[:5000].lower()
    ai_hits = _keyword_hits(title, excerpt, text, AI_KEYWORDS)
    marketing_hits = _keyword_hits(title, excerpt, text, MARKETING_KEYWORDS)
    score = _score_hits(title, excerpt, text, ai_hits) + _score_hits(title, excerpt, text, marketing_hits)
    return ScoredArticle(article=article, score=score, ai_hits=ai_hits, marketing_hits=marketing_hits)


def _keyword_hits(title: str, excerpt: str, text: str, keywords: set[str]) -> tuple[str, ...]:
    hits = []
    for keyword in sorted(keywords, key=len, reverse=True):
        if keyword in title or keyword in excerpt or keyword in text:
            hits.append(keyword)
    return tuple(hits[:6])


def _score_hits(title: str, excerpt: str, text: str, hits: tuple[str, ...]) -> int:
    score = 0
    for keyword in hits:
        if keyword in title:
            score += 3
        if keyword in excerpt:
            score += 2
        if keyword in text:
            score += 1
    return score
