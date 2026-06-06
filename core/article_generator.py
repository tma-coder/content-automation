import json
import logging
from dataclasses import dataclass
from google import genai
from google.genai import types
import config

logger = logging.getLogger(__name__)

client = genai.Client(api_key=config.GOOGLE_GENAI_API_KEY)

SYSTEM_PROMPT = """You are a professional social media content writer. Given a news story,
create engaging, original content. Do NOT copy the source — write your own unique take.

Respond with valid JSON only, no markdown fences:
{
    "title": "Catchy headline (max 100 chars)",
    "short_text": "Concise post for Instagram/Pinterest (max 280 chars). Include a call to action.",
    "long_text": "Detailed post for Facebook (300-500 words). Include analysis and unique perspective.",
    "hashtags": "#tag1 #tag2 #tag3 (5-10 relevant hashtags)"
}"""


@dataclass
class GeneratedArticle:
    title: str
    short_text: str
    long_text: str
    hashtags: str


def generate_article(news_title, news_summary, news_link):
    logger.info(f"Generating article for: {news_title}")

    prompt = f"""Create social media content based on this news:
Title: {news_title}
Summary: {news_summary}
Source: {news_link}

Write original content. Return valid JSON only."""

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.8,
            max_output_tokens=1500,
        ),
    )

    text = response.text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    data = json.loads(text)
    article = GeneratedArticle(
        title=data.get("title", news_title),
        short_text=data.get("short_text", ""),
        long_text=data.get("long_text", ""),
        hashtags=data.get("hashtags", ""),
    )
    logger.info(f"Article generated: {article.title}")
    return article
