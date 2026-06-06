import os
import sys
import asyncio

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import db
import config
from core.pipeline import run_cycle, publish_article

app = FastAPI()

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    pending = db.get_pending_articles()
    history = db.get_post_history(limit=20)
    mode = "AUTO" if config.AUTO_MODE else "MANUAL"
    today = db.get_daily_post_count("facebook")
    return templates.TemplateResponse("index.html", {
        "request": request, "pending": pending, "history": history,
        "mode": mode, "posts_today": today, "total_pending": len(pending),
    })


@app.post("/trigger")
async def trigger():
    await asyncio.to_thread(run_cycle, auto=config.AUTO_MODE)
    return RedirectResponse(url="/", status_code=303)


@app.post("/approve/{article_id}")
async def approve(article_id: int):
    article = db.get_article(article_id)
    if article and article["status"] == "pending":
        db.update_article_status(article_id, "approved")
        await asyncio.to_thread(publish_article, article_id)
    return RedirectResponse(url="/", status_code=303)


@app.post("/reject/{article_id}")
async def reject(article_id: int):
    db.update_article_status(article_id, "rejected")
    return RedirectResponse(url="/", status_code=303)


@app.get("/article/{article_id}", response_class=HTMLResponse)
async def view_article(request: Request, article_id: int):
    article = db.get_article(article_id)
    if not article:
        return HTMLResponse("Not found", status_code=404)
    return templates.TemplateResponse("article.html", {"request": request, "article": article})


@app.get("/api/cron")
async def cron(request: Request):
    secret = request.headers.get("authorization", "")
    if config.CRON_SECRET and secret != f"Bearer {config.CRON_SECRET}":
        return {"error": "unauthorized"}
    ids = await asyncio.to_thread(run_cycle, auto=config.AUTO_MODE)
    return {"processed": len(ids), "article_ids": ids}
