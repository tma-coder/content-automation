import feedparser
import logging
from dataclasses import dataclass
import db
import config

logger = logging.getLogger(__name__)

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en&gl=US&ceid=US:en"


@dataclass
class NewsItem:
    title: str
    link: str
    summary: str
    published: str


def fetch_news(topic, max_items=3):
    """Fetch news for a topic. Deduplicates against DB in batch."""
    if not topic:
        return []

    url = GOOGLE_NEWS_RSS.format(query=topic.replace(" ", "+"))
    logger.info(f"Fetching news for: {topic}")

    try:
        feed = feedparser.parse(url)
    except Exception as e:
        logger.error(f"RSS fetch failed for '{topic}': {e}")
        return []

    if not feed.entries:
        logger.info(f"No entries for: {topic}")
        return []

    # Collect raw entries first
    raw = []
    for entry in feed.entries[:max_items * 3]:  # fetch more, dedup later
        link = entry.get("link", "").strip()
        title = entry.get("title", "").strip()
        if not link or not title:
            continue
        raw.append({
            "title": title,
            "link": link,
            "summary": entry.get("summary", entry.get("description", "")),
            "published": entry.get("published", ""),
        })

    if not raw:
        return []

    # Batch dedup against DB
    try:
        existing = db.existing_hashes([r["link"] for r in raw])
    except Exception as e:
        logger.warning(f"Batch dedup failed, falling back: {e}")
        existing = set()

    items = []
    for r in raw:
        if db.hash_url(r["link"]) in existing:
            continue
        items.append(NewsItem(
            title=r["title"],
            link=r["link"],
            summary=r["summary"],
            published=r["published"],
        ))
        if len(items) >= max_items:
            break

    logger.info(f"Found {len(items)} new articles for: {topic}")
    return items


def fetch_all_topics(max_per_topic=1):
    all_items = []
    for topic in config.NEWS_TOPICS:
        all_items.extend(fetch_news(topic, max_items=max_per_topic))
    return all_items
