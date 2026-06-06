import os
import sys
import asyncio
import traceback

# Add project root to path for imports
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader

app = FastAPI()

TEMPLATES_DIR = os.path.join(ROOT, "templates")
jinja_env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), auto_reload=False, cache_size=0)


def render(name, **ctx):
    return HTMLResponse(jinja_env.get_template(name).render(**ctx))


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    try:
        import db
        import config
        pending = db.get_pending_articles()
        history = db.get_post_history(limit=20)
        mode = "AUTO" if config.AUTO_MODE else "MANUAL"
        today = db.get_daily_post_count("facebook")
        return render("index.html", pending=pending, history=history,
                      mode=mode, posts_today=today, total_pending=len(pending))
    except Exception as e:
        return HTMLResponse(f"<pre>Error: {e}\n\n{traceback.format_exc()}</pre>", status_code=500)


@app.post("/trigger")
async def trigger():
    try:
        import config
        from core.pipeline import run_cycle
        await asyncio.to_thread(run_cycle, auto=config.AUTO_MODE)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    return RedirectResponse(url="/", status_code=303)


@app.post("/approve/{article_id}")
async def approve(article_id: int):
    try:
        import db
        from core.pipeline import publish_article
        article = db.get_article(article_id)
        if article and article["status"] == "pending":
            db.update_article_status(article_id, "approved")
            await asyncio.to_thread(publish_article, article_id)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    return RedirectResponse(url="/", status_code=303)


@app.post("/reject/{article_id}")
async def reject(article_id: int):
    import db
    db.update_article_status(article_id, "rejected")
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
        return HTMLResponse(f"<pre>Error: {e}\n\n{traceback.format_exc()}</pre>", status_code=500)


@app.get("/api/cron")
async def cron(request: Request):
    try:
        import config
        from core.pipeline import run_cycle
        ids = await asyncio.to_thread(run_cycle, auto=config.AUTO_MODE)
        return {"processed": len(ids), "article_ids": ids}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/health")
async def health():
    return {"status": "ok", "templates": os.path.exists(TEMPLATES_DIR), "root": ROOT}


@app.get("/diagnose")
async def diagnose():
    results = {}

    # 1. Check env vars
    import config
    results["env"] = {
        "SUPABASE_URL": bool(config.SUPABASE_URL),
        "SUPABASE_KEY": bool(config.SUPABASE_KEY),
        "OPENROUTER_API_KEY": bool(config.OPENROUTER_API_KEY),
        "META_PAGE_ACCESS_TOKEN": bool(config.META_PAGE_ACCESS_TOKEN),
        "FACEBOOK_PAGE_ID": bool(config.FACEBOOK_PAGE_ID),
    }

    # 2. Test Supabase connection
    try:
        import db
        pending = db.get_pending_articles()
        results["supabase"] = {"ok": True, "pending_count": len(pending)}
    except Exception as e:
        results["supabase"] = {"ok": False, "error": str(e)}

    # 3. Test Google News RSS
    try:
        from core.news_monitor import fetch_news
        items = fetch_news("technology", max_items=1)
        results["news_rss"] = {"ok": True, "items": len(items)}
    except Exception as e:
        results["news_rss"] = {"ok": False, "error": str(e)}

    # 4. Test OpenRouter API
    try:
        from openai import OpenAI
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=config.OPENROUTER_API_KEY)
        resp = client.chat.completions.create(
            model="google/gemini-3.5-flash:free",
            messages=[{"role": "user", "content": "Say hello in 5 words"}],
            max_tokens=20,
        )
        results["openrouter"] = {"ok": True, "response": resp.choices[0].message.content[:50]}
    except Exception as e:
        results["openrouter"] = {"ok": False, "error": str(e)}

    return results
