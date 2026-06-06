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
