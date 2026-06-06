import os
import sys
import asyncio
import traceback
import logging

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Set up logging to capture errors
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

app = FastAPI()

TEMPLATES_DIR = os.path.join(ROOT, "templates")
jinja_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    auto_reload=False,
    cache_size=0,
    autoescape=select_autoescape(["html"]),
)


def render(name, **ctx):
    return HTMLResponse(jinja_env.get_template(name).render(**ctx))


def _error_html(e):
    return HTMLResponse(
        f"<pre style='color:red;padding:20px;font-family:monospace'>Error: {e}\n\n{traceback.format_exc()}</pre>",
        status_code=500,
    )


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    try:
        import db
        import config as cfg
        pending = db.get_pending_articles()
        history = db.get_post_history(limit=20)
        mode = "AUTO" if cfg.AUTO_MODE else "MANUAL"
        today = db.get_daily_post_count("facebook")
        topics = ", ".join(cfg.NEWS_TOPICS)
        return render(
            "index.html",
            pending=pending,
            history=history,
            mode=mode,
            posts_today=today,
            total_pending=len(pending),
            topics=topics,
        )
    except Exception as e:
        logger.exception("Dashboard error")
        return _error_html(e)


@app.post("/trigger")
async def trigger(topics: str = Form("")):
    try:
        import config as cfg
        from core.pipeline import run_cycle
        custom_topics = [t.strip() for t in topics.split(",") if t.strip()] if topics else None
        await asyncio.to_thread(run_cycle, auto=cfg.AUTO_MODE, topics=custom_topics)
    except Exception as e:
        logger.exception("Trigger error")
        return JSONResponse(
            {"error": str(e), "trace": traceback.format_exc()},
            status_code=500,
        )
    return RedirectResponse(url="/", status_code=303)


@app.post("/approve/{article_id}")
async def approve(article_id: int):
    try:
        import db
        from core.pipeline import publish_article
        article = db.get_article(article_id)
        if not article:
            return JSONResponse({"error": "Article not found"}, status_code=404)
        if article["status"] != "pending":
            return RedirectResponse(url="/", status_code=303)

        db.update_article_status(article_id, "approved")
        await asyncio.to_thread(publish_article, article_id)
    except Exception as e:
        logger.exception("Approve error")
        return JSONResponse({"error": str(e), "trace": traceback.format_exc()}, status_code=500)
    return RedirectResponse(url="/", status_code=303)


@app.post("/reject/{article_id}")
async def reject(article_id: int):
    try:
        import db
        db.update_article_status(article_id, "rejected")
    except Exception as e:
        logger.exception("Reject error")
        return JSONResponse({"error": str(e)}, status_code=500)
    return RedirectResponse(url="/", status_code=303)


@app.post("/regenerate-image/{article_id}")
async def regenerate_image_route(article_id: int):
    try:
        import db
        from core.image_generator import regenerate_image
        article = db.get_article(article_id)
        if not article:
            return JSONResponse({"error": "Article not found"}, status_code=404)
        new_url = await asyncio.to_thread(regenerate_image, article["generated_title"])
        if new_url:
            db.update_image(article_id, new_url)
    except Exception as e:
        logger.exception("Regenerate image error")
        return JSONResponse({"error": str(e)}, status_code=500)
    return RedirectResponse(url="/", status_code=303)


@app.post("/delete/{article_id}")
async def delete_article(article_id: int):
    try:
        import db
        db.delete_article(article_id)
    except Exception as e:
        logger.exception("Delete error")
        return JSONResponse({"error": str(e)}, status_code=500)
    return RedirectResponse(url="/", status_code=303)


@app.post("/clear-history")
async def clear_history():
    try:
        import db
        db.clear_history()
    except Exception as e:
        logger.exception("Clear history error")
        return JSONResponse({"error": str(e)}, status_code=500)
    return RedirectResponse(url="/", status_code=303)


@app.get("/article/{article_id}", response_class=HTMLResponse)
async def view_article(request: Request, article_id: int):
    try:
        import db
        article = db.get_article(article_id)
        if not article:
            return HTMLResponse("Not found", status_code=404)
        return render("article.html", article=article)
    except Exception as e:
        logger.exception("View article error")
        return _error_html(e)


@app.get("/api/cron")
async def cron(request: Request):
    try:
        import config as cfg
        from core.pipeline import run_cycle
        ids = await asyncio.to_thread(run_cycle, auto=cfg.AUTO_MODE)
        return {"processed": len(ids), "article_ids": ids}
    except Exception as e:
        logger.exception("Cron error")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/health")
async def health():
    return {"status": "ok", "templates": os.path.exists(TEMPLATES_DIR), "root": ROOT}


@app.get("/diagnose")
async def diagnose():
    results = {}
    try:
        import config as cfg
        results["env"] = {
            "SUPABASE_URL": bool(cfg.SUPABASE_URL),
            "SUPABASE_KEY": bool(cfg.SUPABASE_KEY),
            "OPENROUTER_API_KEY": bool(cfg.OPENROUTER_API_KEY),
            "POLLINATIONS_API_KEY": bool(cfg.POLLINATIONS_API_KEY),
            "META_PAGE_ACCESS_TOKEN": bool(cfg.META_PAGE_ACCESS_TOKEN),
            "FACEBOOK_PAGE_ID": bool(cfg.FACEBOOK_PAGE_ID),
        }
    except Exception as e:
        results["env"] = {"error": str(e)}

    try:
        import db
        pending = db.get_pending_articles()
        results["supabase"] = {"ok": True, "pending_count": len(pending)}
    except Exception as e:
        results["supabase"] = {"ok": False, "error": str(e)}

    try:
        from core.news_monitor import fetch_news
        items = fetch_news("technology", max_items=1)
        results["news_rss"] = {"ok": True, "items": len(items)}
    except Exception as e:
        results["news_rss"] = {"ok": False, "error": str(e)}

    try:
        import config as cfg
        from openai import OpenAI
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=cfg.OPENROUTER_API_KEY)
        resp = client.chat.completions.create(
            model="google/gemini-3.5-flash:free",
            messages=[{"role": "user", "content": "Say hello in 5 words"}],
            max_tokens=20,
        )
        content = resp.choices[0].message.content if resp.choices else ""
        results["openrouter"] = {"ok": True, "response": (content or "")[:50]}
    except Exception as e:
        results["openrouter"] = {"ok": False, "error": str(e)}

    try:
        from core.image_generator import generate_image
        url = generate_image("Test news article about technology")
        results["image_gen"] = {"ok": bool(url), "url": url[:120] if url else ""}
    except Exception as e:
        results["image_gen"] = {"ok": False, "error": str(e)}

    return results
