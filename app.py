import os
import time
import json
import hashlib
import threading
from datetime import datetime
import requests
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

# --- CONFIGURATION ---
RAW_KEYS_URL = "https://gist.githubusercontent.com/Memmbuu/95428a4fbe165af4e78544662d8d54b4/raw/keys.txt"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
FAVICON_URI = "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23da373d' stroke-width='2.5'><path d='M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z'/></svg>"
DATA_FILE = "free_users.json"
FREE_LIMIT = 300

# Thread lock for safe JSON file writes across concurrent threads
db_lock = threading.RLock()

# --- DATABASE / PERSISTENCE HELPERS ---
def get_token_hash(token):
    """Hashes the Discord token so sensitive tokens aren't saved in cleartext."""
    return hashlib.sha256(token.strip().encode()).hexdigest()

def load_free_tracker():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_free_tracker(data):
    with db_lock:
        try:
            with open(DATA_FILE, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[DB ERROR] Failed to save tracker: {e}")

# Load saved tracker into memory on server boot
# Format: { "discord_token_hash": {"count": int, "date": "YYYY-MM-DD"} }
free_usage_tracker = load_free_tracker()
active_sessions = {}


def get_free_usage(token_hash):
    """Return today's free usage for a token, resetting the counter on a new day."""
    today = datetime.now().date().isoformat()

    with db_lock:
        entry = free_usage_tracker.get(token_hash)

        # Backward compatibility with the previous integer-only tracker format.
        if isinstance(entry, int):
            entry = {"count": entry, "date": today}
            free_usage_tracker[token_hash] = entry
            save_free_tracker(free_usage_tracker)
        elif not isinstance(entry, dict):
            entry = {"count": 0, "date": today}
            free_usage_tracker[token_hash] = entry
            save_free_tracker(free_usage_tracker)
        elif entry.get("date") != today:
            entry = {"count": 0, "date": today}
            free_usage_tracker[token_hash] = entry
            save_free_tracker(free_usage_tracker)

        return int(entry.get("count", 0))


def increment_free_usage(token_hash):
    """Increment today's free usage and return the new count."""
    today = datetime.now().date().isoformat()

    with db_lock:
        entry = free_usage_tracker.get(token_hash)

        if not isinstance(entry, dict) or entry.get("date") != today:
            entry = {"count": 0, "date": today}

        entry["count"] = int(entry.get("count", 0)) + 1
        free_usage_tracker[token_hash] = entry
        save_free_tracker(free_usage_tracker)
        return entry["count"]

# --- PRO KEY VALIDATION ---
def verify_key(key):
    if not key:
        return False
    try:
        res = requests.get(RAW_KEYS_URL, timeout=5)
        if res.status_code == 200:
            data = res.json()
            keys_dict = data.get("KEYS", {})
            user_key = keys_dict.get(key.strip())
            # Verify the key exists and active state is strictly true
            if user_key and user_key.get("active") is True:
                return True
    except Exception as e:
        print(f"[KEY VERIFY ERROR] {e}")
    return False

# ==============================================================================
# 1. LANDING HOME PAGE HTML & CSS
# ==============================================================================
HOME_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="AutoSender v3 Discord message automation with a free daily tier and Pro access.">
    <title>AutoSender v3 | Discord Automation</title>
    <link rel="icon" type="image/svg+xml" href="{FAVICON_URI}">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #08090b;
            --panel: #0f1114;
            --panel-2: #14171b;
            --panel-3: #191c21;
            --red: #da373d;
            --red-bright: #ff5d63;
            --red-soft: rgba(218,55,61,.16);
            --green: #23a55a;
            --purple: #5865F2;
            --text: #f5f7fa;
            --muted: #9aa2ad;
            --line: rgba(255,255,255,.08);
            --line-strong: rgba(255,255,255,.13);
            --shadow: 0 30px 80px rgba(0,0,0,.42);
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        html { scroll-behavior: smooth; }
        body {
            min-height: 100vh;
            color: var(--text);
            background:
                radial-gradient(circle at 15% -5%, rgba(218,55,61,.15), transparent 28%),
                radial-gradient(circle at 92% 8%, rgba(88,101,242,.10), transparent 26%),
                linear-gradient(180deg, #090a0c 0%, #08090b 100%);
            font-family: 'Inter', system-ui, sans-serif;
            overflow-x: hidden;
        }
        body::before {
            content: "";
            position: fixed;
            inset: 0;
            pointer-events: none;
            background-image: linear-gradient(rgba(255,255,255,.02) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.02) 1px, transparent 1px);
            background-size: 52px 52px;
            mask-image: linear-gradient(to bottom, rgba(0,0,0,.35), transparent 68%);
        }
        a { color: inherit; text-decoration: none; }
        button { font: inherit; }
        .site-shell { width: min(1240px, calc(100% - 36px)); margin: 0 auto; }
        .topbar {
            position: sticky; top: 0; z-index: 50;
            backdrop-filter: blur(20px);
            background: rgba(8,9,11,.78);
            border-bottom: 1px solid rgba(255,255,255,.06);
        }
        .nav {
            min-height: 76px; display: flex; align-items: center; justify-content: space-between; gap: 18px;
        }
        .brand { display:flex; align-items:center; gap:12px; font-family:'Space Grotesk',sans-serif; font-weight:700; letter-spacing:-.03em; }
        .brand-mark {
            width: 38px; height: 38px; border-radius: 12px; display:grid; place-items:center;
            background: linear-gradient(135deg, #1a1d22, #0f1114); border:1px solid rgba(255,255,255,.1);
            box-shadow: inset 0 0 0 1px rgba(218,55,61,.16), 0 8px 24px rgba(0,0,0,.25);
        }
        .brand-mark svg { width: 21px; height: 21px; }
        .brand-name { font-size: 18px; }
        .brand-name span { color: var(--red); }
        .nav-links { display:flex; align-items:center; gap: 8px; flex-wrap: wrap; justify-content:flex-end; }
        .nav-link, .nav-cta {
            padding: 10px 14px; border-radius: 10px; font-size: 13px; font-weight: 700; transition:.2s ease;
            border: 1px solid transparent;
        }
        .nav-link { color: var(--muted); }
        .nav-link:hover { color: var(--text); background: rgba(255,255,255,.04); }
        .nav-cta { background: var(--red); box-shadow: 0 8px 22px rgba(218,55,61,.22); }
        .nav-cta:hover { transform: translateY(-1px); background: var(--red-bright); }
        .discord-cta { border-color: rgba(88,101,242,.35); background: rgba(88,101,242,.10); color: #c8ccff; }
        .discord-cta:hover { background: rgba(88,101,242,.20); border-color: rgba(88,101,242,.55); }

        .hero { padding: 86px 0 48px; }
        .hero-grid { display:grid; grid-template-columns: 1.04fr .96fr; gap: 42px; align-items:center; }
        .eyebrow { display:inline-flex; gap:8px; align-items:center; padding:7px 10px; border:1px solid rgba(218,55,61,.28); background:rgba(218,55,61,.07); border-radius:999px; color:#ffb4b7; font-size:11px; font-weight:800; letter-spacing:.08em; text-transform:uppercase; }
        .hero h1 { margin-top:18px; font-family:'Space Grotesk',sans-serif; font-size: clamp(44px, 6vw, 76px); line-height:.98; letter-spacing:-.055em; max-width: 800px; }
        .hero h1 span { color: var(--red); }
        .hero-copy { margin-top:20px; max-width: 690px; color: var(--muted); font-size:16px; line-height:1.75; }
        .hero-actions { display:flex; flex-wrap:wrap; gap:12px; margin-top:28px; }
        .hero-btn { padding:14px 18px; border-radius:12px; font-weight:800; font-size:14px; border:1px solid var(--line-strong); transition:.2s ease; }
        .hero-btn.primary { background:linear-gradient(180deg,#ef464d,#c92f35); border-color:rgba(255,255,255,.08); box-shadow:0 18px 35px rgba(218,55,61,.18); }
        .hero-btn.primary:hover { transform:translateY(-2px); }
        .hero-btn.ghost { background:rgba(255,255,255,.03); }
        .hero-btn.ghost:hover { background:rgba(255,255,255,.06); }
        .hero-meta { display:flex; gap:20px; flex-wrap:wrap; margin-top:24px; color:#b2bac5; font-size:12px; font-weight:700; }
        .hero-meta span { display:flex; gap:8px; align-items:center; }
        .dot { width:7px; height:7px; border-radius:50%; background:var(--green); box-shadow:0 0 10px rgba(35,165,90,.65); }

        .preview {
            position:relative; border:1px solid var(--line); background:linear-gradient(180deg,rgba(25,28,33,.95),rgba(11,13,16,.98));
            border-radius:20px; padding:16px; box-shadow:var(--shadow); overflow:hidden;
        }
        .preview::after { content:""; position:absolute; inset:auto -20% -35% 20%; height:240px; background:radial-gradient(circle,rgba(218,55,61,.18),transparent 65%); pointer-events:none; }
        .preview-top { display:flex; align-items:center; justify-content:space-between; padding:4px 2px 12px; }
        .window-dots { display:flex; gap:7px; }
        .window-dots i { width:8px; height:8px; border-radius:50%; background:#41464e; }
        .preview-label { font-size:11px; color:#7f8995; font-weight:800; letter-spacing:.08em; text-transform:uppercase; }
        .preview-panel { border:1px solid var(--line); background:rgba(8,9,11,.9); border-radius:15px; padding:18px; }
        .preview-header { display:flex; align-items:center; justify-content:space-between; gap:12px; }
        .preview-title { font-family:'Space Grotesk',sans-serif; font-size:20px; font-weight:700; }
        .live-badge { padding:6px 9px; border-radius:8px; background:rgba(35,165,90,.12); color:#7fe6a6; border:1px solid rgba(35,165,90,.25); font-size:10px; font-weight:800; }
        .preview-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:14px; }
        .stat { padding:13px; border-radius:12px; background:rgba(255,255,255,.025); border:1px solid var(--line); }
        .stat strong { display:block; font-size:19px; }
        .stat span { display:block; margin-top:4px; color:#7f8995; font-size:11px; }
        .terminal { margin-top:12px; border-radius:12px; background:#070809; border:1px solid rgba(255,255,255,.07); overflow:hidden; }
        .terminal-head { padding:9px 11px; border-bottom:1px solid rgba(255,255,255,.06); font-size:10px; color:#707984; }
        .terminal-body { min-height:180px; max-height:190px; overflow:auto; padding:12px; font:12px/1.65 'Fira Code',monospace; }
        .log-entry { display:flex; gap:10px; }
        .log-time { color:#515a65; }
        .log-tag { color:#ff676d; font-weight:700; }
        .log-text { color:#b7bec7; }
        .log-success { color:#6fdd9d; }
        .terminal-footer { padding:10px 12px; border-top:1px solid rgba(255,255,255,.06); display:flex; align-items:center; justify-content:space-between; }
        .terminal-footer span { font-size:10px; color:#6e7882; }
        .terminal-footer button { border:1px solid rgba(218,55,61,.25); background:rgba(218,55,61,.08); color:#ff9b9f; border-radius:8px; padding:7px 10px; font-size:10px; font-weight:800; cursor:pointer; }

        .section { padding: 76px 0; }
        .section-head { display:flex; align-items:end; justify-content:space-between; gap:24px; margin-bottom:26px; }
        .section-kicker { color:#ff878c; font-size:11px; text-transform:uppercase; letter-spacing:.1em; font-weight:900; }
        .section-title { margin-top:8px; font-family:'Space Grotesk',sans-serif; font-size:clamp(28px,4vw,42px); letter-spacing:-.04em; }
        .section-sub { max-width:650px; color:var(--muted); line-height:1.65; font-size:14px; }
        .features { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }
        .feature { padding:22px; border:1px solid var(--line); background:linear-gradient(180deg,rgba(20,23,27,.9),rgba(13,15,18,.94)); border-radius:16px; transition:.2s ease; }
        .feature:hover { transform:translateY(-3px); border-color:rgba(218,55,61,.28); }
        .feature-icon { width:38px; height:38px; display:grid; place-items:center; border-radius:11px; background:rgba(218,55,61,.10); border:1px solid rgba(218,55,61,.18); color:#ff8589; font-weight:900; }
        .feature h3 { margin-top:15px; font-size:16px; }
        .feature p { margin-top:8px; color:var(--muted); font-size:13px; line-height:1.65; }

        .plans { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }
        .plan { position:relative; padding:26px; background:linear-gradient(180deg,rgba(18,20,24,.98),rgba(12,14,17,.98)); border:1px solid var(--line); border-radius:18px; }
        .plan.popular { border-color:rgba(218,55,61,.48); box-shadow:0 18px 40px rgba(218,55,61,.10); }
        .plan-tag { position:absolute; top:14px; right:14px; font-size:9px; font-weight:900; text-transform:uppercase; letter-spacing:.08em; color:#ffb0b3; background:rgba(218,55,61,.1); padding:5px 7px; border-radius:7px; border:1px solid rgba(218,55,61,.22); }
        .plan h3 { font-size:17px; }
        .plan-price { margin-top:12px; font-family:'Space Grotesk',sans-serif; font-size:38px; letter-spacing:-.04em; }
        .plan-price small { color:#7f8995; font:700 12px Inter,sans-serif; letter-spacing:0; }
        .plan ul { list-style:none; margin-top:20px; display:grid; gap:9px; }
        .plan li { color:#b5bdc7; font-size:12px; }
        .plan li::before { content:'✓'; color:#6fdd9d; margin-right:8px; }
        .plan-btn { display:block; width:100%; margin-top:22px; padding:11px 12px; border-radius:10px; text-align:center; font-size:12px; font-weight:900; border:1px solid var(--line-strong); background:rgba(255,255,255,.03); }
        .plan-btn.primary { background:var(--red); border-color:var(--red); }
        .plan-btn:hover { background:rgba(255,255,255,.07); }
        .plan-btn.primary:hover { background:var(--red-bright); }

        .join { display:grid; grid-template-columns:1.15fr .85fr; gap:18px; align-items:stretch; }
        .join-card { padding:28px; border:1px solid rgba(88,101,242,.25); background:linear-gradient(135deg,rgba(88,101,242,.11),rgba(16,18,22,.95)); border-radius:18px; }
        .join-card h2 { font-family:'Space Grotesk',sans-serif; font-size:28px; }
        .join-card p { margin-top:10px; color:#aab2bc; font-size:13px; line-height:1.7; max-width:670px; }
        .join-btn { display:inline-flex; align-items:center; gap:8px; margin-top:18px; padding:12px 14px; border-radius:10px; background:var(--purple); font-weight:900; font-size:12px; }
        .join-btn:hover { filter:brightness(1.08); transform:translateY(-1px); }
        .buy-card { padding:28px; border:1px solid rgba(218,55,61,.25); background:linear-gradient(135deg,rgba(218,55,61,.12),rgba(16,18,22,.96)); border-radius:18px; }
        .buy-card h3 { font-family:'Space Grotesk',sans-serif; font-size:24px; }
        .buy-card p { margin-top:9px; color:#aab2bc; font-size:13px; line-height:1.65; }
        .buy-btn { display:inline-flex; margin-top:18px; padding:12px 14px; border-radius:10px; background:var(--red); font-weight:900; font-size:12px; }
        .buy-btn:hover { background:var(--red-bright); }

        .rules { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
        .rule-card { padding:22px; border-radius:16px; background:rgba(255,255,255,.025); border:1px solid var(--line); }
        .rule-card h3 { font-size:15px; }
        .rule-card ul { margin-top:12px; padding-left:17px; color:var(--muted); font-size:12px; line-height:1.8; }
        .footer { padding:30px 0 50px; color:#68727e; font-size:11px; border-top:1px solid rgba(255,255,255,.05); }
        .footer-inner { display:flex; align-items:center; justify-content:space-between; gap:16px; }
        .footer strong { color:#9da6b1; }

        @media (max-width: 980px) {
            .hero-grid, .join { grid-template-columns:1fr; }
            .features, .plans { grid-template-columns:1fr 1fr; }
            .preview { max-width:760px; margin:0 auto; }
        }
        @media (max-width: 680px) {
            .site-shell { width:min(100% - 22px,1240px); }
            .nav { min-height:66px; }
            .nav-link { display:none; }
            .hero { padding-top:56px; }
            .hero-actions { display:grid; grid-template-columns:1fr; }
            .hero-btn { text-align:center; }
            .features, .plans, .rules { grid-template-columns:1fr; }
            .section-head { display:block; }
            .section-sub { margin-top:10px; }
            .footer-inner { flex-direction:column; align-items:flex-start; }
        }
        @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after { animation:none !important; transition:none !important; scroll-behavior:auto !important; }
        }
    </style>
</head>
<body>
    <header class="topbar">
        <div class="site-shell nav">
            <a class="brand" href="/">
                <span class="brand-mark" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="#ff5d63" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8A2.5 2.5 0 0 1 17.5 16H9l-4.5 4V5.5Z"/>
                        <path d="M8 8h8M8 11h5"/>
                    </svg>
                </span>
                <span class="brand-name">AutoSender <span>v3</span></span>
            </a>
            <nav class="nav-links">
                <a class="nav-link" href="#features">Features</a>
                <a class="nav-link" href="#pricing">Pricing</a>
                <a class="nav-link" href="#rules">Setup</a>
                <a class="nav-cta discord-cta" href="https://discord.gg/6feS4msabZ" target="_blank" rel="noopener">Join Discord</a>
                <a class="nav-cta" href="/pro">Get Pro</a>
            </nav>
        </div>
    </header>

    <main class="site-shell">
        <section class="hero">
            <div class="hero-grid">
                <div>
                    <span class="eyebrow">Clean setup · Free + Pro</span>
                    <h1>Discord automation, <span>without the clutter.</span></h1>
                    <p class="hero-copy">AutoSender v3 gives you a simple free dashboard for everyday use and a full Pro workspace when you need unlimited message dispatching, multiple process tabs, and watermark-free output.</p>
                    <div class="hero-actions">
                        <a class="hero-btn primary" href="/app">Launch Free Dashboard</a>
                        <a class="hero-btn ghost" href="/pro">Explore Pro Access</a>
                        <a class="hero-btn ghost" href="https://discord.gg/6feS4msabZ" target="_blank" rel="noopener">Join the Discord</a>
                    </div>
                    <div class="hero-meta">
                        <span><i class="dot"></i> Daily Free allowance</span>
                        <span>✓ Pro removes the free watermark</span>
                        <span>✓ Saved browser settings</span>
                    </div>
                </div>
                <div class="preview">
                    <div class="preview-top">
                        <div class="window-dots"><i></i><i></i><i></i></div>
                        <div class="preview-label">AutoSender control panel</div>
                    </div>
                    <div class="preview-panel">
                        <div class="preview-header">
                            <div class="preview-title">Automation overview</div>
                            <div class="live-badge">SYSTEM READY</div>
                        </div>
                        <div class="preview-grid">
                            <div class="stat"><strong>300</strong><span>Free messages / day</span></div>
                            <div class="stat"><strong>∞</strong><span>Pro messages</span></div>
                            <div class="stat"><strong>1</strong><span>Free process tab</span></div>
                            <div class="stat"><strong>Multi</strong><span>Pro process tabs</span></div>
                        </div>
                        <div class="terminal">
                            <div class="terminal-head">autosender-engine.log</div>
                            <div class="terminal-body" id="terminalLogs">
                                <div class="log-entry"><span class="log-time">[SYSTEM]</span><span class="log-tag">[READY]</span><span class="log-text">AutoSender Engine v3 loaded.</span></div>
                                <div class="log-entry"><span class="log-time">[FREE]</span><span class="log-tag">[300]</span><span class="log-success">Daily allowance available.</span></div>
                                <div class="log-entry"><span class="log-time">[PRO]</span><span class="log-tag">[UNLOCK]</span><span class="log-success">Unlimited mode available.</span></div>
                            </div>
                            <div class="terminal-footer"><span>Quick demo only</span><button type="button" onclick="triggerDemoLog()">Run demo</button></div>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <section class="section" id="features">
            <div class="section-head">
                <div><div class="section-kicker">Built around the workflow</div><h2 class="section-title">Everything important is one click away.</h2></div>
                <p class="section-sub">The redesign keeps the existing automation flow intact, but makes the important actions easier to understand before you start a process.</p>
            </div>
            <div class="features">
                <article class="feature"><div class="feature-icon">01</div><h3>Fast setup</h3><p>Clear labels and checks help catch common token, channel ID, comma, and spacing mistakes before the request is sent.</p></article>
                <article class="feature"><div class="feature-icon">02</div><h3>Free every day</h3><p>The Free dashboard uses the daily allowance already built into the backend, with the counter resetting on a new server-local date.</p></article>
                <article class="feature"><div class="feature-icon">03</div><h3>Pro when you need it</h3><p>Valid Pro keys keep the existing multi-process workflow while removing the Free-tier watermark and message cap.</p></article>
            </div>
        </section>

        <section class="section" id="pricing">
            <div class="section-head">
                <div><div class="section-kicker">Choose your tier</div><h2 class="section-title">Start free. Upgrade when you need more.</h2></div>
                <p class="section-sub">Use the Free dashboard for testing and everyday usage, or open Pro when you want the complete automation workspace.</p>
            </div>
            <div class="plans">
                <article class="plan">
                    <h3>Free Tier</h3><div class="plan-price">$0 <small>/ forever</small></div>
                    <ul><li>300 messages each day</li><li>Free-tier watermark</li><li>Single process tab</li><li>Community support</li></ul>
                    <a class="plan-btn" href="/app">Use Free</a>
                </article>
                <article class="plan popular">
                    <div class="plan-tag">Recommended</div><h3>Pro Key</h3><div class="plan-price">$9.99 <small>/ month</small></div>
                    <ul><li>Unlimited messages</li><li>No promotional watermark</li><li>Multiple process tabs</li><li>Priority access to Pro workspace</li></ul>
                    <a class="plan-btn primary" href="/pro">Get Pro Access</a>
                </article>
                <article class="plan">
                    <h3>Lifetime Pass</h3><div class="plan-price">$29.99 <small>/ one-time</small></div>
                    <ul><li>Lifetime unlimited access</li><li>No watermarks</li><li>Pro workspace</li><li>Community support</li></ul>
                    <a class="plan-btn" href="/pro">Open Pro</a>
                </article>
            </div>
        </section>

        <section class="section">
            <div class="join">
                <div class="join-card">
                    <div class="section-kicker">Community</div>
                    <h2>Need a key, support, or just want to stay updated?</h2>
                    <p>Join the AutoSender Discord for support, updates, and access to the community around the tool. Keep credentials private when asking for help.</p>
                    <a class="join-btn" href="https://discord.gg/6feS4msabZ" target="_blank" rel="noopener">Join the AutoSender Discord ↗</a>
                </div>
                <div class="buy-card">
                    <div class="section-kicker">Pro access</div>
                    <h3>Ready to remove the Free-tier limits?</h3>
                    <p>Open the Pro workspace and enter your active key. The existing backend validation and unlimited Pro behavior stay unchanged.</p>
                    <a class="buy-btn" href="/pro">Open Pro Dashboard →</a>
                </div>
            </div>
        </section>

        <section class="section" id="rules">
            <div class="section-head">
                <div><div class="section-kicker">Before you start</div><h2 class="section-title">A few checks save a lot of debugging.</h2></div>
                <p class="section-sub">These reminders mirror the checks already built into the dashboards and are worth reading before troubleshooting a failed send.</p>
            </div>
            <div class="rules">
                <div class="rule-card"><h3>Common input problems</h3><ul><li>Remove commas, quotes, accidental spaces, and line breaks from copied values.</li><li>Channel IDs should be digits only.</li><li>Recheck the token if requests fail before changing anything else.</li><li>Make sure the account can access the target channel.</li></ul></div>
                <div class="rule-card"><h3>Keep credentials private</h3><ul><li>Do not publish account tokens or license keys in screenshots or chats.</li><li>Use the tool only where you have permission and follow Discord and server rules.</li><li>If a credential was exposed, replace it before continuing.</li><li>When asking support for help, share the error, not the credential.</li></ul></div>
            </div>
        </section>

        <footer class="footer"><div class="footer-inner"><div>AutoSender <strong>v3</strong> · premium dashboard redesign</div><div>Free for testing · Pro for unlimited access</div></div></footer>
    </main>
<script>
        function triggerDemoLog() {
            const terminal = document.getElementById('terminalLogs');
            const now = new Date().toTimeString().split(' ')[0];
            const sampleLogs = [
                `<div class="log-entry"><span class="log-time">[${now}]</span> <span class="log-tag">[PROC #1]</span> <span class="log-text">Triggering scheduled payload...</span></div>`,
                `<div class="log-entry"><span class="log-time">[${now}]</span> <span class="log-tag">[PROC #1]</span> <span class="log-success">HTTP 200 OK — Sent (3/300 free used)</span></div>`,
                `<div class="log-entry"><span class="log-time">[${now}]</span> <span class="log-tag">[SYSTEM]</span> <span class="log-text">Interval sleep initialized for 60s.</span></div>`
            ];
            
            sampleLogs.forEach((log, index) => {
                setTimeout(() => {
                    terminal.innerHTML += log;
                    terminal.scrollTop = terminal.scrollHeight;
                }, index * 400);
            });
        }
    </script>
</html>
"""
FREE_TOOL_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoSender v3 | Free Dashboard</title>
    <link rel="icon" type="image/svg+xml" href="{FAVICON_URI}">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Space+Grotesk:wght@600;700&display=swap" rel="stylesheet">
    <style>
        :root { --bg:#08090b; --panel:#111317; --panel2:#171a1f; --input:#0d0f12; --red:#da373d; --red2:#ff5d63; --text:#f3f5f7; --muted:#969faa; --line:rgba(255,255,255,.08); --green:#23a55a; --error:#f23f43; }
        * { box-sizing:border-box; margin:0; padding:0; }
        body { min-height:100vh; color:var(--text); background:radial-gradient(circle at 15% 0%,rgba(218,55,61,.13),transparent 26%),linear-gradient(180deg,#090a0c,#08090b); font-family:Inter,system-ui,sans-serif; }
        a { color:inherit; text-decoration:none; }
        .shell { width:min(1360px,calc(100% - 28px)); margin:0 auto; }
        .topbar { min-height:72px; display:flex; align-items:center; justify-content:space-between; gap:14px; border-bottom:1px solid var(--line); }
        .brand { display:flex; align-items:center; gap:11px; font-family:'Space Grotesk',sans-serif; font-weight:700; }
        .brand svg { width:31px; height:31px; }
        .brand span span { color:var(--red); }
        .top-actions { display:flex; gap:8px; align-items:center; }
        .top-btn { padding:9px 12px; border:1px solid var(--line); border-radius:9px; font-size:11px; font-weight:800; color:var(--muted); background:rgba(255,255,255,.02); }
        .top-btn:hover { color:var(--text); background:rgba(255,255,255,.05); }
        .top-btn.primary { color:white; background:var(--red); border-color:var(--red); }
        .layout { min-height:calc(100vh - 72px); display:grid; grid-template-columns:300px minmax(0,1fr); gap:18px; padding:18px 0 30px; }
        .sidebar, .card { background:linear-gradient(180deg,rgba(18,20,24,.98),rgba(12,14,17,.98)); border:1px solid var(--line); border-radius:18px; }
        .sidebar { padding:22px; align-self:start; position:sticky; top:16px; }
        .badge { display:inline-flex; padding:6px 8px; border-radius:7px; background:rgba(218,55,61,.09); border:1px solid rgba(218,55,61,.18); color:#ff9b9f; font-size:10px; font-weight:900; letter-spacing:.06em; text-transform:uppercase; }
        .sidebar h1 { margin-top:12px; font:700 28px 'Space Grotesk',sans-serif; letter-spacing:-.04em; }
        .sidebar p { margin-top:10px; color:var(--muted); font-size:12px; line-height:1.7; }
        .side-list { list-style:none; margin-top:18px; display:grid; gap:8px; }
        .side-list li { padding:10px 11px; border-radius:9px; background:rgba(255,255,255,.025); border:1px solid rgba(255,255,255,.05); color:#acb4be; font-size:11px; }
        .side-list strong { color:#f0f2f4; }
        .side-cta { display:grid; gap:8px; margin-top:16px; }
        .side-cta a { padding:11px; border-radius:9px; text-align:center; font-size:11px; font-weight:900; border:1px solid var(--line); }
        .side-cta .pro { background:var(--red); border-color:var(--red); }
        .side-cta .discord { color:#c9ceff; border-color:rgba(88,101,242,.3); background:rgba(88,101,242,.08); }
        .card { padding:26px; min-width:0; }
        .header { display:flex; align-items:flex-start; justify-content:space-between; gap:18px; padding-bottom:18px; border-bottom:1px solid var(--line); }
        .header-title h2 { font:700 clamp(24px,3vw,34px) 'Space Grotesk',sans-serif; letter-spacing:-.04em; }
        .header-title h2 span { color:var(--red); }
        .helper-text { margin-top:16px; padding:12px 14px; border:1px solid rgba(255,255,255,.06); background:rgba(255,255,255,.025); border-radius:11px; color:#aab2bc; font-size:12px; line-height:1.6; }
        .rules-card { margin-top:14px; padding:14px; border:1px solid rgba(218,55,61,.16); background:rgba(218,55,61,.045); border-radius:12px; }
        .rules-card strong { font-size:11px; }
        .rules-card ul { margin:9px 0 0 16px; color:#afb7c0; font-size:11px; line-height:1.8; }
        .form-group { margin-top:17px; }
        label { display:block; margin-bottom:7px; color:#a9b0b9; font-size:10px; font-weight:900; text-transform:uppercase; letter-spacing:.08em; }
        input, textarea, select { width:100%; border:1px solid rgba(255,255,255,.08); outline:none; color:var(--text); background:var(--input); border-radius:10px; padding:12px 13px; font:13px Inter,sans-serif; transition:.18s ease; }
        textarea { min-height:160px; resize:vertical; line-height:1.55; }
        input:focus, textarea:focus, select:focus { border-color:rgba(218,55,61,.7); box-shadow:0 0 0 3px rgba(218,55,61,.12); }
        .field-hint { display:block; margin-top:6px; color:#717b86; font-size:10px; line-height:1.5; }
        .btn-group { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:18px; }
        .action-btn { width:100%; border:0; border-radius:10px; padding:13px; font-size:12px; font-weight:900; cursor:pointer; transition:.18s ease; }
        .btn-save { background:#22a35a; color:white; }
        .btn-start { background:linear-gradient(180deg,#ee484e,#cb3036); color:white; box-shadow:0 12px 24px rgba(218,55,61,.16); }
        .btn-stop { background:#23262c; color:#f2f3f5; border:1px solid rgba(255,255,255,.08); }
        .btn-clear { background:transparent; color:#99a2ad; border:1px dashed rgba(255,255,255,.14); }
        .action-btn:hover { transform:translateY(-1px); filter:brightness(1.04); }
        .status-container { margin-top:16px; padding:13px; display:flex; align-items:flex-start; gap:10px; border:1px solid rgba(255,255,255,.06); border-left:3px solid #515965; border-radius:10px; background:rgba(255,255,255,.025); color:#9da6b0; font-size:11px; min-height:48px; }
        .status-container.active { border-left-color:var(--green); color:#d6f5e1; }
        .status-container.error { border-left-color:var(--error); color:#ffd9da; }
        .status-dot-main { width:8px; height:8px; margin-top:3px; border-radius:50%; background:#5c6068; flex:none; }
        .status-container.active .status-dot-main { background:var(--green); box-shadow:0 0 10px rgba(35,165,90,.7); }
        .status-container.error .status-dot-main { background:var(--error); }
        .free-footer-note { margin-top:18px; padding-top:15px; border-top:1px solid var(--line); color:#707985; font-size:10px; line-height:1.6; }
        @media (max-width:900px) { .layout { grid-template-columns:1fr; } .sidebar { position:static; } }
        @media (max-width:620px) { .shell { width:min(100% - 16px,1360px); } .topbar { align-items:flex-start; padding:15px 0; } .top-actions .top-btn:nth-child(2) { display:none; } .btn-group { grid-template-columns:1fr; } .header { flex-direction:column; } }
        @media (prefers-reduced-motion:reduce) { *,*::before,*::after { transition:none !important; } }
    </style>
</head>
<body>
<div class="shell">
    <div class="topbar">
        <a class="brand" href="/"><svg viewBox="0 0 24 24" fill="none" stroke="#ff5d63" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8A2.5 2.5 0 0 1 17.5 16H9l-4.5 4V5.5Z"/><path d="M8 8h8M8 11h5"/></svg><span>AutoSender <span>v3</span></span></a>
        <div class="top-actions"><a class="top-btn" href="/">Home</a><a class="top-btn" href="https://discord.gg/6feS4msabZ" target="_blank" rel="noopener">Discord</a><a class="top-btn primary" href="/pro">Go Pro</a></div>
    </div>
    <div class="layout">
        <aside class="sidebar">
            <span class="badge">Free Mode</span>
            <h1>Start clean.</h1>
            <p>Use the Free dashboard for testing and everyday sends. The setup checks on the right are there to catch the most common copy and access mistakes.</p>
            <ul class="side-list">
                <li><strong>Daily allowance:</strong> 300 messages</li>
                <li><strong>Watermark:</strong> Free tier only</li>
                <li><strong>Processes:</strong> 1 tab</li>
                <li><strong>Reset:</strong> Everyday</li>
            </ul>
            <div class="side-cta"><a class="pro" href="/pro">Upgrade to Pro</a><a class="discord" href="https://discord.gg/6feS4msabZ" target="_blank" rel="noopener">Join Discord</a></div>
        </aside>
        <section class="card">
            <div class="header"><div class="header-title"><h2>Free <span>Dashboard</span></h2></div><span class="badge">Daily 300</span></div>
            <div class="helper-text">Enter your details exactly as provided. If a request fails, start by checking the token, channel ID, and copied punctuation before changing your settings.</div>
            <div class="rules-card"><strong>Quick checks before starting</strong><ul><li>Paste the token exactly. Remove commas, quotes, extra spaces, or accidental line breaks.</li><li>Channel ID should contain digits only. Recheck that you copied the correct channel.</li><li>If sending fails, recheck the token and that the account can send in the target channel.</li><li>Keep your token private. Never post it in screenshots, chats, or support tickets.</li><li>Use the tool only where you have permission and follow Discord and server rules.</li></ul></div>
            <div id="process-content-1">
                <div class="form-group"><label>Discord Account Token</label><input type="password" class="input-token" autocomplete="off" spellcheck="false" placeholder="Paste token exactly as provided"><span class="field-hint">Remove commas, quotes, or accidental spaces if copied from a list.</span></div>
                <div class="form-group"><label>Discord Channel ID</label><input type="text" class="input-channel" inputmode="numeric" autocomplete="off" spellcheck="false" placeholder="109283746592817264"><span class="field-hint">Digits only. No commas or spaces.</span></div>
                <div class="form-group"><label>Message Content</label><textarea class="input-message" rows="6" placeholder="Paste your formatted message here...&#10;Line 1&#10;Line 2"></textarea></div>
                <div class="form-group"><label>Interval <span style="font-weight:400;color:#5c6068">(Min. 10 Sec)</span></label><div style="display:flex;gap:10px"><input type="number" class="input-interval-val" value="1" min="1"><select class="input-interval-unit"><option value="1">Seconds</option><option value="60" selected>Minutes</option></select></div></div>
                <div class="btn-group"><button class="action-btn btn-save" onclick="saveProcessConfig()">Save Config</button><button class="action-btn btn-clear" onclick="clearProcessConfig()">Clear Config</button></div>
                <div class="btn-group"><button class="action-btn btn-start" onclick="startProcess(1)">Start Process</button><button class="action-btn btn-stop" onclick="stopProcess(1)">Stop Process</button></div>
                <div class="status-container" id="status-1"><div class="status-dot-main"></div><span class="status-text">Process Ready. Idle.</span></div>
            </div>
            <div class="free-footer-note">Free mode includes the daily message allowance and the Free-tier watermark. For more tabs and watermark-free operation, open the Pro dashboard.</div>
        </section>
    </div>
</div>
<script>
        window.addEventListener('load', () => {
            loadProcessConfig();
        });

        window.addEventListener('beforeunload', () => {
            navigator.sendBeacon('/api/stopall');
        });

        function saveProcessConfig() {
            const content = document.getElementById('process-content-1');
            const config = {
                token: content.querySelector('.input-token').value,
                channelId: content.querySelector('.input-channel').value,
                message: content.querySelector('.input-message').value,
                intervalVal: content.querySelector('.input-interval-val').value,
                intervalUnit: content.querySelector('.input-interval-unit').value
            };

            localStorage.setItem('autosender_free_config', JSON.stringify(config));
            const statusText = document.querySelector('#status-1 .status-text');
            statusText.innerText = 'Configuration saved to browser local storage!';
        }

        function loadProcessConfig() {
            const savedData = localStorage.getItem('autosender_free_config');
            if (savedData) {
                try {
                    const config = JSON.parse(savedData);
                    const content = document.getElementById('process-content-1');
                    if (config.token) content.querySelector('.input-token').value = config.token;
                    if (config.channelId) content.querySelector('.input-channel').value = config.channelId;
                    if (config.message) content.querySelector('.input-message').value = config.message;
                    if (config.intervalVal) content.querySelector('.input-interval-val').value = config.intervalVal;
                    if (config.intervalUnit) content.querySelector('.input-interval-unit').value = config.intervalUnit;

                    const statusText = document.querySelector('#status-1 .status-text');
                    statusText.innerText = 'Loaded saved configuration from browser storage!';
                } catch (e) {
                    console.error('Failed to parse saved config:', e);
                }
            }
        }

        function clearProcessConfig() {
            localStorage.removeItem('autosender_free_config');
            const content = document.getElementById('process-content-1');
            content.querySelector('.input-token').value = '';
            content.querySelector('.input-channel').value = '';
            content.querySelector('.input-message').value = '';
            content.querySelector('.input-interval-val').value = '1';
            content.querySelector('.input-interval-unit').value = '60';

            const statusText = document.querySelector('#status-1 .status-text');
            statusText.innerText = 'Saved config cleared!';
        }

        function validateFreeFields(content) {
            const token = content.querySelector('.input-token').value.trim();
            const channelId = content.querySelector('.input-channel').value.trim();
            const message = content.querySelector('.input-message').value.trim();

            if (!token) return 'Enter your token first.';
            if (token.includes(',')) return 'Your token contains a comma. Remove commas and paste the token exactly.';
            if (/\\s/.test(token)) return 'Your token contains a space or line break. Paste it as one continuous value.';
            if (!channelId) return 'Enter the Discord channel ID first.';
            if (!/^\\d+$/.test(channelId)) return 'Channel ID must contain digits only. Remove commas, spaces, or other characters.';
            if (!message) return 'Enter a message before starting the process.';
            return '';
        }

        async function startProcess(id) {
            const content = document.getElementById(`process-content-${id}`);
            const validationError = validateFreeFields(content);
            const statusBox = document.getElementById(`status-${id}`);
            const statusText = statusBox.querySelector('.status-text');
            if (validationError) {
                statusBox.className = 'status-container error';
                statusText.innerText = validationError;
                return;
            }
            const token = content.querySelector('.input-token').value.trim();
            const channelId = content.querySelector('.input-channel').value;
            const message = content.querySelector('.input-message').value;
            
            const intervalVal = parseInt(content.querySelector('.input-interval-val').value) || 1;
            const intervalUnit = parseInt(content.querySelector('.input-interval-unit').value) || 60;
            let totalSeconds = intervalVal * intervalUnit;
            if (totalSeconds < 10) totalSeconds = 10;

            try {
                const res = await fetch('/api/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        process_id: id,
                        key: '',
                        token: token,
                        channel_id: channelId,
                        message: message,
                        interval: totalSeconds
                    })
                });

                const data = await res.json();

                if (res.ok) {
                    statusBox.className = 'status-container active';
                    statusText.innerText = data.message;
                } else {
                    statusBox.className = 'status-container error';
                    statusText.innerText = data.message || 'Error starting process.';
                }
            } catch (err) {
                statusBox.className = 'status-container error';
                statusText.innerText = 'Network Error: Cannot connect to server.';
            }
        }

        async function stopProcess(id) {
            const statusBox = document.getElementById(`status-${id}`);
            if (!statusBox) return;
            const statusText = statusBox.querySelector('.status-text');

            try {
                const res = await fetch('/api/stop', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ process_id: id })
                });

                const data = await res.json();
                statusBox.className = 'status-container';
                statusText.innerText = data.message || 'Process stopped.';
            } catch (err) {
                statusBox.className = 'status-container error';
                statusText.innerText = 'Failed to stop process.';
            }
        }
    </script>
</html>
"""
PRO_TOOL_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoSender v3 | Pro Dashboard</title>
    <link rel="icon" type="image/svg+xml" href="{FAVICON_URI}">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Space+Grotesk:wght@600;700&display=swap" rel="stylesheet">
    <style>
        :root { --bg:#07080a; --panel:#101216; --panel2:#171a1f; --input:#0b0d10; --red:#da373d; --red2:#ff5d63; --text:#f3f5f7; --muted:#969faa; --line:rgba(255,255,255,.08); --green:#23a55a; --error:#f23f43; --purple:#5865F2; }
        * { box-sizing:border-box; margin:0; padding:0; }
        body { min-height:100vh; color:var(--text); background:radial-gradient(circle at 10% 0%,rgba(218,55,61,.15),transparent 25%),radial-gradient(circle at 90% 0%,rgba(88,101,242,.10),transparent 24%),linear-gradient(180deg,#08090b,#07080a); font-family:Inter,system-ui,sans-serif; }
        a { color:inherit; text-decoration:none; }
        .shell { width:min(1400px,calc(100% - 28px)); margin:0 auto; }
        .topbar { min-height:72px; display:flex; align-items:center; justify-content:space-between; gap:14px; border-bottom:1px solid var(--line); }
        .brand { display:flex; align-items:center; gap:11px; font-family:'Space Grotesk',sans-serif; font-weight:700; }
        .brand svg { width:31px; height:31px; }
        .brand span span { color:var(--red); }
        .top-actions { display:flex; gap:8px; }
        .top-btn { padding:9px 12px; border-radius:9px; border:1px solid var(--line); background:rgba(255,255,255,.02); color:var(--muted); font-size:11px; font-weight:800; }
        .top-btn:hover { color:var(--text); background:rgba(255,255,255,.05); }
        .top-btn.primary { background:var(--red); color:#fff; border-color:var(--red); }
        .layout { min-height:calc(100vh - 72px); display:grid; grid-template-columns:285px minmax(0,1fr); gap:18px; padding:18px 0 30px; }
        .sidebar, .card { background:linear-gradient(180deg,rgba(17,19,24,.99),rgba(10,12,15,.99)); border:1px solid var(--line); border-radius:18px; }
        .sidebar { padding:22px; position:sticky; top:16px; align-self:start; }
        .badge { display:inline-flex; padding:6px 8px; border-radius:7px; background:rgba(218,55,61,.10); border:1px solid rgba(218,55,61,.20); color:#ffb5b8; font-size:10px; font-weight:900; letter-spacing:.06em; text-transform:uppercase; }
        .sidebar h1 { margin-top:12px; font:700 29px 'Space Grotesk',sans-serif; letter-spacing:-.045em; }
        .sidebar p { margin-top:10px; color:var(--muted); font-size:12px; line-height:1.7; }
        .pro-list { margin-top:18px; display:grid; gap:8px; list-style:none; }
        .pro-list li { padding:10px 11px; border:1px solid rgba(255,255,255,.05); border-radius:9px; background:rgba(255,255,255,.02); color:#b3bbc5; font-size:11px; }
        .pro-list strong { color:#f3f5f7; }
        .side-cta { display:grid; gap:8px; margin-top:16px; }
        .side-cta a { padding:11px; border-radius:9px; text-align:center; font-size:11px; font-weight:900; border:1px solid var(--line); }
        .side-cta .free { background:rgba(255,255,255,.03); }
        .side-cta .discord { color:#d2d5ff; background:rgba(88,101,242,.08); border-color:rgba(88,101,242,.3); }
        .card { padding:26px; min-width:0; }
        .header { display:flex; align-items:flex-start; justify-content:space-between; gap:18px; padding-bottom:18px; border-bottom:1px solid var(--line); }
        .header-title h2 { font:700 clamp(25px,3vw,36px) 'Space Grotesk',sans-serif; letter-spacing:-.045em; }
        .header-title h2 span { color:var(--red); }
        .pro-intro { margin-top:16px; padding:13px 14px; border:1px solid rgba(35,165,90,.16); background:rgba(35,165,90,.05); border-radius:11px; color:#b5c7bc; font-size:12px; line-height:1.65; }
        .rules-card { margin-top:14px; padding:14px; border:1px solid rgba(218,55,61,.16); background:rgba(218,55,61,.045); border-radius:12px; }
        .rules-card strong { font-size:11px; }
        .rules-card ul { margin:9px 0 0 16px; color:#afb7c0; font-size:11px; line-height:1.8; }
        .tabs-bar { display:flex; gap:7px; align-items:center; overflow-x:auto; padding:2px 1px 8px; margin-top:18px; scrollbar-width:thin; }
        .tab-btn, .add-tab-btn { flex:none; border-radius:9px; padding:9px 11px; font-size:11px; font-weight:900; cursor:pointer; transition:.18s ease; }
        .tab-btn { display:flex; align-items:center; gap:7px; background:rgba(255,255,255,.025); color:#929ca7; border:1px solid rgba(255,255,255,.06); }
        .tab-btn:hover { color:#fff; background:rgba(255,255,255,.05); }
        .tab-btn.active { color:white; background:var(--red); border-color:var(--red); box-shadow:0 8px 18px rgba(218,55,61,.18); }
        .tab-btn.running .status-dot { background:var(--green); box-shadow:0 0 9px rgba(35,165,90,.7); }
        .status-dot { width:7px; height:7px; border-radius:50%; background:#555d67; }
        .close-tab { color:#7d8691; font-size:15px; }
        .tab-btn.active .close-tab { color:rgba(255,255,255,.72); }
        .add-tab-btn { background:rgba(255,255,255,.025); border:1px dashed rgba(255,255,255,.16); color:#d8dde3; }
        .process-tab-content { display:none; }
        .process-tab-content.active { display:block; }
        .form-group { margin-top:17px; }
        label { display:block; margin-bottom:7px; color:#a9b0b9; font-size:10px; font-weight:900; text-transform:uppercase; letter-spacing:.08em; }
        input, textarea, select { width:100%; border:1px solid rgba(255,255,255,.08); outline:none; color:var(--text); background:var(--input); border-radius:10px; padding:12px 13px; font:13px Inter,sans-serif; transition:.18s ease; }
        input:focus, textarea:focus, select:focus { border-color:rgba(218,55,61,.7); box-shadow:0 0 0 3px rgba(218,55,61,.12); }
        textarea { min-height:170px; resize:vertical; line-height:1.55; }
        .field-hint { display:block; margin-top:6px; color:#707985; font-size:10px; line-height:1.5; }
        .pro-banner { margin-top:17px; padding:12px 13px; border:1px solid rgba(35,165,90,.23); border-radius:10px; background:rgba(35,165,90,.08); color:#8ce4ae; font-size:11px; font-weight:900; }
        .btn-group { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:18px; }
        .action-btn { width:100%; border:0; border-radius:10px; padding:13px; font-size:12px; font-weight:900; cursor:pointer; transition:.18s ease; }
        .btn-save { background:#22a35a; color:#fff; }
        .btn-clear { background:transparent; color:#99a2ad; border:1px dashed rgba(255,255,255,.14); }
        .btn-start { background:linear-gradient(180deg,#ee484e,#cb3036); color:white; box-shadow:0 12px 24px rgba(218,55,61,.16); }
        .btn-stop { background:#23262c; color:#f2f3f5; border:1px solid rgba(255,255,255,.08); }
        .action-btn:hover { transform:translateY(-1px); filter:brightness(1.04); }
        .status-container { margin-top:16px; padding:13px; display:flex; align-items:flex-start; gap:10px; border:1px solid rgba(255,255,255,.06); border-left:3px solid #515965; border-radius:10px; background:rgba(255,255,255,.025); color:#9da6b0; font-size:11px; min-height:48px; }
        .status-container.active { border-left-color:var(--green); color:#d6f5e1; }
        .status-container.error { border-left-color:var(--error); color:#ffd9da; }
        .status-dot-main { width:8px; height:8px; margin-top:3px; border-radius:50%; background:#5c6068; flex:none; }
        .status-container.active .status-dot-main { background:var(--green); box-shadow:0 0 10px rgba(35,165,90,.7); }
        .status-container.error .status-dot-main { background:var(--error); }
        .security-note { margin-top:18px; padding-top:15px; border-top:1px solid var(--line); color:#707985; font-size:10px; line-height:1.6; }
        @media (max-width:920px) { .layout { grid-template-columns:1fr; } .sidebar { position:static; } }
        @media (max-width:620px) { .shell { width:min(100% - 16px,1400px); } .topbar { padding:15px 0; } .top-actions .top-btn:first-child { display:none; } .btn-group { grid-template-columns:1fr; } .header { flex-direction:column; } }
        @media (prefers-reduced-motion:reduce) { *,*::before,*::after { transition:none !important; } }
    </style>
</head>
<body>
<div class="shell">
    <div class="topbar">
        <a class="brand" href="/"><svg viewBox="0 0 24 24" fill="none" stroke="#ff5d63" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8A2.5 2.5 0 0 1 17.5 16H9l-4.5 4V5.5Z"/><path d="M8 8h8M8 11h5"/></svg><span>AutoSender <span>v3</span></span></a>
        <div class="top-actions"><a class="top-btn" href="/">Home</a><a class="top-btn" href="/app">Free</a><a class="top-btn" href="https://discord.gg/6feS4msabZ" target="_blank" rel="noopener">Discord</a></div>
    </div>
    <div class="layout">
        <aside class="sidebar">
            <span class="badge">Pro Unlimited</span>
            <h1>Go further.</h1>
            <p>Use an active Pro key to keep the existing multi-process workflow and remove the Free-tier limits and watermark.</p>
            <ul class="pro-list"><li><strong>Messages:</strong> unlimited while Pro is active</li><li><strong>Watermark:</strong> disabled</li><li><strong>Processes:</strong> multiple tabs</li><li><strong>Checks:</strong> key + token + channel validation</li></ul>
            <div class="side-cta"><a class="free" href="/app">Back to Free</a><a class="discord" href="https://discord.gg/6feS4msabZ" target="_blank" rel="noopener">Join Discord</a></div>
        </aside>
        <section class="card">
            <div class="header"><div class="header-title"><h2>AutoSender <span>PRO</span></h2></div><span class="badge">Unlimited</span></div>
            <div class="pro-intro">Pro keeps the setup you already know. Enter an active key, add your process details, and use the same start/stop controls across as many Pro tabs as you need.</div>
            <div class="rules-card"><strong>Quick checks before starting</strong><ul><li>License key: paste it exactly. Remove commas, quotes, or accidental spaces.</li><li>Token: paste the full value as one continuous string. Recheck the token if it fails.</li><li>Channel ID: digits only. Recheck the correct channel and account access.</li><li>Keep credentials private and never post them in screenshots or chats.</li><li>Use the tool only where you have permission and follow Discord and server rules.</li></ul></div>
            <div class="tabs-bar" id="tabsBar"><button class="tab-btn active" id="tab-btn-1" onclick="switchTab(1)"><span class="status-dot"></span> Process #1</button><button class="add-tab-btn" onclick="addNewProcessTab()">+</button></div>
            <div id="tabContents">
                <div class="process-tab-content active" id="process-content-1">
                    <div class="form-group"><label>License Key</label><input type="text" class="input-key" autocomplete="off" spellcheck="false" placeholder="Enter active Pro key"><span class="field-hint">No commas, quotes, or extra spaces.</span></div>
                    <div class="form-group"><label>Discord Account Token</label><input type="password" class="input-token" autocomplete="off" spellcheck="false" placeholder="Paste token exactly as provided"><span class="field-hint">If copied from a list, remove commas, quotes, or line breaks.</span></div>
                    <div class="form-group"><label>Discord Channel ID</label><input type="text" class="input-channel" inputmode="numeric" autocomplete="off" spellcheck="false" placeholder="109283746592817264"><span class="field-hint">Digits only. No commas or spaces.</span></div>
                    <div class="form-group"><label>Message Content</label><textarea class="input-message" rows="6" placeholder="Paste your multi-line message here...&#10;Line 1&#10;Line 2"></textarea></div>
                    <div class="form-group"><label>Interval <span style="font-weight:400;color:#5c6068">(Min. 10 Sec)</span></label><div style="display:flex;gap:10px"><input type="number" class="input-interval-val" value="1" min="1"><select class="input-interval-unit"><option value="1">Seconds</option><option value="60" selected>Minutes</option></select></div></div>
                    <div class="pro-banner">Pro mode: watermark disabled and unlimited message dispatching when the key validates.</div>
                    <div class="btn-group"><button class="action-btn btn-save" onclick="saveAllProConfigs()">Save All Tabs</button><button class="action-btn btn-clear" onclick="clearProConfigs()">Clear Storage</button></div>
                    <div class="btn-group"><button class="action-btn btn-start" onclick="startProcess(1)">Start Pro Process</button><button class="action-btn btn-stop" onclick="stopProcess(1)">Stop Process</button></div>
                    <div class="status-container" id="status-1"><div class="status-dot-main"></div><span class="status-text">Status: Waiting for Pro key activation...</span></div>
                </div>
            </div>
            <div class="security-note">Tip: if Pro behaves like Free, verify that the key is active and reload the page so the latest key list is checked again.</div>
        </section>
    </div>
</div>
<script>
        let tabCount = 1;

        window.addEventListener('load', () => {
            loadProConfigs();
        });

        window.addEventListener('beforeunload', () => {
            navigator.sendBeacon('/api/stopall');
        });

        function saveAllProConfigs() {
            const configs = [];
            const activeContents = document.querySelectorAll('.process-tab-content');

            activeContents.forEach((c) => {
                configs.push({
                    key: c.querySelector('.input-key').value,
                    token: c.querySelector('.input-token').value,
                    channelId: c.querySelector('.input-channel').value,
                    message: c.querySelector('.input-message').value,
                    intervalVal: c.querySelector('.input-interval-val').value,
                    intervalUnit: c.querySelector('.input-interval-unit').value
                });
            });

            localStorage.setItem('autosender_pro_config', JSON.stringify(configs));
            
            activeContents.forEach((c, idx) => {
                const statusText = c.querySelector('.status-text');
                if (statusText) statusText.innerText = 'All Pro tab configurations saved!';
            });
        }

        function loadProConfigs() {
            const savedData = localStorage.getItem('autosender_pro_config');
            if (savedData) {
                try {
                    const configs = JSON.parse(savedData);
                    if (Array.isArray(configs) && configs.length > 0) {
                        // Fill tab 1
                        fillTabFields(1, configs[0]);
                        
                        // Dynamically re-create extra tabs if saved
                        for (let i = 1; i < configs.length; i++) {
                            addNewProcessTab();
                            fillTabFields(tabCount, configs[i]);
                        }

                        const activeContents = document.querySelectorAll('.process-tab-content');
                        activeContents.forEach((c) => {
                            const statusText = c.querySelector('.status-text');
                            if (statusText) statusText.innerText = 'Saved Pro session restored!';
                        });
                    }
                } catch (e) {
                    console.error('Failed to load Pro config:', e);
                }
            }
        }

        function fillTabFields(id, config) {
            const content = document.getElementById(`process-content-${id}`);
            if (!content || !config) return;

            if (config.key) content.querySelector('.input-key').value = config.key;
            if (config.token) content.querySelector('.input-token').value = config.token;
            if (config.channelId) content.querySelector('.input-channel').value = config.channelId;
            if (config.message) content.querySelector('.input-message').value = config.message;
            if (config.intervalVal) content.querySelector('.input-interval-val').value = config.intervalVal;
            if (config.intervalUnit) content.querySelector('.input-interval-unit').value = config.intervalUnit;
        }

        function clearProConfigs() {
            localStorage.removeItem('autosender_pro_config');
            location.reload();
        }

        function switchTab(id) {
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.process-tab-content').forEach(c => c.classList.remove('active'));

            const selectedBtn = document.getElementById(`tab-btn-${id}`);
            const selectedContent = document.getElementById(`process-content-${id}`);

            if (selectedBtn && selectedContent) {
                selectedBtn.classList.add('active');
                selectedContent.classList.add('active');
            }
        }

        function addNewProcessTab() {
            tabCount++;
            const tabId = tabCount;

            const tabsBar = document.getElementById('tabsBar');
            const addBtn = tabsBar.querySelector('.add-tab-btn');

            const newTabBtn = document.createElement('button');
            newTabBtn.className = 'tab-btn';
            newTabBtn.id = `tab-btn-${tabId}`;
            newTabBtn.onclick = () => switchTab(tabId);
            newTabBtn.innerHTML = `<span class="status-dot"></span> Process #${tabId} <span class="close-tab" onclick="closeTab(event, ${tabId})">×</span>`;

            tabsBar.insertBefore(newTabBtn, addBtn);

            const tabContents = document.getElementById('tabContents');
            const newContent = document.createElement('div');
            newContent.className = 'process-tab-content';
            newContent.id = `process-content-${tabId}`;
            
            let mainKey = document.querySelector('#process-content-1 .input-key') ? document.querySelector('#process-content-1 .input-key').value : '';

            newContent.innerHTML = `
                <div class="form-group">
                    <label>License Key <span style="font-weight: 400; color: #5c6068;">(Inherited from Tab 1)</span></label>
                    <input type="text" class="input-key" value="${mainKey}" autocomplete="off" spellcheck="false" placeholder="Enter valid Pro key">
                    <span class="field-hint">No commas, quotes, or extra spaces.</span>
                </div>
                <div class="form-group">
                    <label>Discord Account Token</label>
                    <input type="password" class="input-token" autocomplete="off" spellcheck="false" placeholder="Paste token exactly as provided">
                    <span class="field-hint">Remove commas or accidental line breaks.</span>
                </div>
                <div class="form-group">
                    <label>Discord Channel ID</label>
                    <input type="text" class="input-channel" inputmode="numeric" autocomplete="off" spellcheck="false" placeholder="109283746592817264">
                    <span class="field-hint">Digits only. No commas or spaces.</span>
                </div>
                <div class="form-group">
                    <label>Message Content</label>
                    <textarea class="input-message" rows="6" placeholder="Paste your multi-line message here...&#10;Line 1&#10;Line 2"></textarea>
                </div>
                <div class="form-group">
                    <label>Interval <span style="font-weight: 400; color: #5c6068;">(Min. 10 Sec)</span></label>
                    <div style="display: flex; gap: 10px;">
                        <input type="number" class="input-interval-val" value="1" min="1" style="flex: 1;">
                        <select class="input-interval-unit" style="flex: 1;">
                            <option value="1">Seconds</option>
                            <option value="60" selected>Minutes</option>
                        </select>
                    </div>
                </div>
                <div class="pro-banner">
                    ✨ Pro Mode: Watermarks completely disabled & Unlimited messages active!
                </div>
                <div class="btn-group">
                    <button class="action-btn btn-save" onclick="saveAllProConfigs()">💾 Save All Tabs</button>
                    <button class="action-btn btn-clear" onclick="clearProConfigs()">🗑️ Clear Storage</button>
                </div>
                <div class="btn-group">
                    <button class="action-btn btn-start" onclick="startProcess(${tabId})">Start Pro Process</button>
                    <button class="action-btn btn-stop" onclick="stopProcess(${tabId})">Stop Process</button>
                </div>
                <div class="status-container" id="status-${tabId}">
                    <div class="status-dot-main"></div>
                    <span class="status-text">Status: Waiting for Pro Key activation...</span>
                </div>
            `;

            tabContents.appendChild(newContent);
            switchTab(tabId);
        }

        async function closeTab(event, id) {
            event.stopPropagation();
            
            await stopProcess(id);
            
            const tabBtn = document.getElementById(`tab-btn-${id}`);
            const tabContent = document.getElementById(`process-content-${id}`);
            if(tabBtn) tabBtn.remove();
            if(tabContent) tabContent.remove();
            
            switchTab(1);
        }

        function validateProFields(content) {
            const key = content.querySelector('.input-key').value.trim();
            const token = content.querySelector('.input-token').value.trim();
            const channelId = content.querySelector('.input-channel').value.trim();
            const message = content.querySelector('.input-message').value.trim();

            if (!key) return 'Enter your Pro license key first.';
            if (key.includes(',')) return 'Your Pro key contains a comma. Remove commas and paste the key exactly.';
            if (/\\s/.test(key)) return 'Your Pro key contains a space or line break. Paste the exact key as one continuous value.';
            if (!token) return 'Enter your token first.';
            if (token.includes(',')) return 'Your token contains a comma. Remove commas and paste the token exactly.';
            if (/\\s/.test(token)) return 'Your token contains a space or line break. Paste it as one continuous value.';
            if (!channelId) return 'Enter the Discord channel ID first.';
            if (!/^\\d+$/.test(channelId)) return 'Channel ID must contain digits only. Remove commas, spaces, or other characters.';
            if (!message) return 'Enter a message before starting the process.';
            return '';
        }

        async function startProcess(id) {
            const content = document.getElementById(`process-content-${id}`);
            const validationError = validateProFields(content);
            const statusBox = document.getElementById(`status-${id}`);
            const statusText = statusBox.querySelector('.status-text');
            if (validationError) {
                statusBox.className = 'status-container error';
                statusText.innerText = validationError;
                return;
            }
            const key = content.querySelector('.input-key').value.trim();
            const token = content.querySelector('.input-token').value.trim();
            const channelId = content.querySelector('.input-channel').value;
            const message = content.querySelector('.input-message').value;
            
            const intervalVal = parseInt(content.querySelector('.input-interval-val').value) || 1;
            const intervalUnit = parseInt(content.querySelector('.input-interval-unit').value) || 60;
            let totalSeconds = intervalVal * intervalUnit;
            if (totalSeconds < 10) totalSeconds = 10;

            try {
                const res = await fetch('/api/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        process_id: id,
                        key: key,
                        token: token,
                        channel_id: channelId,
                        message: message,
                        interval: totalSeconds
                    })
                });

                const data = await res.json();

                if (res.ok) {
                    statusBox.className = 'status-container active';
                    statusText.innerText = data.message;
                    document.getElementById(`tab-btn-${id}`).classList.add('running');
                } else {
                    statusBox.className = 'status-container error';
                    statusText.innerText = data.message || 'Error starting process.';
                }
            } catch (err) {
                statusBox.className = 'status-container error';
                statusText.innerText = 'Network Error: Cannot connect to server.';
            }
        }

        async function stopProcess(id) {
            const statusBox = document.getElementById(`status-${id}`);
            if(!statusBox) return;
            const statusText = statusBox.querySelector('.status-text');

            try {
                const res = await fetch('/api/stop', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ process_id: id })
                });

                const data = await res.json();
                statusBox.className = 'status-container';
                statusText.innerText = data.message;
                const tabBtn = document.getElementById(`tab-btn-${id}`);
                if(tabBtn) tabBtn.classList.remove('running');
            } catch (err) {
                statusBox.className = 'status-container error';
                statusText.innerText = 'Failed to stop process.';
            }
        }
    </script>
</html>
"""

# Resolve shared favicon placeholder used by the static premium templates.
HOME_TEMPLATE = HOME_TEMPLATE.replace("{FAVICON_URI}", FAVICON_URI)
FREE_TOOL_TEMPLATE = FREE_TOOL_TEMPLATE.replace("{FAVICON_URI}", FAVICON_URI)
PRO_TOOL_TEMPLATE = PRO_TOOL_TEMPLATE.replace("{FAVICON_URI}", FAVICON_URI)


# ==============================================================================
# 3. BACKGROUND WORKER & DISCORD POSTER LOGIC
# ==============================================================================
def background_poster(process_id, token, channel_id, message, interval_sec, is_pro_user):
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": token.strip(),
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT
    }

    token_hash = get_token_hash(token)

    # Initialize or migrate the usage record.
    get_free_usage(token_hash)

    while active_sessions.get(process_id, {}).get("is_running", False):
        
        # --- FREE LIMIT CHECK ---
        current_usage = get_free_usage(token_hash)
        
        if not is_pro_user and current_usage >= FREE_LIMIT:
            print(f"[PROCESS #{process_id} STOPPED] Token hit {FREE_LIMIT} daily limit cap.")
            active_sessions[process_id]["is_running"] = False
            break

        # Free-tier messages receive the promotional watermark; Pro messages stay untouched.
        if is_pro_user:
            send_message = message
        else:
            send_message = f"{message}\n\nSent via autosenderv3"
            if len(send_message) > 2000:
                send_message = send_message[:2000]
        payload = {"content": send_message}

        try:
            res = requests.post(url, headers=headers, json=payload, timeout=10)
            if res.status_code in (200, 201):
                if not is_pro_user:
                    current = increment_free_usage(token_hash)
                    print(f"[PROC #{process_id} SUCCESS] ({current}/{FREE_LIMIT} Free Msgs Used)")
                else:
                    print(f"[PROC #{process_id} PRO SUCCESS] Clean message dispatched without watermark!")
            elif res.status_code == 429:
                try:
                    error_data = res.json()
                    retry_after = error_data.get('retry_after', 1)
                except Exception:
                    retry_after = 1
                
                print(f"[PROC #{process_id} RATE LIMITED] Sleeping for {retry_after}s")
                time.sleep(retry_after)
            else:
                print(f"[PROC #{process_id} ERROR {res.status_code}] {res.text}")
        except Exception as e:
            print(f"[PROC #{process_id} ERROR] {e}")

        for _ in range(int(interval_sec)):
            if not active_sessions.get(process_id, {}).get("is_running", False):
                break
            time.sleep(1)

# ==============================================================================
# 4. FLASK ROUTES & API ENDPOINTS
# ==============================================================================
@app.route('/')
def home():
    return render_template_string(HOME_TEMPLATE)

@app.route('/app')
def tool():
    return render_template_string(FREE_TOOL_TEMPLATE)

@app.route('/pro')
def pro_tool():
    return render_template_string(PRO_TOOL_TEMPLATE)

@app.route('/api/start', methods=['POST'])
def start_bot():
    data = request.json or {}
    process_id = str(data.get('process_id', '1'))
    user_key = data.get('key', '').strip()
    token = data.get('token', '').strip()
    channel_id = data.get('channel_id', '').strip()
    message = data.get('message', '').strip()
    
    try:
        interval_sec = int(data.get('interval', 60))
        if interval_sec < 10:
            interval_sec = 10
    except ValueError:
        interval_sec = 60

    if not token or not channel_id:
        return jsonify({"message": "Discord Token and Channel ID are required!"}), 400

    # Key validation: verify key against remote list
    is_pro = verify_key(user_key) if user_key else False
    
    # ENFORCE FREE SINGLE-PROCESS RULE:
    if not is_pro and process_id != '1':
        return jsonify({
            "message": "Free Tier is restricted to Process #1 only. Upgrade to Pro for multi-process automation."
        }), 403

    token_hash = get_token_hash(token)

    # Get today's usage, automatically resetting the free counter on a new day.
    current_usage = get_free_usage(token_hash)

    # Enforce limit ONLY if user key is not valid (Free tier)
    if not is_pro and current_usage >= FREE_LIMIT:
        return jsonify({
            "message": f"Free limit of {FREE_LIMIT} messages reached for this token! Enter a valid Pro key to get unlimited access."
        }), 403

    # Stop process if already running on this tab
    if process_id in active_sessions:
        active_sessions[process_id]["is_running"] = False

    active_sessions[process_id] = {"is_running": True}

    worker_thread = threading.Thread(
        target=background_poster,
        args=(process_id, token, channel_id, message, interval_sec, is_pro),
        daemon=True
    )
    worker_thread.start()

    status_msg = "Process Running (Pro License Active)" if is_pro else f"Process Running (Free Tier: {current_usage}/{FREE_LIMIT} Used)"
    return jsonify({"message": status_msg, "is_pro": is_pro}), 200

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    data = request.json or {}
    process_id = str(data.get('process_id'))

    if process_id in active_sessions:
        active_sessions[process_id]["is_running"] = False
        return jsonify({"message": f"Process #{process_id} Stopped."}), 200

    return jsonify({"message": f"Process #{process_id} is not running."}), 400

@app.route('/api/stopall', methods=['POST'])
def stop_all_bots():
    for pid in active_sessions:
        active_sessions[pid]["is_running"] = False
    return jsonify({"message": "All active processes stopped."}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
