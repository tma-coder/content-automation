import logging
from core.news_monitor import fetch_all_topics
from core.article_generator import generate_article
from core.image_generator import generate_image
from publishers.facebook_pub import FacebookPublisher
import config
import db

logger = logging.getLogger(__name__)
fb = FacebookPublisher()


def process_news_item(item, auto_approve=False):
    try:
        article = generate_article(item.title, item.summary, item.link)
    except Exception as e:
        logger.error(f"Article generation failed for '{item.title}': {e}")
        return None

    image_path = generate_image(article.title, article.short_text)

    status = "approved" if auto_approve else "pending"
    article_id = db.save_article(
        source_url=item.link, source_title=item.title,
        generated_title=article.title, short_text=article.short_text,
        long_text=article.long_text, hashtags=article.hashtags,
        image_path=image_path, status=status,
    )
    logger.info(f"Article #{article_id} saved [{status}]: {article.title}")

    if auto_approve:
        publish_article(article_id)
    return article_id


def publish_article(article_id):
    article = db.get_article(article_id)
    if not article:
        return {}

    results = {}
    try:
        result = fb.publish(
            title=article["generated_title"], body=article["long_text"],
            short_text=article["short_text"], hashtags=article["hashtags"],
            image_path=article["image_path"], link=article["source_url"],
        )
        db.log_post(article_id, "facebook", result["success"],
                     post_id=result.get("post_id", ""), error_message=result.get("error", ""))
        results["facebook"] = result["success"]
        if result["success"]:
            logger.info(f"Posted to Facebook: {result.get('post_id')}")
        else:
            logger.error(f"Facebook failed: {result.get('error')}")
    except Exception as e:
        logger.error(f"Facebook exception: {e}")
        db.log_post(article_id, "facebook", False, error_message=str(e))
        results["facebook"] = False

    db.update_article_status(article_id, "posted" if any(results.values()) else "failed")
    return results


def run_cycle(auto=False):
    logger.info(f"Starting {'auto' if auto else 'manual'} cycle...")
    items = fetch_all_topics(max_per_topic=1)
    if not items:
        logger.info("No new articles found")
        return []

    items = items[:config.MAX_ARTICLES_PER_CYCLE]
    article_ids = []
    for item in items:
        aid = process_news_item(item, auto_approve=auto)
        if aid:
            article_ids.append(aid)

    logger.info(f"Cycle complete. {len(article_ids)} article(s) {'posted' if auto else 'pending'}.")
    return article_ids
