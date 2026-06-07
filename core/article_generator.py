import json
import logging
import re
from dataclasses import dataclass
from openai import OpenAI
import config

logger = logging.getLogger(__name__)

FREE_MODELS = [
    "google/gemini-3.5-flash:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "deepseek/deepseek-chat-v3-0324:free",
    "meta-llama/llama-4-maverick:free",
    "microsoft/phi-4-reasoning:free",
    "qwen/qwen3-235b-a22b:free",
    "mistralai/mistral-small-3.2-24b-instruct:free",
]


@dataclass
class GeneratedArticle:
    title: str
    short_text: str
    long_text: str
    hashtags: str
    subject: str = ""
    highlight_phrases: list = None


SYSTEM_PROMPT = """You are a professional social media content writer. Given a news story,
create engaging, original content. Do NOT copy the source.

You MUST respond with ONLY valid JSON, no markdown, no explanation, no fences.
Format:
{
    "title": "Catchy headline (max 120 chars). Can be a quote or statement.",
    "short_text": "Concise post (max 280 chars). Include a call to action.",
    "long_text": "Detailed post (300-500 words). Include analysis and unique perspective.",
    "hashtags": "#tag1 #tag2 #tag3 (5-10 relevant hashtags)",
    "subject": "Visual subject for the cover photo (e.g. 'businessman speaking at podium', 'crypto trader at computer screens', 'rocket launching')",
    "highlight_phrases": ["2-3 key phrases from the title to highlight (each 2-6 words)"]
}"""


def _extract_json(text):
    """Robustly extract JSON object from text that may have extra content."""
    if not text:
        return None

    text = text.strip()

    # Remove markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find the first { and last } to extract just the JSON
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    candidate = text[start:end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # Try to fix common issues: trailing commas, single quotes
        candidate = re.sub(r",(\s*[}\]])", r"\1", candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None


def generate_article(news_title, news_summary, news_link):
    if not config.OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not set")

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=config.OPENROUTER_API_KEY,
    )

    prompt = f"""Create social media content based on this news:
Title: {news_title}
Summary: {news_summary}
Source: {news_link}

Write original content. Return ONLY valid JSON, nothing else."""

    last_error = None

    for model in FREE_MODELS:
        try:
            logger.info(f"Trying model: {model}")
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
                max_tokens=1500,
            )

            if not response.choices:
                logger.warning(f"{model}: empty choices")
                continue

            content = response.choices[0].message.content
            if not content:
                logger.warning(f"{model}: empty content")
                continue

            data = _extract_json(content)
            if not data:
                logger.warning(f"{model}: could not extract JSON from response")
                continue

            # Validate required fields
            title = data.get("title") or news_title
            short_text = data.get("short_text") or ""
            long_text = data.get("long_text") or ""
            hashtags = data.get("hashtags") or ""

            if not short_text and not long_text:
                logger.warning(f"{model}: missing both short_text and long_text")
                continue

            subject = data.get("subject") or ""
            highlights = data.get("highlight_phrases") or []
            if not isinstance(highlights, list):
                highlights = []

            logger.info(f"Article generated successfully with: {model}")
            return GeneratedArticle(
                title=str(title)[:200],
                short_text=str(short_text)[:500],
                long_text=str(long_text)[:3000],
                hashtags=str(hashtags)[:500],
                subject=str(subject)[:200],
                highlight_phrases=[str(h)[:80] for h in highlights[:4]],
            )

        except Exception as e:
            last_error = e
            logger.warning(f"Model {model} failed: {e}")
            continue

    raise Exception(f"All models failed. Last error: {last_error}")
