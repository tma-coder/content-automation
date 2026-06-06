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
    url = GOOGLE_NEWS_RSS.format(query=topic.replace(" ", "+"))
    logger.info(f"Fetching news for: {topic}")
    try:
        feed = feedparser.parse(url)
    except Exception as e:
        logger.error(f"RSS fetch failed for '{topic}': {e}")
        return []

    items = []
    for entry in feed.entries[:max_items]:
        link = entry.get("link", "")
        title = entry.get("title", "")
        summary = entry.get("summary", entry.get("description", ""))
        if not link or not title or db.article_exists(link):
            continue
        items.append(NewsItem(title=title, link=link, summary=summary, published=entry.get("published", "")))

    logger.info(f"Found {len(items)} new articles for: {topic}")
    return items


def fetch_all_topics(max_per_topic=1):
    all_items = []
    for topic in config.NEWS_TOPICS:
        all_items.extend(fetch_news(topic, max_items=max_per_topic))
    return all_items
