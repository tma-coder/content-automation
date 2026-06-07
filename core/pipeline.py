import logging
from core.news_monitor import fetch_all_topics, fetch_news
from core.article_generator import generate_article
from core.image_generator import generate_image
from publishers.facebook_pub import FacebookPublisher
import config
import db

logger = logging.getLogger(__name__)


def process_news_item(item, auto_approve=False):
    """Process one news item: generate article + image, save, optionally publish."""
    if not item or not item.link:
        logger.warning("Invalid news item")
        return None

    # Generate article (required)
    try:
        article = generate_article(item.title, item.summary, item.link)
    except Exception as e:
        logger.error(f"Article generation failed for '{item.title[:60]}': {e}")
        return None

    # Generate image (always returns something, even fallback)
    try:
        image_url = generate_image(
            article.title,
            article.short_text,
            subject=article.subject or "",
            highlight_phrases=article.highlight_phrases or [],
        )
    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        image_url = ""

    status = "approved" if auto_approve else "pending"

    try:
        article_id = db.save_article(
            source_url=item.link,
            source_title=item.title,
            generated_title=article.title,
            short_text=article.short_text,
            long_text=article.long_text,
            hashtags=article.hashtags,
            image_url=image_url,
            status=status,
            published_at=item.published or "",
        )
    except Exception as e:
        logger.error(f"DB save failed: {e}")
        return None

    if not article_id:
        return None

    logger.info(f"Saved article #{article_id}: {article.title[:60]}")

    if auto_approve:
        try:
            publish_article(article_id)
        except Exception as e:
            logger.error(f"Auto-publish failed for #{article_id}: {e}")

    return article_id


def publish_article(article_id):
    """Publish an article to all enabled platforms."""
    article = db.get_article(article_id)
    if not article:
        logger.error(f"Article #{article_id} not found")
        return {}

    results = {}

    # Facebook
    if config.META_PAGE_ACCESS_TOKEN and config.FACEBOOK_PAGE_ID:
        fb = FacebookPublisher()
        try:
            result = fb.publish(
                title=article["generated_title"],
                body=article["long_text"],
                short_text=article["short_text"],
                hashtags=article["hashtags"],
                image_url=article["image_url"],
                link=article["source_url"],
            )
            db.log_post(
                article_id,
                "facebook",
                result["success"],
                post_id=result.get("post_id", ""),
                error_message=result.get("error", ""),
            )
            results["facebook"] = result["success"]
            if result["success"]:
                logger.info(f"Posted to Facebook: {result.get('post_id', '')}")
            else:
                logger.error(f"Facebook failed: {result.get('error', '')}")
        except Exception as e:
            logger.exception(f"Facebook exception for #{article_id}")
            try:
                db.log_post(article_id, "facebook", False, error_message=str(e))
            except Exception:
                pass
            results["facebook"] = False

    # Update status
    new_status = "posted" if any(results.values()) else "failed"
    try:
        db.update_article_status(article_id, new_status)
    except Exception as e:
        logger.error(f"Status update failed: {e}")

    return results


def run_cycle(auto=False, topics=None):
    """Fetch news, generate content for each item. Returns list of article IDs."""
    try:
        if topics:
            items = []
            for topic in topics:
                items.extend(fetch_news(topic, max_items=1))
        else:
            items = fetch_all_topics(max_per_topic=1)
    except Exception as e:
        logger.exception("Fetch failed")
        return []

    if not items:
        logger.info("No new articles found this cycle")
        return []

    items = items[:config.MAX_ARTICLES_PER_CYCLE]
    logger.info(f"Processing {len(items)} article(s), auto={auto}")

    article_ids = []
    for item in items:
        try:
            aid = process_news_item(item, auto_approve=auto)
            if aid:
                article_ids.append(aid)
        except Exception as e:
            logger.exception(f"Processing failed for: {item.title[:60]}")

    return article_ids
