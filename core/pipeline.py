import logging
from core.news_monitor import fetch_all_topics, fetch_news
from core.article_generator import generate_article
from core.image_generator import generate_image
from publishers.facebook_pub import FacebookPublisher
import config
import db

logger = logging.getLogger(__name__)


def process_news_item(item, auto_approve=False):
    try:
        article = generate_article(item.title, item.summary, item.link)
    except Exception as e:
        logger.error(f"Article generation failed: {e}")
        return None

    image_url = generate_image(article.title, article.short_text)

    status = "approved" if auto_approve else "pending"
    article_id = db.save_article(
        source_url=item.link, source_title=item.title,
        generated_title=article.title, short_text=article.short_text,
        long_text=article.long_text, hashtags=article.hashtags,
        image_url=image_url, status=status, published_at=item.published,
    )

    if auto_approve and article_id:
        publish_article(article_id)
    return article_id


def publish_article(article_id):
    article = db.get_article(article_id)
    if not article:
        return {}

    fb = FacebookPublisher()
    results = {}
    try:
        result = fb.publish(
            title=article["generated_title"], body=article["long_text"],
            short_text=article["short_text"], hashtags=article["hashtags"],
            image_url=article["image_url"], link=article["source_url"],
        )
        db.log_post(article_id, "facebook", result["success"],
                     post_id=result.get("post_id", ""), error_message=result.get("error", ""))
        results["facebook"] = result["success"]
    except Exception as e:
        db.log_post(article_id, "facebook", False, error_message=str(e))
        results["facebook"] = False

    db.update_article_status(article_id, "posted" if any(results.values()) else "failed")
    return results


def run_cycle(auto=False, topics=None):
    if topics:
        items = []
        for topic in topics:
            items.extend(fetch_news(topic, max_items=1))
    else:
        items = fetch_all_topics(max_per_topic=1)

    if not items:
        return []

    items = items[:config.MAX_ARTICLES_PER_CYCLE]
    article_ids = []
    for item in items:
        aid = process_news_item(item, auto_approve=auto)
        if aid:
            article_ids.append(aid)
    return article_ids
