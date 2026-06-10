import hashlib
import logging
from datetime import datetime, timezone
from supabase import create_client
import config

logger = logging.getLogger(__name__)

_client = None


def get_client():
    global _client
    if _client is None:
        if not config.SUPABASE_URL or not config.SUPABASE_KEY:
            raise RuntimeError("SUPABASE_URL or SUPABASE_KEY not set")
        _client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    return _client


def hash_url(url):
    return hashlib.sha256(url.encode()).hexdigest()


def article_exists(source_url):
    res = get_client().table("articles").select("id").eq("source_hash", hash_url(source_url)).execute()
    return len(res.data) > 0


def existing_hashes(source_urls):
    """Batch check which URLs are already in DB. Returns set of existing hashes."""
    if not source_urls:
        return set()
    hashes = [hash_url(u) for u in source_urls]
    res = get_client().table("articles").select("source_hash").in_("source_hash", hashes).execute()
    return {r["source_hash"] for r in res.data}


def save_article(source_url, source_title, generated_title, short_text, long_text, hashtags, image_url, status="pending", published_at=""):
    data = {
        "source_hash": hash_url(source_url),
        "source_url": source_url,
        "source_title": source_title,
        "generated_title": generated_title,
        "short_text": short_text,
        "long_text": long_text,
        "hashtags": hashtags,
        "image_url": image_url,
        "status": status,
        "published_at": published_at or None,
    }
    try:
        res = get_client().table("articles").insert(data).execute()
        return res.data[0]["id"] if res.data else None
    except Exception as e:
        logger.error(f"Failed to save article: {e}")
        return None


def get_article(article_id):
    res = get_client().table("articles").select("*").eq("id", article_id).execute()
    return res.data[0] if res.data else None


def get_pending_articles():
    res = get_client().table("articles").select("*").eq("status", "pending").order("created_at", desc=True).execute()
    return res.data


def update_article_status(article_id, status):
    data = {"status": status}
    if status == "posted":
        data["posted_at"] = datetime.now(timezone.utc).isoformat()
    get_client().table("articles").update(data).eq("id", article_id).execute()


def update_image(article_id, image_url):
    get_client().table("articles").update({"image_url": image_url}).eq("id", article_id).execute()


def delete_article(article_id):
    try:
        get_client().table("post_log").delete().eq("article_id", article_id).execute()
    except Exception as e:
        logger.warning(f"Post log delete failed (may not exist): {e}")
    get_client().table("articles").delete().eq("id", article_id).execute()


def clear_history():
    """Delete all posted/failed/rejected articles and their post logs."""
    try:
        # Get IDs of articles to delete
        articles = get_client().table("articles").select("id").in_(
            "status", ["posted", "failed", "rejected"]
        ).execute().data
        article_ids = [r["id"] for r in articles]

        if not article_ids:
            return

        # Delete post logs first
        get_client().table("post_log").delete().in_("article_id", article_ids).execute()
        # Then delete articles
        get_client().table("articles").delete().in_("id", article_ids).execute()
        logger.info(f"Cleared {len(article_ids)} history articles")
    except Exception as e:
        logger.error(f"Clear history failed: {e}")


def log_post(article_id, platform, success, post_id="", error_message=""):
    get_client().table("post_log").insert({
        "article_id": article_id,
        "platform": platform,
        "success": bool(success),
        "post_id": post_id,
        "error_message": error_message,
    }).execute()


def get_post_history(limit=20):
    """Include posted, failed, and rejected articles in history."""
    res = get_client().table("articles").select("*").in_(
        "status", ["posted", "failed", "rejected"]
    ).order("created_at", desc=True).limit(limit).execute()
    return res.data


# =================
# Facebook Pages
# =================

def get_facebook_pages(enabled_only=False):
    """Get all configured Facebook pages."""
    try:
        query = get_client().table("facebook_pages").select("*").order("page_name")
        if enabled_only:
            query = query.eq("enabled", True)
        res = query.execute()
        pages = res.data or []

        # If no pages in DB, fall back to env vars (single page legacy)
        if not pages:
            import config
            if config.FACEBOOK_PAGE_ID and config.META_PAGE_ACCESS_TOKEN:
                return [{
                    "id": 0,
                    "page_id": config.FACEBOOK_PAGE_ID,
                    "page_name": "Default Page",
                    "access_token": config.META_PAGE_ACCESS_TOKEN,
                    "enabled": True,
                }]
        return pages
    except Exception as e:
        logger.warning(f"get_facebook_pages: {e}")
        # Fall back to env
        import config
        if config.FACEBOOK_PAGE_ID and config.META_PAGE_ACCESS_TOKEN:
            return [{
                "id": 0,
                "page_id": config.FACEBOOK_PAGE_ID,
                "page_name": "Default Page",
                "access_token": config.META_PAGE_ACCESS_TOKEN,
                "enabled": True,
            }]
        return []


def add_facebook_page(page_id, page_name, access_token):
    get_client().table("facebook_pages").insert({
        "page_id": page_id,
        "page_name": page_name,
        "access_token": access_token,
        "enabled": True,
    }).execute()


def delete_facebook_page(row_id):
    get_client().table("facebook_pages").delete().eq("id", row_id).execute()


def toggle_facebook_page(row_id):
    page = get_client().table("facebook_pages").select("enabled").eq("id", row_id).execute()
    if page.data:
        current = page.data[0].get("enabled", True)
        get_client().table("facebook_pages").update({"enabled": not current}).eq("id", row_id).execute()


def get_daily_post_count(platform):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        res = get_client().table("post_log").select("id", count="exact").eq(
            "platform", platform
        ).eq("success", True).gte("posted_at", f"{today}T00:00:00").execute()
        return res.count or 0
    except Exception as e:
        logger.warning(f"Daily count failed: {e}")
        return 0
