import os
import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import db
import config
from core.pipeline import run_cycle, publish_article
from scheduler.jobs import is_auto_mode, toggle_mode

app = FastAPI(title="Content Automation")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

os.makedirs(config.STORAGE_DIR, exist_ok=True)
app.mount("/images", StaticFiles(directory=config.STORAGE_DIR), name="images")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    pending = db.get_pending_articles()
    history = db.get_post_history(limit=20)
    mode = "AUTO" if is_auto_mode() else "MANUAL"
    today = db.get_daily_post_count("facebook")
    return templates.TemplateResponse("index.html", {
        "request": request, "pending": pending, "history": history,
        "mode": mode, "posts_today": today, "total_pending": len(pending),
    })


@app.post("/trigger")
async def trigger(request: Request):
    await asyncio.to_thread(run_cycle, auto=is_auto_mode())
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


@app.post("/toggle")
async def toggle():
    toggle_mode()
    return RedirectResponse(url="/", status_code=303)


@app.get("/article/{article_id}", response_class=HTMLResponse)
async def view_article(request: Request, article_id: int):
    article = db.get_article(article_id)
    if not article:
        return HTMLResponse("Not found", status_code=404)
    return templates.TemplateResponse("article.html", {"request": request, "article": article})
