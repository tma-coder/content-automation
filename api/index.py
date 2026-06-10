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


# =====================
# SHARED UI HELPERS (theme + nav)
# =====================

def _theme_css():
    return """
    <style>
    :root{
        --bg:#0a0d14; --surface:#11151f; --surface-2:#161b27; --surface-3:#1c2230;
        --border:#252b3d; --border-strong:#363d52;
        --primary:#6366f1; --primary-2:#8b5cf6; --primary-glow:rgba(99,102,241,.4);
        --success:#10b981; --warning:#f59e0b; --danger:#ef4444; --info:#3b82f6;
        --text:#e5e7eb; --text-2:#9ca3af; --text-3:#6b7280; --text-muted:#4b5563;
    }
    *{margin:0;padding:0;box-sizing:border-box}
    html{font-size:14px}
    body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','SF Pro Display',Roboto,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;line-height:1.5;-webkit-font-smoothing:antialiased}
    a{color:var(--primary);text-decoration:none;transition:color .15s}
    a:hover{color:var(--primary-2)}
    code{background:var(--surface);padding:2px 7px;border-radius:5px;font-size:12px;font-family:'JetBrains Mono','SF Mono',Consolas,monospace;color:var(--text-2)}

    /* Navigation */
    .nav{position:sticky;top:0;background:rgba(10,13,20,.85);backdrop-filter:blur(20px);border-bottom:1px solid var(--border);z-index:50;padding:14px 32px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px}
    .nav-left{display:flex;align-items:center;gap:24px}
    .brand{display:flex;align-items:center;gap:10px;font-weight:700;font-size:15px;color:var(--text)}
    .brand-icon{width:32px;height:32px;background:linear-gradient(135deg,var(--primary),var(--primary-2));border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:800;color:#fff}
    .nav-tabs{display:flex;gap:4px}
    .nav-tab{padding:8px 14px;border-radius:7px;color:var(--text-2);font-size:13px;font-weight:500;transition:all .15s}
    .nav-tab:hover{background:var(--surface);color:var(--text)}
    .nav-tab.active{background:var(--surface-2);color:var(--text)}
    .nav-right{display:flex;align-items:center;gap:10px}

    /* User chip & badges */
    .user-chip{display:flex;align-items:center;gap:8px;padding:6px 12px;background:var(--surface);border:1px solid var(--border);border-radius:20px;font-size:12px;color:var(--text-2)}
    .avatar{width:24px;height:24px;border-radius:50%;background:linear-gradient(135deg,var(--primary),var(--primary-2));color:#fff;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700}
    .role-tag{padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700;letter-spacing:.5px;text-transform:uppercase}
    .role-admin{background:rgba(99,102,241,.15);color:#a5b4fc}
    .role-moderator{background:rgba(245,158,11,.15);color:#fcd34d}
    .badge{padding:4px 10px;border-radius:14px;font-size:11px;font-weight:600;display:inline-flex;align-items:center;gap:4px}
    .badge-success{background:rgba(16,185,129,.15);color:var(--success)}
    .badge-info{background:rgba(59,130,246,.15);color:var(--info)}
    .badge-warning{background:rgba(245,158,11,.15);color:var(--warning)}
    .badge-muted{background:var(--surface-2);color:var(--text-3)}
    .badge-auto{background:rgba(16,185,129,.15);color:var(--success);border:1px solid rgba(16,185,129,.3)}
    .badge-manual{background:rgba(245,158,11,.15);color:var(--warning);border:1px solid rgba(245,158,11,.3)}

    /* Main layout */
    .main-wrap{max-width:1280px;margin:0 auto;padding:28px 32px 60px}
    @media(max-width:768px){.main-wrap,.nav{padding-left:18px;padding-right:18px}}

    /* Sections */
    .section{margin-bottom:36px}
    .section-header{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;margin-bottom:18px;flex-wrap:wrap}
    .section-header h1{font-size:22px;font-weight:700;color:var(--text);margin-bottom:4px}
    .section-header h2{font-size:18px;font-weight:600;color:var(--text);margin-bottom:4px}
    .section-sub{color:var(--text-2);font-size:13px;max-width:600px}

    /* Cards */
    .card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:20px}
    .card-flush{padding:0;overflow:hidden}
    .card:hover{border-color:var(--border-strong)}

    /* Stats */
    .stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:28px}
    .stat-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:18px 20px;transition:transform .15s,border-color .15s}
    .stat-card:hover{border-color:var(--primary);transform:translateY(-2px)}
    .stat-label{font-size:11px;color:var(--text-3);text-transform:uppercase;letter-spacing:1px;font-weight:600}
    .stat-value{font-size:28px;font-weight:700;margin-top:6px;line-height:1}
    .stat-icon{font-size:18px;margin-bottom:8px;opacity:.8}
    .v-pending{color:var(--warning)}.v-posted{color:var(--success)}.v-info{color:var(--info)}.v-primary{color:#a5b4fc}

    /* Buttons */
    .btn{padding:9px 16px;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;transition:all .15s;text-decoration:none;display:inline-flex;align-items:center;gap:6px;font-family:inherit;line-height:1}
    .btn:hover{transform:translateY(-1px)}
    .btn-primary{background:linear-gradient(135deg,var(--primary),var(--primary-2));color:#fff;box-shadow:0 4px 12px var(--primary-glow)}
    .btn-primary:hover{box-shadow:0 6px 18px var(--primary-glow)}
    .btn-success{background:var(--success);color:#fff}
    .btn-danger{background:var(--danger);color:#fff}
    .btn-ghost{background:transparent;border:1px solid var(--border-strong);color:var(--text-2)}
    .btn-ghost:hover{background:var(--surface);color:var(--text);border-color:var(--primary)}
    .btn-sm{padding:6px 12px;font-size:12px}
    .btn-icon{padding:8px;width:32px;height:32px;justify-content:center}

    /* Inputs */
    .form-group{margin-bottom:18px}
    .label-row{display:flex;justify-content:space-between;align-items:center;margin-bottom:7px}
    label{font-size:12px;color:var(--text-2);font-weight:600;display:block}
    .required{color:var(--danger)}
    .optional{color:var(--text-3);font-weight:400;font-size:11px}
    input,textarea,select{width:100%;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:11px 14px;border-radius:8px;font-size:13px;font-family:inherit;transition:border-color .15s,background .15s}
    input:focus,textarea:focus,select:focus{outline:none;border-color:var(--primary);background:var(--surface)}
    input::placeholder{color:var(--text-3)}
    .form-actions{display:flex;gap:10px;margin-top:8px}

    /* Help text */
    .help-btn{background:var(--surface-2);border:1px solid var(--border);color:var(--text-3);padding:4px 10px;border-radius:6px;font-size:11px;cursor:pointer;font-family:inherit;transition:all .15s}
    .help-btn:hover{background:var(--surface-3);color:var(--text-2)}
    .help-text{display:none;background:var(--surface-2);border:1px solid var(--border);border-left:3px solid var(--primary);border-radius:6px;padding:14px 16px;margin-top:8px;font-size:12px;color:var(--text-2);line-height:1.7}
    .help-text ol{padding-left:18px;margin:6px 0}
    .help-text strong{color:var(--text)}
    .help-text code{font-size:11px}
    .help-text em{color:var(--text-3);font-style:normal;display:block;margin-top:8px}

    /* Tables */
    .data-table{width:100%;border-collapse:collapse;font-size:13px}
    .data-table th{text-align:left;padding:14px 18px;font-size:11px;color:var(--text-3);text-transform:uppercase;letter-spacing:1px;font-weight:600;background:var(--surface-2);border-bottom:1px solid var(--border)}
    .data-table td{padding:14px 18px;border-bottom:1px solid var(--border)}
    .data-table tr:last-child td{border-bottom:none}
    .data-table tr:hover{background:var(--surface-2)}
    .empty-cell{text-align:center;color:var(--text-3);padding:48px 16px;font-size:13px}
    .muted{color:var(--text-3);font-size:11px}
    .page-name{font-weight:600;color:var(--text)}
    .page-id{font-size:11px}

    /* Alerts */
    .alert{padding:12px 16px;border-radius:8px;margin-bottom:18px;font-size:13px;display:flex;align-items:center;gap:10px}
    .alert-success{background:rgba(16,185,129,.1);border:1px solid rgba(16,185,129,.3);color:#86efac}
    .alert-warning{background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.3);color:#fcd34d}
    .alert-danger{background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);color:#fca5a5}
    .alert-info{background:rgba(59,130,246,.1);border:1px solid rgba(59,130,246,.3);color:#93c5fd}

    /* Cards grid */
    .card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:18px}
    .article-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;overflow:hidden;transition:all .15s}
    .article-card:hover{border-color:var(--primary);transform:translateY(-2px)}
    .article-img-wrap{position:relative;height:170px;background:var(--surface-2);overflow:hidden}
    .article-img{width:100%;height:170px;object-fit:cover;display:block;background:var(--surface-2)}
    .img-actions{position:absolute;top:8px;right:8px;display:flex;gap:6px}
    .img-btn{background:rgba(0,0,0,.7);backdrop-filter:blur(4px);color:#fff;border:none;padding:5px 10px;border-radius:6px;font-size:11px;cursor:pointer;font-family:inherit;font-weight:500;transition:background .15s}
    .img-btn:hover{background:rgba(0,0,0,.9)}
    .article-body{padding:14px 16px 16px}
    .article-title{font-size:14px;font-weight:600;line-height:1.35;margin-bottom:6px;color:var(--text);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
    .article-summary{font-size:12px;color:var(--text-2);line-height:1.5;margin-bottom:10px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
    .article-tags{font-size:11px;color:var(--primary);margin-bottom:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .article-meta{font-size:10px;color:var(--text-3);line-height:1.7;padding-top:10px;border-top:1px solid var(--border);margin-bottom:12px}
    .article-actions{display:flex;gap:6px;flex-wrap:wrap}

    /* Topic chips */
    .topic-chips{display:flex;gap:6px;flex-wrap:wrap}
    .chip{background:var(--surface-2);color:var(--text-2);border:1px solid var(--border);padding:5px 11px;border-radius:14px;font-size:11px;cursor:pointer;transition:all .15s;font-family:inherit}
    .chip:hover{background:var(--primary);color:#fff;border-color:var(--primary)}

    /* Loading overlay */
    .loading-overlay{display:none;position:fixed;inset:0;background:rgba(10,13,20,.85);backdrop-filter:blur(10px);z-index:999;align-items:center;justify-content:center;flex-direction:column;gap:14px}
    .loading-overlay.active{display:flex}
    .spinner{width:40px;height:40px;border:3px solid var(--border);border-top-color:var(--primary);border-radius:50%;animation:spin .8s linear infinite}
    @keyframes spin{to{transform:rotate(360deg)}}

    /* Status pill */
    .status{padding:3px 10px;border-radius:5px;font-size:10px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;display:inline-block}
    .s-posted{background:rgba(16,185,129,.15);color:var(--success)}
    .s-pending{background:rgba(245,158,11,.15);color:var(--warning)}
    .s-failed{background:rgba(239,68,68,.15);color:var(--danger)}
    .s-rejected{background:var(--surface-2);color:var(--text-3)}
    .s-approved{background:rgba(16,185,129,.15);color:var(--success)}

    form.inline{display:inline}
    </style>
    """


def _nav(user, active=""):
    role = user.get("role", "moderator")
    email = user.get("email", "")
    initial = email[0].upper() if email else "U"
    role_label = role.upper()

    admin_tabs = ""
    if role == "admin":
        admin_tabs = f'<a href="/pages" class="nav-tab {"active" if active == "pages" else ""}">Pages</a>'

    return f"""
    <nav class="nav">
        <div class="nav-left">
            <a href="/" class="brand">
                <span class="brand-icon">CA</span>
                <span>Content Automation</span>
            </a>
            <div class="nav-tabs">
                <a href="/" class="nav-tab {'active' if active == 'dashboard' else ''}">Dashboard</a>
                {admin_tabs}
            </div>
        </div>
        <div class="nav-right">
            <div class="user-chip">
                <div class="avatar">{initial}</div>
                <span>{email}</span>
                <span class="role-tag role-{role}">{role_label}</span>
            </div>
            <a href="/logout" class="btn btn-ghost btn-sm">Sign out</a>
        </div>
    </nav>
    """


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
    """Parse DASHBOARD_USERS env: 'email:password:role,email:password:role'.
    Role is optional (defaults to 'admin' if missing). Roles: admin | moderator.
    Email is case-insensitive."""
    import config
    users = {}
    for entry in config.DASHBOARD_USERS.split(","):
        parts = entry.split(":")
        if len(parts) < 2:
            continue
        email = parts[0].strip().lower()
        password = parts[1].strip()
        role = (parts[2].strip().lower() if len(parts) >= 3 else "admin")
        if role not in ("admin", "moderator"):
            role = "moderator"
        users[email] = {"password": password, "role": role}
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
    """Returns {'email': str, 'role': str} or None."""
    if not token or "." not in token:
        return None
    payload, _, sig = token.rpartition(".")
    expected = _sign(payload).rpartition(".")[2]
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        decoded = base64.urlsafe_b64decode(payload + "==").decode()
        parts = decoded.split("|")
        if len(parts) < 3:
            return None
        email, role, ts = parts[0], parts[1], parts[2]
        if int(time.time()) - int(ts) > SESSION_MAX_AGE:
            return None
        return {"email": email, "role": role}
    except Exception:
        return None


def _make_session(email, role):
    payload = base64.urlsafe_b64encode(f"{email}|{role}|{int(time.time())}".encode()).decode().rstrip("=")
    return _sign(payload)


def require_auth(ca_session: str = Cookie(None)):
    user = _verify(ca_session) if ca_session else None
    if not user:
        raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/login"})
    return user


def require_admin(user: dict = Depends(lambda ca_session=Cookie(None): require_auth(ca_session))):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
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
    email_lower = email.strip().lower()
    user_record = users.get(email_lower)
    if user_record and user_record["password"] == password:
        token = _make_session(email_lower, user_record["role"])
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
async def dashboard(request: Request, user: dict = Depends(require_auth)):
    try:
        import db
        import config as cfg
        pending = db.get_pending_articles()
        history = db.get_post_history(limit=20)
        mode = "AUTO" if cfg.AUTO_MODE else "MANUAL"
        today = sum(db.get_daily_post_count(f"facebook:{p['page_name']}") for p in db.get_facebook_pages())
        if today == 0:
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
async def trigger(topics: str = Form(""), user: dict = Depends(require_auth)):
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
async def approve(article_id: int, request: Request, user: dict = Depends(require_auth)):
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
async def reject(article_id: int, user: dict = Depends(require_auth)):
    try:
        import db
        db.update_article_status(article_id, "rejected")
    except Exception as e:
        logger.exception("Reject error")
        return JSONResponse({"error": str(e)}, status_code=500)
    return RedirectResponse(url="/", status_code=303)


@app.post("/regenerate-image/{article_id}")
async def regenerate_image_route(article_id: int, user: dict = Depends(require_auth)):
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
async def delete_article(article_id: int, user: dict = Depends(require_auth)):
    try:
        import db
        db.delete_article(article_id)
    except Exception as e:
        logger.exception("Delete error")
        return JSONResponse({"error": str(e)}, status_code=500)
    return RedirectResponse(url="/", status_code=303)


@app.post("/clear-history")
async def clear_history(user: dict = Depends(require_auth)):
    try:
        import db
        db.clear_history()
    except Exception as e:
        logger.exception("Clear history error")
        return JSONResponse({"error": str(e)}, status_code=500)
    return RedirectResponse(url="/", status_code=303)


@app.get("/article/{article_id}", response_class=HTMLResponse)
async def view_article(request: Request, article_id: int, user: dict = Depends(require_auth)):
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
async def pages_view(user: dict = Depends(require_auth), error: str = "", msg: str = "", added: str = ""):
    import db
    pages = db.get_facebook_pages()
    is_admin = user.get("role") == "admin"

    rows = ""
    for p in pages:
        is_env = p.get("id") == 0
        actions = ""
        if is_env:
            actions = '<span class="muted">From env vars</span>'
        elif is_admin:
            actions = f"""
                <form method="post" action="/pages/toggle/{p['id']}" class="inline"><button class="btn btn-sm btn-ghost">{'Disable' if p.get('enabled') else 'Enable'}</button></form>
                <form method="post" action="/pages/delete/{p['id']}" class="inline" onsubmit="return confirm('Delete page {p.get('page_name','')}?')"><button class="btn btn-sm btn-danger">Remove</button></form>
            """
        else:
            actions = '<span class="muted">Admin only</span>'

        status_badge = '<span class="badge badge-success">● Active</span>' if p.get('enabled') else '<span class="badge badge-muted">○ Inactive</span>'
        rows += f"""
        <tr>
            <td><div class="page-name">{p.get('page_name', '')}</div></td>
            <td><code class="page-id">{p.get('page_id', '')}</code></td>
            <td>{status_badge}</td>
            <td>{actions}</td>
        </tr>
        """

    alert = ""
    if added:
        alert = '<div class="alert alert-success">✅ Page added successfully. The bot will now post to this page.</div>'
    if error == "admin_only":
        alert = '<div class="alert alert-warning">⚠️ Only admins can add/remove pages. Contact your admin.</div>'
    if error == "fb":
        alert = f'<div class="alert alert-danger">❌ Facebook rejected the token: {msg}. Make sure the Page ID and token are correct.</div>'

    add_form = ""
    if is_admin:
        add_form = f"""
        <div class="section">
            <div class="section-header">
                <h2>➕ Connect a New Facebook Page</h2>
                <p class="section-sub">Add another Facebook Page to post articles to. The bot will use the Access Token to post on behalf of the page.</p>
            </div>
            <div class="card">
            <form method="post" action="/pages/add" id="addForm">
                <div class="form-group">
                    <div class="label-row">
                        <label>Facebook Page ID <span class="required">*</span></label>
                        <button type="button" class="help-btn" onclick="toggleHelp('h1')">❓ How to find</button>
                    </div>
                    <input name="page_id" placeholder="e.g. 104075216017794" required>
                    <div class="help-text" id="h1">
                        <strong>To find your Page ID:</strong>
                        <ol>
                            <li>Go to your Facebook Page on desktop</li>
                            <li>Click <strong>About</strong> in the left sidebar</li>
                            <li>Scroll all the way down — you'll see "Page ID: 123456789012345"</li>
                        </ol>
                        <em>Alternative:</em> Visit <code>facebook.com/YourPageName</code> → URL may contain the ID, or right-click → View Source → Ctrl+F "page_id".
                    </div>
                </div>

                <div class="form-group">
                    <div class="label-row">
                        <label>Page Access Token <span class="required">*</span></label>
                        <button type="button" class="help-btn" onclick="toggleHelp('h2')">❓ How to get</button>
                    </div>
                    <input name="access_token" placeholder="EAAxxxxxxxx..." required>
                    <div class="help-text" id="h2">
                        <strong>To generate a long-lived Page Access Token:</strong>
                        <ol>
                            <li>Go to <a href="https://developers.facebook.com/tools/explorer/" target="_blank">Graph API Explorer</a></li>
                            <li>Select your Meta App from the dropdown (top right)</li>
                            <li>Click <strong>"Generate Access Token"</strong></li>
                            <li>Grant these permissions: <code>pages_manage_posts</code>, <code>pages_read_engagement</code>, <code>pages_show_list</code></li>
                            <li>In the "User or Page" dropdown, switch from <em>User Token</em> to your <strong>Page name</strong> → copy the new token</li>
                            <li><strong>To extend to 60 days:</strong> Paste in <a href="https://developers.facebook.com/tools/debug/accesstoken/" target="_blank">Token Debugger</a> → click <strong>"Extend Access Token"</strong></li>
                        </ol>
                        <em>⚠️ Tokens are sensitive — treat like passwords.</em>
                    </div>
                </div>

                <div class="form-group">
                    <div class="label-row">
                        <label>Page Name <span class="optional">(optional)</span></label>
                        <button type="button" class="help-btn" onclick="toggleHelp('h3')">❓</button>
                    </div>
                    <input name="page_name" placeholder="Auto-fetched from Facebook if blank">
                    <div class="help-text" id="h3">
                        Leave this blank — we'll fetch the real page name from Facebook automatically to verify the token is valid.
                    </div>
                </div>

                <div class="form-actions">
                    <button class="btn btn-primary" type="submit">+ Connect Page</button>
                </div>
            </form>
            </div>
        </div>
        """

    return HTMLResponse(f"""
    <!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pages · Content Automation</title>
    {_theme_css()}
    </head><body>
    {_nav(user, "pages")}
    <main class="main-wrap">
        {alert}
        <div class="section">
            <div class="section-header">
                <div>
                    <h1>Facebook Pages</h1>
                    <p class="section-sub">Manage which pages the bot posts to. You'll be able to choose specific pages when approving each article.</p>
                </div>
                <span class="badge badge-info">{len(pages)} connected</span>
            </div>
            <div class="card card-flush">
                <table class="data-table">
                    <thead><tr><th>Page Name</th><th>Page ID</th><th>Status</th><th></th></tr></thead>
                    <tbody>{rows or '<tr><td colspan="4" class="empty-cell">No pages connected yet. Add one below to get started.</td></tr>'}</tbody>
                </table>
            </div>
        </div>
        {add_form}
    </main>
    <script>
    function toggleHelp(id) {{
        const el = document.getElementById(id);
        el.style.display = el.style.display === 'block' ? 'none' : 'block';
    }}
    </script>
    </body></html>
    """)


@app.post("/pages/add")
async def pages_add(
    page_id: str = Form(...),
    access_token: str = Form(...),
    page_name: str = Form(""),
    user: dict = Depends(require_auth),
):
    if user.get("role") != "admin":
        return RedirectResponse(url="/pages?error=admin_only", status_code=303)
    import db
    import httpx
    try:
        # Auto-fetch real page name from Facebook if not provided
        fetched_name = ""
        try:
            r = httpx.get(
                f"https://graph.facebook.com/v21.0/{page_id.strip()}",
                params={"fields": "name", "access_token": access_token.strip()},
                timeout=10,
            )
            data = r.json()
            if "name" in data:
                fetched_name = data["name"]
            elif "error" in data:
                return RedirectResponse(url=f"/pages?error=fb&msg={data['error'].get('message','invalid')[:80]}", status_code=303)
        except Exception as e:
            logger.warning(f"Page name fetch: {e}")

        final_name = page_name.strip() or fetched_name or f"Page {page_id}"
        db.add_facebook_page(page_id.strip(), final_name, access_token.strip())
    except Exception as e:
        return RedirectResponse(url=f"/pages?error=db&msg={str(e)[:80]}", status_code=303)
    return RedirectResponse(url="/pages?added=1", status_code=303)


@app.post("/pages/delete/{row_id}")
async def pages_delete_admin(row_id: int, user: dict = Depends(require_auth)):
    if user.get("role") != "admin":
        return RedirectResponse(url="/pages?error=admin_only", status_code=303)
    import db
    db.delete_facebook_page(row_id)
    return RedirectResponse(url="/pages", status_code=303)


@app.post("/pages/toggle/{row_id}")
async def pages_toggle_admin(row_id: int, user: dict = Depends(require_auth)):
    if user.get("role") != "admin":
        return RedirectResponse(url="/pages?error=admin_only", status_code=303)
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
    user: dict = Depends(require_auth),
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
async def diagnose(user: dict = Depends(require_auth)):
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
