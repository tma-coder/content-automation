import hashlib
from datetime import datetime, timezone
from supabase import create_client
import config

_client = None


def get_client():
    global _client
    if _client is None:
        _client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    return _client


def hash_url(url):
    return hashlib.sha256(url.encode()).hexdigest()


def article_exists(source_url):
    res = get_client().table("articles").select("id").eq("source_hash", hash_url(source_url)).execute()
    return len(res.data) > 0


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
    res = get_client().table("articles").insert(data).execute()
    return res.data[0]["id"] if res.data else None


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


def log_post(article_id, platform, success, post_id="", error_message=""):
    get_client().table("post_log").insert({
        "article_id": article_id,
        "platform": platform,
        "success": success,
        "post_id": post_id,
        "error_message": error_message,
    }).execute()


def get_post_history(limit=20):
    res = get_client().table("articles").select("*").in_("status", ["posted", "failed"]).order("created_at", desc=True).limit(limit).execute()
    return res.data


def get_daily_post_count(platform):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    res = get_client().table("post_log").select("id", count="exact").eq("platform", platform).eq("success", True).gte("posted_at", f"{today}T00:00:00").execute()
    return res.count or 0
