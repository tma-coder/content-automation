import json
import logging
from dataclasses import dataclass
from openai import OpenAI
import config

logger = logging.getLogger(__name__)

# Free models on OpenRouter - tries in order, falls back to next if one fails
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


SYSTEM_PROMPT = """You are a professional social media content writer. Given a news story,
create engaging, original content. Do NOT copy the source.

Respond with valid JSON only, no markdown fences:
{
    "title": "Catchy headline (max 100 chars)",
    "short_text": "Concise post (max 280 chars). Include a call to action.",
    "long_text": "Detailed post (300-500 words). Include analysis and unique perspective.",
    "hashtags": "#tag1 #tag2 #tag3 (5-10 relevant hashtags)"
}"""


def generate_article(news_title, news_summary, news_link):
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=config.OPENROUTER_API_KEY,
    )

    prompt = f"""Create social media content based on this news:
Title: {news_title}
Summary: {news_summary}
Source: {news_link}

Write original content. Return valid JSON only."""

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

            text = response.choices[0].message.content.strip()
            if text.startswith("```"):
                lines = [l for l in text.split("\n") if not l.strip().startswith("```")]
                text = "\n".join(lines)

            data = json.loads(text)
            logger.info(f"Article generated successfully with: {model}")
            return GeneratedArticle(
                title=data.get("title", news_title),
                short_text=data.get("short_text", ""),
                long_text=data.get("long_text", ""),
                hashtags=data.get("hashtags", ""),
            )

        except Exception as e:
            last_error = e
            logger.warning(f"Model {model} failed: {e}")
            continue

    raise Exception(f"All models failed. Last error: {last_error}")
