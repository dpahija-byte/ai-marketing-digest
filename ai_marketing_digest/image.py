from __future__ import annotations

import base64
import logging
import os
import shutil
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

    if config.image_static_path:
        static_path = config.image_static_path
        if static_path.exists():
            target = assets_dir / f"{run_date.isoformat()}-hero{static_path.suffix}"
            shutil.copyfile(static_path, target)
            return target
        LOGGER.warning("Configured static image was not found: %s", static_path)

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


def _create_placeholder_svg(_article: PublicArticle, image_path: Path) -> Path:
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1536 864" role="img" aria-label="Abstract editorial image about AI marketing strategy">
  <defs>
    <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0" stop-color="#f8f6f0"/>
      <stop offset="0.52" stop-color="#eef4f2"/>
      <stop offset="1" stop-color="#e8edf7"/>
    </linearGradient>
    <linearGradient id="plane" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0.94"/>
      <stop offset="1" stop-color="#f5f7f9" stop-opacity="0.84"/>
    </linearGradient>
  </defs>
  <rect width="1536" height="864" fill="url(#bg)"/>
  <path d="M0 676 L420 520 L780 618 L1536 360 L1536 864 L0 864 Z" fill="#0f766e" opacity="0.08"/>
  <path d="M0 168 L420 58 L900 150 L1536 48 L1536 0 L0 0 Z" fill="#273449" opacity="0.06"/>
  <g transform="translate(214 138)">
    <rect x="0" y="88" width="1108" height="540" rx="34" fill="url(#plane)" stroke="#d7dde5" stroke-width="2"/>
    <rect x="92" y="166" width="360" height="216" rx="18" fill="#ffffff" stroke="#dce2e8" stroke-width="2"/>
    <rect x="516" y="166" width="500" height="216" rx="18" fill="#ffffff" stroke="#dce2e8" stroke-width="2"/>
    <rect x="92" y="438" width="924" height="98" rx="18" fill="#ffffff" stroke="#dce2e8" stroke-width="2"/>
    <path d="M164 324 C254 210 372 352 482 270 C606 178 700 344 812 240 C888 170 946 194 986 246" fill="none" stroke="#0f766e" stroke-width="16" stroke-linecap="round"/>
    <path d="M592 474 H730 M766 474 H902 M158 474 H394" stroke="#273449" stroke-width="14" stroke-linecap="round" opacity="0.15"/>
    <path d="M158 512 H514 M552 512 H808 M846 512 H956" stroke="#273449" stroke-width="14" stroke-linecap="round" opacity="0.10"/>
    <g fill="#d97706" opacity="0.68">
      <rect x="170" y="208" width="42" height="42" rx="10"/>
      <rect x="224" y="208" width="42" height="42" rx="10"/>
      <rect x="278" y="208" width="42" height="42" rx="10"/>
    </g>
    <g stroke="#273449" stroke-width="10" stroke-linecap="round" opacity="0.24">
      <path d="M620 228 H934"/>
      <path d="M620 272 H874"/>
      <path d="M620 316 H962"/>
    </g>
    <g fill="#0f766e" opacity="0.16">
      <rect x="90" y="54" width="168" height="54" rx="16"/>
      <rect x="840" y="44" width="214" height="64" rx="18"/>
    </g>
  </g>
  <path d="M1172 636 L1264 690 L1350 606" fill="none" stroke="#d97706" stroke-width="14" stroke-linecap="round" stroke-linejoin="round" opacity="0.76"/>
</svg>
"""
    image_path.write_text(svg, encoding="utf-8")
    return image_path
