import json
import logging
from dataclasses import dataclass
from openai import OpenAI
import config

logger = logging.getLogger(__name__)


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

    response = client.chat.completions.create(
        model="google/gemini-2.0-flash-exp:free",
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
    return GeneratedArticle(
        title=data.get("title", news_title),
        short_text=data.get("short_text", ""),
        long_text=data.get("long_text", ""),
        hashtags=data.get("hashtags", ""),
    )
