import os
import sys
import asyncio
import traceback
import logging
import hmac
import hashlib
import time
import base64
from typing import List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

from fastapi import FastAPI, Request, Form, Cookie, Depends, HTTPException, status
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


# =====================
# AUTHENTICATION
# =====================

SESSION_COOKIE = "ca_session"
SESSION_MAX_AGE = 7 * 24 * 3600  # 7 days

def _get_users():
    """Parse DASHBOARD_USERS env: 'email1@x.com:pass1,email2@x.com:pass2'.
    Email is case-insensitive."""
    import config
    users = {}
    for entry in config.DASHBOARD_USERS.split(","):
        if ":" in entry:
            u, p = entry.split(":", 1)
            users[u.strip().lower()] = p.strip()
    return users


def _sign(payload):
    import config
    sig = hmac.new(
        config.SESSION_SECRET.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}.{sig}"


def _verify(token):
    if not token or "." not in token:
        return None
    payload, _, sig = token.rpartition(".")
    expected = _sign(payload).rpartition(".")[2]
    if not hmac.compare_digest(sig, expected):
        return None
    # Parse payload: username|timestamp
    try:
        decoded = base64.urlsafe_b64decode(payload + "==").decode()
        username, ts = decoded.rsplit("|", 1)
        if int(time.time()) - int(ts) > SESSION_MAX_AGE:
            return None
        return username
    except Exception:
        return None


def _make_session(username):
    payload = base64.urlsafe_b64encode(f"{username}|{int(time.time())}".encode()).decode().rstrip("=")
    return _sign(payload)


def require_auth(ca_session: str = Cookie(None)):
    user = _verify(ca_session) if ca_session else None
    if not user:
        raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/login"})
    return user


# =====================
# LOGIN / LOGOUT
# =====================

@app.get("/login", response_class=HTMLResponse)
async def login_page(error: str = ""):
    return HTMLResponse(f"""
    <!DOCTYPE html><html><head><title>Sign In - Content Automation</title>
    <style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0f1117;color:#e1e4e8;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}}
    .card{{background:#1e2030;border:1px solid #2d3148;border-radius:14px;padding:36px;width:100%;max-width:380px;box-shadow:0 20px 60px rgba(0,0,0,.4)}}
    .logo{{width:48px;height:48px;background:linear-gradient(135deg,#667eea,#764ba2);border-radius:12px;margin:0 auto 16px;display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:bold;color:#fff}}
    h1{{font-size:22px;background:linear-gradient(135deg,#667eea,#764ba2);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:6px;text-align:center;font-weight:700}}
    .sub{{color:#8b8fa3;font-size:13px;text-align:center;margin-bottom:28px}}
    label{{font-size:11px;color:#8b8fa3;text-transform:uppercase;letter-spacing:1px;display:block;margin-bottom:6px;margin-top:16px;font-weight:600}}
    .input-wrap{{position:relative}}
    .input-icon{{position:absolute;left:14px;top:50%;transform:translateY(-50%);color:#5a5f7a;font-size:14px;pointer-events:none}}
    input{{width:100%;background:#0f1117;border:1px solid #2d3148;color:#e1e4e8;padding:12px 14px 12px 40px;border-radius:8px;font-size:14px;transition:border-color .15s}}
    input:focus{{outline:none;border-color:#667eea}}
    input::placeholder{{color:#5a5f7a}}
    button{{width:100%;margin-top:24px;padding:13px;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;transition:all .15s}}
    button:hover{{opacity:.9;transform:translateY(-1px)}}
    .err{{background:#7f1d1d;color:#fecaca;padding:10px 14px;border-radius:6px;font-size:12px;margin-top:16px;display:flex;align-items:center;gap:8px}}
    .footer{{text-align:center;color:#5a5f7a;font-size:11px;margin-top:24px}}
    </style></head><body>
    <div class="card">
    <div class="logo">CA</div>
    <h1>Content Automation</h1>
    <div class="sub">Sign in with your email to continue</div>
    <form method="post" action="/login">
    <label>Email address</label>
    <div class="input-wrap">
        <span class="input-icon">✉️</span>
        <input name="email" type="email" required autofocus placeholder="you@example.com" autocomplete="email">
    </div>
    <label>Password</label>
    <div class="input-wrap">
        <span class="input-icon">🔒</span>
        <input name="password" type="password" required placeholder="••••••••" autocomplete="current-password">
    </div>
    {"<div class='err'>⚠️ Invalid email or password</div>" if error else ""}
    <button type="submit">Sign In →</button>
    </form>
    <div class="footer">Secured by HMAC sessions · 7-day persistence</div>
    </div></body></html>
    """)


@app.post("/login")
async def login_submit(email: str = Form(...), password: str = Form(...)):
    users = _get_users()
    # Normalize email (case-insensitive)
    email_lower = email.strip().lower()
    if users.get(email_lower) == password:
        token = _make_session(email_lower)
        resp = RedirectResponse(url="/", status_code=303)
        resp.set_cookie(SESSION_COOKIE, token, max_age=SESSION_MAX_AGE, httponly=True, samesite="lax")
        return resp
    return RedirectResponse(url="/login?error=1", status_code=303)


@app.get("/logout")
async def logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


# =====================
# PUBLIC PAGES (no auth)
# =====================

@app.get("/privacy", response_class=HTMLResponse)
async def privacy_policy():
    return HTMLResponse("""
    <!DOCTYPE html><html><head><title>Privacy Policy</title>
    <style>body{font-family:sans-serif;max-width:800px;margin:40px auto;padding:20px;line-height:1.7;color:#222}
    h1{color:#1a1a2e}h2{margin-top:30px;color:#1a1a2e}</style></head><body>
    <h1>Privacy Policy</h1>
    <p><strong>Last updated:</strong> June 2026</p>
    <h2>Overview</h2>
    <p>Content Automation Bot is a personal automation tool that fetches public news articles and posts them to social media accounts owned by the operator.</p>
    <h2>Data Collection</h2>
    <p>We collect: public news articles, AI-generated content, posting history. We do NOT collect personal data from visitors or readers.</p>
    <h2>Third-Party Services</h2>
    <p>Meta Graph API, OpenRouter, Pollinations.ai, Hugging Face, Google News RSS.</p>
    <h2>Data Deletion</h2>
    <p>Contact the page operator to request data deletion.</p>
    <h2>Contact</h2>
    <p>Contact via the Facebook Page operator.</p>
    </body></html>
    """)


@app.get("/data-deletion", response_class=HTMLResponse)
async def data_deletion():
    return HTMLResponse("""
    <!DOCTYPE html><html><head><title>Data Deletion</title>
    <style>body{font-family:sans-serif;max-width:800px;margin:40px auto;padding:20px;line-height:1.7}</style>
    </head><body>
    <h1>Data Deletion Instructions</h1>
    <ol>
        <li>Contact the operator of the Facebook Page directly</li>
        <li>Include the specific post URL or content</li>
        <li>Data will be deleted within 30 days</li>
    </ol>
    </body></html>
    """)


@app.get("/health")
async def health():
    return {"status": "ok", "templates": os.path.exists(TEMPLATES_DIR), "root": ROOT}


# =====================
# PROTECTED ROUTES
# =====================

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, user: str = Depends(require_auth)):
    try:
        import db
        import config as cfg
        pending = db.get_pending_articles()
        history = db.get_post_history(limit=20)
        mode = "AUTO" if cfg.AUTO_MODE else "MANUAL"
        today = db.get_daily_post_count("facebook")
        topics = ", ".join(cfg.NEWS_TOPICS)
        pages = db.get_facebook_pages(enabled_only=True)
        return render(
            "index.html",
            pending=pending,
            history=history,
            mode=mode,
            posts_today=today,
            total_pending=len(pending),
            topics=topics,
            pages=pages,
            user=user,
        )
    except Exception as e:
        logger.exception("Dashboard error")
        return _error_html(e)


@app.post("/trigger")
async def trigger(topics: str = Form(""), user: str = Depends(require_auth)):
    try:
        import config as cfg
        from core.pipeline import run_cycle
        custom_topics = [t.strip() for t in topics.split(",") if t.strip()] if topics else None
        await asyncio.to_thread(run_cycle, auto=cfg.AUTO_MODE, topics=custom_topics)
    except Exception as e:
        logger.exception("Trigger error")
        return JSONResponse({"error": str(e), "trace": traceback.format_exc()}, status_code=500)
    return RedirectResponse(url="/", status_code=303)


@app.post("/approve/{article_id}")
async def approve(article_id: int, request: Request, user: str = Depends(require_auth)):
    try:
        form = await request.form()
        # Multi-select: page_ids may come as multiple values
        selected_pages = form.getlist("page_ids") if hasattr(form, "getlist") else []
        if not selected_pages:
            # Some implementations use .multi_items()
            try:
                selected_pages = [v for k, v in form.multi_items() if k == "page_ids"]
            except Exception:
                pass

        import db
        from core.pipeline import publish_article
        article = db.get_article(article_id)
        if not article:
            return JSONResponse({"error": "Article not found"}, status_code=404)
        if article["status"] != "pending":
            return RedirectResponse(url="/", status_code=303)

        db.update_article_status(article_id, "approved")
        await asyncio.to_thread(publish_article, article_id, selected_pages or None)
    except Exception as e:
        logger.exception("Approve error")
        return JSONResponse({"error": str(e), "trace": traceback.format_exc()}, status_code=500)
    return RedirectResponse(url="/", status_code=303)


@app.post("/reject/{article_id}")
async def reject(article_id: int, user: str = Depends(require_auth)):
    try:
        import db
        db.update_article_status(article_id, "rejected")
    except Exception as e:
        logger.exception("Reject error")
        return JSONResponse({"error": str(e)}, status_code=500)
    return RedirectResponse(url="/", status_code=303)


@app.post("/regenerate-image/{article_id}")
async def regenerate_image_route(article_id: int, user: str = Depends(require_auth)):
    try:
        import db
        from core.image_generator import regenerate_image
        article = db.get_article(article_id)
        if not article:
            return JSONResponse({"error": "Article not found"}, status_code=404)

        title = article["generated_title"]
        words = title.split()
        phrases = []
        if len(words) >= 4:
            phrases.append(" ".join(words[:4]))
        if ":" in title:
            after_colon = title.split(":", 1)[1].strip()
            if after_colon:
                phrases.append(after_colon)

        import re
        names = re.findall(r'\b([A-Z][a-z]+ [A-Z][a-z]+)\b', title)
        skip = {"United States", "White House", "Wall Street", "New York", "San Francisco", "Los Angeles"}
        names = [n for n in names if n not in skip]

        new_url = await asyncio.to_thread(
            regenerate_image, title,
            subject="", highlight_phrases=phrases, people=names
        )
        if new_url:
            db.update_image(article_id, new_url)
    except Exception as e:
        logger.exception("Regenerate image error")
        return JSONResponse({"error": str(e)}, status_code=500)
    return RedirectResponse(url="/", status_code=303)


@app.post("/delete/{article_id}")
async def delete_article(article_id: int, user: str = Depends(require_auth)):
    try:
        import db
        db.delete_article(article_id)
    except Exception as e:
        logger.exception("Delete error")
        return JSONResponse({"error": str(e)}, status_code=500)
    return RedirectResponse(url="/", status_code=303)


@app.post("/clear-history")
async def clear_history(user: str = Depends(require_auth)):
    try:
        import db
        db.clear_history()
    except Exception as e:
        logger.exception("Clear history error")
        return JSONResponse({"error": str(e)}, status_code=500)
    return RedirectResponse(url="/", status_code=303)


@app.get("/article/{article_id}", response_class=HTMLResponse)
async def view_article(request: Request, article_id: int, user: str = Depends(require_auth)):
    try:
        import db
        article = db.get_article(article_id)
        if not article:
            return HTMLResponse("Not found", status_code=404)
        pages = db.get_facebook_pages(enabled_only=True)
        return render("article.html", article=article, pages=pages)
    except Exception as e:
        logger.exception("View article error")
        return _error_html(e)


# =====================
# FACEBOOK PAGES
# =====================

@app.get("/pages", response_class=HTMLResponse)
async def pages_view(user: str = Depends(require_auth)):
    import db
    pages = db.get_facebook_pages()
    rows = ""
    for p in pages:
        is_env = p.get("id") == 0
        rows += f"""
        <tr>
            <td>{p.get('page_name', '')}</td>
            <td><code>{p.get('page_id', '')}</code></td>
            <td>{'✅ Enabled' if p.get('enabled') else '❌ Disabled'}</td>
            <td>{'<span style="color:#8b8fa3;font-size:11px">From env vars</span>' if is_env else f'''
                <form method="post" action="/pages/toggle/{p['id']}" class="inline"><button class="btn btn-sm btn-ghost">Toggle</button></form>
                <form method="post" action="/pages/delete/{p['id']}" class="inline" onsubmit="return confirm('Delete this page?')"><button class="btn btn-sm btn-danger">Delete</button></form>
            '''}</td>
        </tr>
        """
    return HTMLResponse(f"""
    <!DOCTYPE html><html><head><title>Facebook Pages</title>
    <style>
    *{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0f1117;color:#e1e4e8;min-height:100vh}}
    .header{{background:linear-gradient(135deg,#1a1d29,#252836);border-bottom:1px solid #2d3148;padding:16px 30px;display:flex;justify-content:space-between;align-items:center}}
    a{{color:#667eea;text-decoration:none}}
    .container{{max-width:900px;margin:0 auto;padding:30px 20px}}
    h2{{margin-bottom:16px}}
    table{{width:100%;border-collapse:collapse;background:#1e2030;border-radius:8px;overflow:hidden;margin-bottom:30px}}
    th{{text-align:left;padding:12px;font-size:12px;color:#8b8fa3;text-transform:uppercase;border-bottom:1px solid #2d3148;background:#252836}}
    td{{padding:14px 12px;border-bottom:1px solid #1a1d29;font-size:13px;vertical-align:middle}}
    code{{background:#0f1117;padding:2px 6px;border-radius:4px;font-size:11px}}
    .card{{background:#1e2030;border:1px solid #2d3148;border-radius:10px;padding:24px}}
    label{{display:block;font-size:11px;color:#8b8fa3;text-transform:uppercase;margin:14px 0 6px}}
    input{{width:100%;background:#0f1117;border:1px solid #2d3148;color:#e1e4e8;padding:10px;border-radius:6px;font-size:13px}}
    input:focus{{outline:none;border-color:#667eea}}
    .btn{{padding:8px 16px;border:none;border-radius:6px;font-size:13px;font-weight:600;cursor:pointer;display:inline-block;margin-top:4px}}
    .btn-sm{{padding:4px 10px;font-size:11px}}
    .btn-primary{{background:linear-gradient(135deg,#667eea,#764ba2);color:#fff}}
    .btn-danger{{background:#dc2626;color:#fff}}
    .btn-ghost{{background:transparent;border:1px solid #2d3148;color:#8b8fa3}}
    form.inline{{display:inline}}
    .help{{color:#8b8fa3;font-size:12px;margin-top:6px;line-height:1.5}}
    .help a{{color:#667eea}}
    </style></head><body>
    <div class="header"><h1 style="font-size:18px"><a href="/">← Dashboard</a> &nbsp; / &nbsp; Facebook Pages</h1>
    <a href="/logout" style="font-size:13px;color:#8b8fa3">Logout</a></div>
    <div class="container">
    <h2>📘 Connected Pages</h2>
    <table>
    <thead><tr><th>Name</th><th>Page ID</th><th>Status</th><th>Actions</th></tr></thead>
    <tbody>{rows or '<tr><td colspan="4" style="text-align:center;color:#5a5f7a;padding:30px">No pages added yet</td></tr>'}</tbody>
    </table>

    <h2>➕ Add New Page</h2>
    <div class="card">
    <form method="post" action="/pages/add">
    <label>Page Name</label>
    <input name="page_name" placeholder="e.g. Tech News Channel" required>

    <label>Page ID</label>
    <input name="page_id" placeholder="e.g. 104075216017794" required>

    <label>Page Access Token (Long-lived)</label>
    <input name="access_token" placeholder="EAAU..." required>
    <div class="help">Get from <a href="https://developers.facebook.com/tools/explorer/" target="_blank">Graph API Explorer</a>. Select your app → Get User Token with pages_manage_posts → switch dropdown to your Page → copy token.</div>

    <button class="btn btn-primary" type="submit">Add Page</button>
    </form>
    </div>
    </div></body></html>
    """)


@app.post("/pages/add")
async def pages_add(page_name: str = Form(...), page_id: str = Form(...), access_token: str = Form(...), user: str = Depends(require_auth)):
    import db
    try:
        db.add_facebook_page(page_id.strip(), page_name.strip(), access_token.strip())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    return RedirectResponse(url="/pages", status_code=303)


@app.post("/pages/delete/{row_id}")
async def pages_delete(row_id: int, user: str = Depends(require_auth)):
    import db
    db.delete_facebook_page(row_id)
    return RedirectResponse(url="/pages", status_code=303)


@app.post("/pages/toggle/{row_id}")
async def pages_toggle(row_id: int, user: str = Depends(require_auth)):
    import db
    db.toggle_facebook_page(row_id)
    return RedirectResponse(url="/pages", status_code=303)


# =====================
# DEBUG / CRON / TEST
# =====================

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


@app.get("/test-image")
async def test_image(
    title: str = "Trump and Sanders agree on AI tax policy",
    subject: str = "politicians discussing policy",
    highlights: str = "Trump and Sanders|AI tax",
    people: str = "Donald Trump|Bernie Sanders",
    user: str = Depends(require_auth),
):
    try:
        from core.image_generator import generate_image, get_debug
        import time as t

        highlight_list = [h.strip() for h in highlights.split("|") if h.strip()]
        people_list = [p.strip() for p in people.split("|") if p.strip()]

        start = t.time()
        url = await asyncio.to_thread(generate_image, title, "", subject, highlight_list, people_list)
        elapsed = t.time() - start

        debug = get_debug()
        bg_source = debug.get("bg_source", "Unknown")

        debug_html = "<br>".join([f"<b>{k}:</b> {v}" for k, v in debug.items()])

        return HTMLResponse(f"""
        <!DOCTYPE html><html><head><title>Image Test</title>
        <style>body{{background:#0f1117;color:#e1e4e8;font-family:sans-serif;padding:20px;max-width:900px;margin:0 auto}}
        img{{max-width:600px;border:1px solid #2d3148;border-radius:8px;margin-top:20px;display:block}}
        code{{background:#1e2030;padding:8px;border-radius:4px;font-size:11px;display:block;word-break:break-all;margin:8px 0}}
        a{{color:#667eea}}.debug{{background:#0d1019;padding:12px;border-radius:8px;margin:12px 0;font-size:11px;font-family:monospace;line-height:1.7;color:#fbbf24}}</style></head><body>
        <h2>🖼️ Image Test (logged in as {user})</h2>
        <p><b>Source:</b> {bg_source} | <b>Time:</b> {elapsed:.2f}s</p>
        <div class="debug"><b style="color:#667eea">DEBUG:</b><br>{debug_html}</div>
        <code>{url}</code>
        <img src="{url}">
        <p><a href="/">← Dashboard</a></p>
        </body></html>
        """)
    except Exception as e:
        return HTMLResponse(f"<pre>Error: {e}\n{traceback.format_exc()}</pre>", status_code=500)


@app.get("/diagnose")
async def diagnose(user: str = Depends(require_auth)):
    results = {}
    try:
        import config as cfg
        results["env"] = {
            "SUPABASE_URL": bool(cfg.SUPABASE_URL),
            "SUPABASE_KEY": bool(cfg.SUPABASE_KEY),
            "OPENROUTER_API_KEY": bool(cfg.OPENROUTER_API_KEY),
            "OPENROUTER_IMAGE_API_KEY": bool(cfg.OPENROUTER_IMAGE_API_KEY),
            "POLLINATIONS_API_KEY": bool(cfg.POLLINATIONS_API_KEY),
            "HUGGINGFACE_API_KEY": bool(cfg.HUGGINGFACE_API_KEY),
            "META_PAGE_ACCESS_TOKEN": bool(cfg.META_PAGE_ACCESS_TOKEN),
            "FACEBOOK_PAGE_ID": bool(cfg.FACEBOOK_PAGE_ID),
            "SESSION_SECRET_set": cfg.SESSION_SECRET != "change-me-please-use-a-random-string",
        }
    except Exception as e:
        results["env"] = {"error": str(e)}

    try:
        import db
        results["supabase"] = {"ok": True, "pending": len(db.get_pending_articles()), "fb_pages": len(db.get_facebook_pages())}
    except Exception as e:
        results["supabase"] = {"ok": False, "error": str(e)}

    return results
