from __future__ import annotations

import base64
import logging
import os
from datetime import date
from pathlib import Path

from .models import AppConfig, PublicArticle

LOGGER = logging.getLogger(__name__)


def create_article_image(article: PublicArticle, config: AppConfig, run_date: date) -> Path | None:
    assets_dir = config.output_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    image_path = assets_dir / f"{run_date.isoformat()}-hero.png"

    if not config.image_enabled:
        return None

    if os.getenv("OPENAI_API_KEY"):
        try:
            return _create_openai_image(article, config, image_path)
        except Exception as exc:
            LOGGER.warning("AI image generation failed; using local placeholder: %s", exc)
            LOGGER.debug("AI image generation details", exc_info=True)

    return _create_placeholder_svg(article, assets_dir / f"{run_date.isoformat()}-hero.svg")


def _create_openai_image(article: PublicArticle, config: AppConfig, image_path: Path) -> Path:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    prompt = (
        f"{article.image_prompt}\n\n"
        "Visual direction: premium editorial illustration/photo hybrid, serious business publication, "
        "warm natural light, specific visual metaphor, no text, no letters, no logos, no brand marks, no robots."
    )
    response = client.images.generate(
        model=config.image_model,
        prompt=prompt,
        size=config.image_size,
        quality=config.image_quality,
        n=1,
    )
    data = response.data[0]
    b64_json = getattr(data, "b64_json", None)
    if not b64_json:
        raise RuntimeError("OpenAI image response did not contain b64_json")
    image_path.write_bytes(base64.b64decode(b64_json))
    return image_path


def _create_placeholder_svg(article: PublicArticle, image_path: Path) -> Path:
    title = _escape_xml(article.title[:90])
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1536 1024" role="img">
  <defs>
    <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0" stop-color="#f7f8fa"/>
      <stop offset="1" stop-color="#d7ede8"/>
    </linearGradient>
  </defs>
  <rect width="1536" height="1024" fill="url(#bg)"/>
  <circle cx="1180" cy="220" r="180" fill="#0f766e" opacity="0.10"/>
  <circle cx="320" cy="780" r="240" fill="#155e75" opacity="0.10"/>
  <rect x="220" y="240" width="1096" height="544" rx="28" fill="#ffffff" opacity="0.82"/>
  <path d="M320 650 C520 420 710 740 930 470 S1160 410 1210 560" fill="none" stroke="#0f766e" stroke-width="18" stroke-linecap="round"/>
  <path d="M360 520 H690 M360 575 H820 M360 710 H1050" stroke="#172033" stroke-width="16" stroke-linecap="round" opacity="0.18"/>
  <text x="300" y="370" fill="#172033" font-family="Arial, Helvetica, sans-serif" font-size="54" font-weight="700">{title}</text>
</svg>
"""
    image_path.write_text(svg, encoding="utf-8")
    return image_path


def _escape_xml(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
