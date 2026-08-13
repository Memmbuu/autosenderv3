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


# Browser-instance aware process keys. This prevents two browser tabs from
# accidentally sharing Process #1 and stopping each other.
def make_session_key(client_id, process_id):
    client_id = str(client_id or "legacy").strip() or "legacy"
    process_id = str(process_id or "1").strip() or "1"
    return f"{client_id}:{process_id}"


def stop_client_sessions(client_id):
    prefix = f"{str(client_id or 'legacy').strip() or 'legacy'}:"
    for session_key, session in list(active_sessions.items()):
        if session_key.startswith(prefix):
            session["is_running"] = False


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
HOME_TEMPLATE = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoSender v3 - Next-Gen Discord Automation</title>
    <link rel="icon" type="image/svg+xml" href="{FAVICON_URI}">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-primary: #0b0c0e;
            --bg-secondary: #121316;
            --bg-card: #1a1b1e;
            --accent-red: #da373d;
            --accent-red-hover: #ff474d;
            --discord-blurple: #5865F2;
            --discord-hover: #4752C4;
            --text-normal: #f2f3f5;
            --text-muted: #949ba4;
            --border-color: rgba(255, 255, 255, 0.08);
            --blur-bg: rgba(18, 19, 22, 0.85);
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }}

        ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
        ::-webkit-scrollbar-track {{ background: var(--bg-primary); border-radius: 4px; }}
        ::-webkit-scrollbar-thumb {{ background: #1f2023; border-radius: 4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: var(--accent-red); }}

        body {{
            background-color: var(--bg-primary);
            color: var(--text-normal);
            overflow-x: hidden;
        }}

        header {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            z-index: 1000;
            background: var(--blur-bg);
            backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--border-color);
            padding: 16px 40px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .logo {{
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 20px;
            font-weight: 800;
            letter-spacing: -0.5px;
            text-decoration: none;
            color: var(--text-normal);
        }}

        .logo span {{ color: var(--accent-red); }}

        nav {{
            display: flex;
            align-items: center;
            gap: 20px;
        }}

        nav a {{
            color: var(--text-muted);
            text-decoration: none;
            font-size: 14px;
            font-weight: 600;
            transition: color 0.2s ease;
        }}

        nav a:hover {{ color: var(--text-normal); }}

        .discord-nav-btn {{
            background-color: rgba(88, 101, 242, 0.15);
            color: #5865F2 !important;
            border: 1px solid rgba(88, 101, 242, 0.4);
            padding: 8px 14px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s ease;
        }}

        .discord-nav-btn:hover {{
            background-color: var(--discord-blurple);
            color: #ffffff !important;
        }}

        .nav-btn {{
            background-color: var(--accent-red);
            color: #ffffff !important;
            padding: 8px 18px;
            border-radius: 8px;
            transition: all 0.2s ease;
            box-shadow: 0 4px 14px rgba(218, 55, 61, 0.3);
        }}

        .nav-btn:hover {{
            background-color: var(--accent-red-hover);
            transform: translateY(-1px);
        }}

        .hero {{
            padding: 160px 40px 80px;
            max-width: 1200px;
            margin: 0 auto;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 60px;
            align-items: center;
        }}

        .hero-text h1 {{
            font-size: 54px;
            font-weight: 900;
            line-height: 1.1;
            letter-spacing: -1.5px;
            margin-bottom: 24px;
        }}

        .hero-text h1 span {{
            background: linear-gradient(135deg, #da373d 0%, #ff7377 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .hero-text p {{
            font-size: 16px;
            color: var(--text-muted);
            line-height: 1.6;
            margin-bottom: 36px;
        }}

        .hero-actions {{
            display: flex;
            gap: 16px;
        }}

        .btn-primary {{
            background-color: var(--accent-red);
            color: #ffffff;
            text-decoration: none;
            font-size: 15px;
            font-weight: 700;
            padding: 14px 28px;
            border-radius: 8px;
            transition: all 0.2s ease;
            box-shadow: 0 6px 20px rgba(218, 55, 61, 0.4);
            display: inline-block;
        }}

        .btn-primary:hover {{
            background-color: var(--accent-red-hover);
            transform: translateY(-2px);
        }}

        .btn-secondary {{
            background-color: var(--bg-card);
            color: var(--text-normal);
            text-decoration: none;
            font-size: 15px;
            font-weight: 600;
            padding: 14px 28px;
            border-radius: 8px;
            border: 1px solid var(--border-color);
            transition: all 0.2s ease;
        }}

        .btn-secondary:hover {{ background-color: #24262b; }}

        .terminal-card {{
            background: #0d0e11;
            border: 1px solid var(--border-color);
            border-radius: 14px;
            overflow: hidden;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6);
        }}

        .terminal-header {{
            background: #16181d;
            padding: 12px 18px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
        }}

        .window-controls {{ display: flex; gap: 8px; }}
        .control-dot {{ width: 10px; height: 10px; border-radius: 50%; }}
        .dot-red {{ background-color: #ff5f56; }}
        .dot-yellow {{ background-color: #ffbd2e; }}
        .dot-green {{ background-color: #27c93f; }}

        .terminal-title {{
            font-size: 12px;
            color: var(--text-muted);
            font-family: 'Fira Code', monospace;
            font-weight: 500;
        }}

        .terminal-body {{
            padding: 20px;
            font-family: 'Fira Code', monospace;
            font-size: 12px;
            height: 250px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 10px;
            background-color: #0b0c0e;
        }}

        .log-entry {{ line-height: 1.5; display: flex; gap: 10px; }}
        .log-time {{ color: #5c6068; }}
        .log-tag {{ color: var(--accent-red); font-weight: 700; }}
        .log-text {{ color: #d1d5db; }}
        .log-success {{ color: #23a55a; }}

        .terminal-footer {{
            padding: 12px 18px;
            background-color: #121316;
            border-top: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .terminal-footer button {{
            background: var(--accent-red);
            color: #fff;
            border: none;
            padding: 6px 14px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 700;
            cursor: pointer;
            transition: background 0.2s;
        }}

        .terminal-footer button:hover {{ background: var(--accent-red-hover); }}

        /* --- PRO TOOL SECTION STYLES --- */
        .pro-tool-section {{
            max-width: 1100px;
            margin: 0 auto 60px;
            padding: 0 40px;
        }}

        .pro-tool-card {{
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 40px;
            display: flex;
            flex-direction: column;
            gap: 24px;
            position: relative;
            box-shadow: 0 10px 30px rgba(0,0,0,0.4);
        }}

        .pro-tool-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
        }}

        .pro-badge {{
            background-color: rgba(35, 165, 90, 0.15);
            color: #23a55a;
            font-size: 11px;
            font-weight: 800;
            padding: 4px 10px;
            border-radius: 20px;
            text-transform: uppercase;
            border: 1px solid rgba(35, 165, 90, 0.3);
            display: inline-block;
        }}

        .pro-tool-header h2 {{
            font-size: 32px;
            font-weight: 800;
            margin-top: 8px;
        }}

        .pro-tool-desc {{
            color: var(--text-muted);
            font-size: 15px;
            line-height: 1.6;
        }}

        .pro-features-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-top: 10px;
        }}

        .pro-feature-card {{
            background: var(--bg-card);
            padding: 20px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
        }}

        .pro-feature-card h4 {{
            color: var(--accent-red);
            margin-bottom: 6px;
            font-size: 16px;
        }}

        .pro-feature-card p {{
            color: var(--text-muted);
            font-size: 13px;
        }}

        .discord-section {{
            max-width: 1100px;
            margin: 0 auto 60px;
            padding: 0 40px;
        }}

        .discord-card {{
            background: linear-gradient(135deg, rgba(88, 101, 242, 0.12) 0%, rgba(18, 19, 22, 0.8) 100%);
            border: 1px solid rgba(88, 101, 242, 0.3);
            border-radius: 16px;
            padding: 32px 40px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 24px;
        }}

        .discord-info {{ display: flex; align-items: center; gap: 20px; }}

        .discord-icon-wrapper {{
            background: var(--discord-blurple);
            width: 56px;
            height: 56px;
            border-radius: 14px;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 8px 20px rgba(88, 101, 242, 0.35);
        }}

        .discord-text h3 {{ font-size: 20px; font-weight: 800; margin-bottom: 4px; }}
        .discord-text p {{ font-size: 14px; color: var(--text-muted); }}

        .btn-discord {{
            background-color: var(--discord-blurple);
            color: #ffffff;
            text-decoration: none;
            font-size: 14px;
            font-weight: 700;
            padding: 12px 24px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            gap: 10px;
            white-space: nowrap;
            transition: all 0.2s ease;
            box-shadow: 0 4px 16px rgba(88, 101, 242, 0.4);
        }}

        .btn-discord:hover {{
            background-color: var(--discord-hover);
            transform: translateY(-2px);
        }}

        .pricing-section {{
            max-width: 1100px;
            margin: 0 auto;
            padding: 40px 40px 100px;
        }}

        .section-title {{ text-align: center; margin-bottom: 60px; }}
        .section-title h2 {{ font-size: 36px; font-weight: 800; letter-spacing: -1px; }}
        .section-title p {{ color: var(--text-muted); margin-top: 10px; }}

        .pricing-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 24px;
        }}

        .price-card {{
            background-color: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 32px 24px;
            display: flex;
            flex-direction: column;
            transition: all 0.3s ease;
            position: relative;
        }}

        .price-card:hover {{
            transform: translateY(-6px);
            border-color: var(--accent-red);
        }}

        .price-card.popular {{
            border-color: var(--accent-red);
            box-shadow: 0 0 30px rgba(218, 55, 61, 0.2);
        }}

        .popular-tag {{
            position: absolute;
            top: -12px;
            right: 24px;
            background-color: var(--accent-red);
            color: #ffffff;
            font-size: 10px;
            font-weight: 800;
            padding: 4px 10px;
            border-radius: 20px;
            text-transform: uppercase;
        }}

        .price-card h3 {{ font-size: 18px; font-weight: 700; margin-bottom: 8px; }}
        .price {{ font-size: 38px; font-weight: 900; margin-bottom: 16px; }}
        .price span {{ font-size: 14px; color: var(--text-muted); font-weight: 500; }}

        .features-list {{
            list-style: none;
            margin: 24px 0 32px;
            flex-grow: 1;
        }}

        .features-list li {{
            font-size: 13px;
            color: var(--text-muted);
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .features-list li::before {{
            content: "✓";
            color: var(--accent-red);
            font-weight: 800;
        }}

        @media (max-width: 900px) {{
            .hero {{ grid-template-columns: 1fr; }}
            .pricing-grid {{ grid-template-columns: 1fr; }}
            .discord-card {{ flex-direction: column; text-align: center; }}
            .discord-info {{ flex-direction: column; }}
        }}
    </style>
</head>
<body>

    <header>
        <a href="/" class="logo">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#da373d" stroke-width="2.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
            AutoSender <span>v3</span>
        </a>
        <nav>
            <a href="/">Home</a>
            <a href="#pro-tool">Pro Tool</a>
            <a href="#pricing">Pricing</a>
            <a href="https://discord.gg/X8KuxXM5r" target="_blank" class="discord-nav-btn">
                <svg width="18" height="18" viewBox="0 0 127.14 96.36" fill="currentColor">
                    <path d="M107.7,8.07A105.15,105.15,0,0,0,81.47,0a72.06,72.06,0,0,0-3.36,6.83A97.68,97.68,0,0,0,49,6.83,72.37,72.37,0,0,0,45.64,0,105.89,105.89,0,0,0,19.39,8.09C2.79,32.65-1.71,56.6.54,80.21h0A105.73,105.73,0,0,0,32.71,96.36,77.7,77.7,0,0,0,39.6,85.25a68.42,68.42,0,0,1-10.85-5.18c.91-.66,1.8-1.34,2.66-2a75.57,75.57,0,0,0,64.32,0c.87.71,1.76,1.39,2.66,2a68.68,68.68,0,0,1-10.87,5.19,77,77,0,0,0,6.89,11.1,105.25,105.25,0,0,0,32.19-16.14c2.64-27.38-4.51-51.11-18.91-72.15ZM42.45,65.69C36.18,65.69,31,60,31,53s5-12.74,11.43-12.74S54,45.91,53.87,53,48.83,65.69,42.45,65.69Zm42.24,0C78.41,65.69,73.25,60,73.25,53s5-12.74,11.44-12.74S96.23,45.91,96.1,53,91.08,65.69,84.69,65.69Z"/>
                </svg>
                Discord
            </a>
            <a href="/app" class="nav-btn">Launch Tool</a>
        </nav>
    </header>

    <section class="hero">
        <div class="hero-text">
            <h1>Automate Discord Messages <span>24/7 Effortlessly</span></h1>
            <p>Keep your services, offers, and advertisements visible across multiple Discord channels simultaneously without lifting a finger.</p>
            <div class="hero-actions">
                <a href="/app" class="btn-primary">Open Free Dashboard</a>
                <a href="/pro" class="btn-secondary" style="border-color: var(--accent-red); color: var(--accent-red);">Launch Pro Tool</a>
            </div>
        </div>

        <div class="terminal-card">
            <div class="terminal-header">
                <div class="window-controls">
                    <span class="control-dot dot-red"></span>
                    <span class="control-dot dot-yellow"></span>
                    <span class="control-dot dot-green"></span>
                </div>
                <div class="terminal-title">autosender-engine.log</div>
            </div>
            <div class="terminal-body" id="terminalLogs">
                <div class="log-entry">
                    <span class="log-time">[SYSTEM]</span>
                    <span class="log-tag">[INIT]</span>
                    <span class="log-text">AutoSender Engine v3.0 loaded...</span>
                </div>
                <div class="log-entry">
                    <span class="log-time">[SYSTEM]</span>
                    <span class="log-tag">[FREE]</span>
                    <span class="log-success">300 Free Messages Tier Active!</span>
                </div>
                <div class="log-entry">
                    <span class="log-time">[12:00:01]</span>
                    <span class="log-tag">[PROC #1]</span>
                    <span class="log-text">Connecting to channel ID: 109283...</span>
                </div>
                <div class="log-entry">
                    <span class="log-time">[12:00:02]</span>
                    <span class="log-tag">[PROC #1]</span>
                    <span class="log-success">HTTP 200 OK — Message dispatched (+Watermark)</span>
                </div>
            </div>
            <div class="terminal-footer">
                <span style="font-size: 11px; color: var(--text-muted);">Status: <strong style="color: #23a55a;">ONLINE</strong></span>
                <button onclick="triggerDemoLog()">Run Test Log</button>
            </div>
        </div>
    </section>

    <section class="pro-tool-section" id="pro-tool">
        <div class="pro-tool-card">
            <div class="pro-tool-header">
                <div>
                    <span class="pro-badge">PRO EDITION</span>
                    <h2>Pro Tool Automation Suite</h2>
                </div>
                <a href="/pro" class="btn-primary">Launch Pro Tool Dashboard →</a>
            </div>
            <p class="pro-tool-desc">
                Unlock full control with our premium automation suite. Execute multiple channel processes simultaneously without watermarks, custom delays, and continuous multi-token dispatching.
            </p>
            <div class="pro-features-grid">
                <div class="pro-feature-card">
                    <h4>Multi-Process Automation</h4>
                    <p>Run unlimited parallel process tabs at the same time across different channels.</p>
                </div>
                <div class="pro-feature-card">
                    <h4>Zero Watermarks</h4>
                    <p>Clean message output with no promotional footers or watermarks appended.</p>
                </div>
                <div class="pro-feature-card">
                    <h4>Unlimited Dispatching</h4>
                    <p>Bypass the 300-message limit completely with lifetime & pro key licenses.</p>
                </div>
            </div>
        </div>
    </section>

    <section class="discord-section">
        <div class="discord-card">
            <div class="discord-info">
                <div class="discord-icon-wrapper">
                    <svg width="32" height="32" viewBox="0 0 127.14 96.36" fill="#ffffff">
                        <path d="M107.7,8.07A105.15,105.15,0,0,0,81.47,0a72.06,72.06,0,0,0-3.36,6.83A97.68,97.68,0,0,0,49,6.83,72.37,72.37,0,0,0,45.64,0,105.89,105.89,0,0,0,19.39,8.09C2.79,32.65-1.71,56.6.54,80.21h0A105.73,105.73,0,0,0,32.71,96.36,77.7,77.7,0,0,0,39.6,85.25a68.42,68.42,0,0,1-10.85-5.18c.91-.66,1.8-1.34,2.66-2a75.57,75.57,0,0,0,64.32,0c.87.71,1.76,1.39,2.66,2a68.68,68.68,0,0,1-10.87,5.19,77,77,0,0,0,6.89,11.1,105.25,105.25,0,0,0,32.19-16.14c2.64-27.38-4.51-51.11-18.91-72.15ZM42.45,65.69C36.18,65.69,31,60,31,53s5-12.74,11.43-12.74S54,45.91,53.87,53,48.83,65.69,42.45,65.69Zm42.24,0C78.41,65.69,73.25,60,73.25,53s5-12.74,11.44-12.74S96.23,45.91,96.1,53,91.08,65.69,84.69,65.69Z"/>
                    </svg>
                </div>
                <div class="discord-text">
                    <h3>Join Our Discord Community</h3>
                    <p>Get instant support, request free key giveaways, and chat with members.</p>
                </div>
            </div>
            <a href="https://discord.gg/X8KuxXM5r" target="_blank" class="btn-discord">
                Join Discord Server →
            </a>
        </div>
    </section>

    <section class="pricing-section" id="pricing">
        <div class="section-title">
            <h2>Flexible License Plans</h2>
            <p>Start free with 300 messages every day or upgrade for unlimited watermark-free access.</p>
        </div>

        <div class="pricing-grid">
            <div class="price-card">
                <h3>Free Tier</h3>
                <div class="price">$0 <span>/ forever</span></div>
                <ul class="features-list">
                    <li>300 Free Messages Daily</li>
                    <li>Automatic Free-Tier Watermark</li>
                    <li>Single Process Tab Only</li>
                    <li>Community Support</li>
                </ul>
                <a href="/app" class="btn-secondary" style="text-align: center;">Try Free Now</a>
            </div>

            <div class="price-card popular">
                <div class="popular-tag">MOST POPULAR</div>
                <h3>Pro Key Tier</h3>
                <div class="price">$9.99 <span>/ month</span></div>
                <ul class="features-list">
                    <li>Unlimited Parallel Tab Processes</li>
                    <li><strong>No Message Watermarks</strong></li>
                    <li>Unlimited Lifetime Messages</li>
                    <li>Priority Backend Dispatch</li>
                </ul>
                <a href="/pro" class="btn-primary" style="text-align: center;">Launch Pro Tool</a>
            </div>

            <div class="price-card">
                <h3>Lifetime Pass</h3>
                <div class="price">$29.99 <span>/ one-time</span></div>
                <ul class="features-list">
                    <li>Lifetime Unlimited Access</li>
                    <li>No Watermarks Ever</li>
                    <li>Custom User-Agent Spoofing</li>
                    <li>24/7 Dedicated Discord Support</li>
                </ul>
                <a href="/pro" class="btn-secondary" style="text-align: center;">Get Lifetime</a>
            </div>
        </div>
    </section>

    <script>
        function triggerDemoLog() {{
            const terminal = document.getElementById('terminalLogs');
            const now = new Date().toTimeString().split(' ')[0];
            const sampleLogs = [
                `<div class="log-entry"><span class="log-time">[${{now}}]</span> <span class="log-tag">[PROC #1]</span> <span class="log-text">Triggering scheduled payload...</span></div>`,
                `<div class="log-entry"><span class="log-time">[${{now}}]</span> <span class="log-tag">[PROC #1]</span> <span class="log-success">HTTP 200 OK — Sent (3/300 free used)</span></div>`,
                `<div class="log-entry"><span class="log-time">[${{now}}]</span> <span class="log-tag">[SYSTEM]</span> <span class="log-text">Interval sleep initialized for 60s.</span></div>`
            ];
            
            sampleLogs.forEach((log, index) => {{
                setTimeout(() => {{
                    terminal.innerHTML += log;
                    terminal.scrollTop = terminal.scrollHeight;
                }}, index * 400);
            }});
        }}
    </script>
</body>
</html>
"""

# ==============================================================================
# 2. AUTO-SENDER DASHBOARD (FREE) HTML & CSS
# ==============================================================================
FREE_TOOL_TEMPLATE = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoSender v3 - Free Process Dashboard</title>
    <link rel="icon" type="image/svg+xml" href="{FAVICON_URI}">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-primary: #1e1f22;
            --bg-secondary: #2b2d31;
            --bg-tertiary: #313338;
            --accent-red: #da373d;
            --accent-red-hover: #a12828;
            --text-normal: #f2f3f5;
            --text-muted: #949ba4;
            --input-bg: #1e1f22;
            --success-color: #23a55a;
            --error-color: #f23f43;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }}

        ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
        ::-webkit-scrollbar-track {{ background: var(--bg-primary); border-radius: 4px; }}
        ::-webkit-scrollbar-thumb {{ background: #111214; border-radius: 4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: var(--accent-red); }}

        body {{
            background-color: var(--bg-primary);
            color: var(--text-normal);
            display: flex;
            flex-direction: column;
            align-items: center;
            min-height: 100vh;
        }}

        .top-nav {{
            width: 100%;
            background-color: #111214;
            padding: 12px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            margin-bottom: 30px;
        }}

        .top-nav a {{
            color: var(--text-muted);
            text-decoration: none;
            font-size: 13px;
            font-weight: 600;
            transition: color 0.2s;
        }}

        .top-nav a:hover {{ color: var(--text-normal); }}

        .tool-container {{
            width: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 0 20px 40px;
        }}

        .card {{
            background-color: var(--bg-secondary);
            width: 100%;
            max-width: 520px;
            padding: 28px;
            border-radius: 12px;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
            border: 1px solid rgba(255, 255, 255, 0.05);
        }}

        .header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 20px;
            padding-bottom: 16px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }}

        .header-title h2 {{ font-size: 20px; font-weight: 700; }}
        .badge {{
            background-color: rgba(218, 55, 61, 0.15);
            color: var(--accent-red);
            font-size: 11px;
            font-weight: 700;
            padding: 4px 8px;
            border-radius: 6px;
            text-transform: uppercase;
            border: 1px solid rgba(218, 55, 61, 0.3);
        }}

        .form-group {{ margin-bottom: 16px; }}

        label {{
            display: block;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-bottom: 6px;
            letter-spacing: 0.5px;
        }}

        input[type="text"],
        input[type="number"],
        textarea.input-message,
        select.input-interval-unit {{
            width: 100%;
            padding: 10px 12px;
            background-color: var(--input-bg);
            border: 1px solid rgba(0, 0, 0, 0.3);
            border-radius: 6px;
            color: var(--text-normal);
            font-size: 13px;
            outline: none;
            transition: all 0.2s ease;
            font-family: inherit;
        }}

        textarea.input-message {{
            resize: vertical;
            min-height: 100px;
            line-height: 1.4;
        }}

        input[type="text"]:focus,
        input[type="number"]:focus,
        textarea.input-message:focus,
        select.input-interval-unit:focus {{
            border-color: var(--accent-red);
            box-shadow: 0 0 0 2px rgba(218, 55, 61, 0.25);
        }}

        .btn-group {{
            display: flex;
            gap: 10px;
            margin-top: 15px;
        }}

        button.action-btn {{
            flex: 1;
            padding: 12px;
            border: none;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .btn-start {{
            background-color: var(--accent-red);
            color: #ffffff;
        }}

        .btn-start:hover {{ background-color: var(--accent-red-hover); }}

        .btn-stop {{
            background-color: var(--bg-tertiary);
            color: var(--text-normal);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}

        .btn-stop:hover {{ background-color: #3f4248; }}

        .btn-save {{
            background-color: #23a55a;
            color: #ffffff;
        }}
        .btn-save:hover {{ background-color: #1f904e; }}

        .btn-clear {{
            background-color: transparent;
            color: var(--text-muted);
            border: 1px dashed rgba(255, 255, 255, 0.2);
        }}
        .btn-clear:hover {{ color: var(--error-color); border-color: var(--error-color); }}

        .status-container {{
            margin-top: 16px;
            padding: 10px 12px;
            background-color: var(--bg-tertiary);
            border-radius: 6px;
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 12px;
            color: var(--text-muted);
            border-left: 3px solid #5c6068;
        }}

        .status-dot-main {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background-color: #5c6068;
        }}

        .status-container.active {{
            border-left-color: var(--success-color);
            color: var(--text-normal);
        }}
        .status-container.active .status-dot-main {{
            background-color: var(--success-color);
            box-shadow: 0 0 8px var(--success-color);
        }}

        .status-container.error {{
            border-left-color: var(--error-color);
            color: var(--text-normal);
        }}
        .status-container.error .status-dot-main {{
            background-color: var(--error-color);
        }}
    </style>
</head>
<body>

    <div class="top-nav">
        <a href="/">← Back to Home Page</a>
    </div>

    <div class="tool-container">
        <div class="card">
            <div class="header">
                <div class="header-title">
                    <h2>AutoSender <span>v3</span></h2>
                </div>
                <span class="badge">Free Mode</span>
            </div>

            <div id="process-content-1">
                <div class="form-group">
                    <label>Discord Account Token</label>
                    <input type="text" class="input-token" placeholder="mfa.X9k1...">
                </div>
                <div class="form-group">
                    <label>Discord Channel ID</label>
                    <input type="text" class="input-channel" placeholder="109283746592817264">
                </div>
                <div class="form-group">
                    <label>Message Content</label>
                    <textarea class="input-message" rows="6" placeholder="Paste your formatted message here...&#10;Line 1&#10;Line 2"></textarea>
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

                <div class="btn-group">
                    <button class="action-btn btn-save" onclick="saveProcessConfig()">💾 Save Config</button>
                    <button class="action-btn btn-clear" onclick="clearProcessConfig()">🗑️ Clear Config</button>
                </div>

                <div class="btn-group">
                    <button class="action-btn btn-start" onclick="startProcess(1)">Start Process</button>
                    <button class="action-btn btn-stop" onclick="stopProcess(1)">Stop Process</button>
                </div>

                <div class="status-container" id="status-1">
                    <div class="status-dot-main"></div>
                    <span class="status-text">Process Ready. Idle.</span>
                </div>
            </div>
        </div>
    </div>

    <script>
        const AUTO_CLIENT_ID = (window.crypto && crypto.randomUUID)
            ? crypto.randomUUID()
            : ('c-' + Date.now() + '-' + Math.random().toString(36).slice(2));

        window.addEventListener('load', () => {{
            loadProcessConfig();
        }});

        // Stop only processes owned by this dashboard's tab sessions on page close.
        window.addEventListener('beforeunload', () => {{
            Object.values(TAB_DEVICE_IDS).forEach((deviceId) => {{
                const body = new Blob([JSON.stringify({{ client_id: deviceId }})], {{ type: 'application/json' }});
                navigator.sendBeacon('/api/stopall', body);
            }});
        }});

        function saveProcessConfig() {{
            const content = document.getElementById('process-content-1');
            const config = {{
                token: content.querySelector('.input-token').value,
                channelId: content.querySelector('.input-channel').value,
                message: content.querySelector('.input-message').value,
                intervalVal: content.querySelector('.input-interval-val').value,
                intervalUnit: content.querySelector('.input-interval-unit').value
            }};

            localStorage.setItem('autosender_free_config', JSON.stringify(config));
            const statusText = document.querySelector('#status-1 .status-text');
            statusText.innerText = 'Configuration saved to browser local storage!';
        }}

        function loadProcessConfig() {{
            const savedData = localStorage.getItem('autosender_free_config');
            if (savedData) {{
                try {{
                    const config = JSON.parse(savedData);
                    const content = document.getElementById('process-content-1');
                    if (config.token) content.querySelector('.input-token').value = config.token;
                    if (config.channelId) content.querySelector('.input-channel').value = config.channelId;
                    if (config.message) content.querySelector('.input-message').value = config.message;
                    if (config.intervalVal) content.querySelector('.input-interval-val').value = config.intervalVal;
                    if (config.intervalUnit) content.querySelector('.input-interval-unit').value = config.intervalUnit;

                    const statusText = document.querySelector('#status-1 .status-text');
                    statusText.innerText = 'Loaded saved configuration from browser storage!';
                }} catch (e) {{
                    console.error('Failed to parse saved config:', e);
                }}
            }}
        }}

        function clearProcessConfig() {{
            localStorage.removeItem('autosender_free_config');
            const content = document.getElementById('process-content-1');
            content.querySelector('.input-token').value = '';
            content.querySelector('.input-channel').value = '';
            content.querySelector('.input-message').value = '';
            content.querySelector('.input-interval-val').value = '1';
            content.querySelector('.input-interval-unit').value = '60';

            const statusText = document.querySelector('#status-1 .status-text');
            statusText.innerText = 'Saved config cleared!';
        }}

        async function startProcess(id) {{
            const content = document.getElementById(`process-content-${{id}}`);
            const token = content.querySelector('.input-token').value;
            const channelId = content.querySelector('.input-channel').value;
            const message = content.querySelector('.input-message').value;
            
            const intervalVal = parseInt(content.querySelector('.input-interval-val').value) || 1;
            const intervalUnit = parseInt(content.querySelector('.input-interval-unit').value) || 60;
            let totalSeconds = intervalVal * intervalUnit;
            if (totalSeconds < 10) totalSeconds = 10;

            const statusBox = document.getElementById(`status-${{id}}`);
            const statusText = statusBox.querySelector('.status-text');

            try {{
                const res = await fetch('/api/start', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        process_id: id,
                        client_id: AUTO_CLIENT_ID,
                        key: '',
                        token: token,
                        channel_id: channelId,
                        message: message,
                        interval: totalSeconds
                    }})
                }});

                const data = await res.json();

                if (res.ok) {{
                    statusBox.className = 'status-container active';
                    statusText.innerText = data.message;
                }} else {{
                    statusBox.className = 'status-container error';
                    statusText.innerText = data.message || 'Error starting process.';
                }}
            }} catch (err) {{
                statusBox.className = 'status-container error';
                statusText.innerText = 'Network Error: Cannot connect to server.';
            }}
        }}

        async function stopProcess(id) {{
            const statusBox = document.getElementById(`status-${{id}}`);
            const statusText = statusBox.querySelector('.status-text');

            try {{
                const res = await fetch('/api/stop', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ process_id: id, client_id: makeTabDeviceId(id) }})
                }});

                const data = await res.json();
                statusBox.className = 'status-container';
                statusText.innerText = data.message;
            }} catch (err) {{
                statusBox.className = 'status-container error';
                statusText.innerText = 'Failed to stop process.';
            }}
        }}
    </script>
</body>
</html>
"""

# ==============================================================================
# 2.5 AUTO-SENDER DASHBOARD (PRO VERSION) HTML & CSS
# ==============================================================================
PRO_TOOL_TEMPLATE = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoSender PRO - Multi-Process Dashboard</title>
    <link rel="icon" type="image/svg+xml" href="{FAVICON_URI}">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-primary: #111214;
            --bg-secondary: #1a1b1e;
            --bg-tertiary: #232428;
            --accent-red: #da373d;
            --accent-red-hover: #e54c52;
            --text-normal: #f2f3f5;
            --text-muted: #949ba4;
            --input-bg: #1e1f22;
            --success-color: #23a55a;
            --error-color: #f23f43;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }}

        ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
        ::-webkit-scrollbar-track {{ background: var(--bg-primary); border-radius: 4px; }}
        ::-webkit-scrollbar-thumb {{ background: #232428; border-radius: 4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: var(--accent-red); }}

        body {{
            background-color: var(--bg-primary);
            color: var(--text-normal);
            display: flex;
            flex-direction: column;
            align-items: center;
            min-height: 100vh;
        }}

        .top-nav {{
            width: 100%;
            background-color: #0b0c0e;
            padding: 12px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            margin-bottom: 40px;
        }}

        .top-nav a {{
            color: var(--text-muted);
            text-decoration: none;
            font-size: 13px;
            font-weight: 600;
            transition: color 0.2s;
        }}
        .top-nav a:hover {{ color: var(--text-normal); }}
        
        .top-nav .pro-header-tag {{
            color: var(--accent-red);
            font-weight: 700;
            font-size: 14px;
        }}

        .tool-container {{
            width: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 0 20px 40px;
        }}

        .card {{
            background-color: var(--bg-secondary);
            width: 100%;
            max-width: 580px;
            padding: 35px;
            border-radius: 12px;
            box-shadow: 0 0 25px rgba(218, 55, 61, 0.15);
            border: 1px solid var(--accent-red);
        }}

        .header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 25px;
        }}

        .header-title h2 {{ font-size: 24px; font-weight: 800; }}
        .header-title span {{ color: var(--accent-red); }}

        .badge.pro {{
            background-color: var(--accent-red);
            color: #ffffff;
            font-size: 11px;
            font-weight: 800;
            padding: 5px 10px;
            border-radius: 6px;
            text-transform: uppercase;
        }}

        .pro-banner {{
            background-color: rgba(35, 165, 90, 0.15);
            border: 1px solid #23a55a;
            color: #23a55a;
            padding: 12px;
            border-radius: 6px;
            margin-bottom: 20px;
            font-size: 13px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .tabs-bar {{
            display: flex;
            gap: 6px;
            margin-bottom: 20px;
            overflow-x: auto;
            padding-bottom: 8px;
        }}

        .tab-btn {{
            background-color: var(--bg-tertiary);
            color: var(--text-muted);
            border: 1px solid rgba(255, 255, 255, 0.05);
            padding: 8px 14px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            white-space: nowrap;
            display: flex;
            align-items: center;
            gap: 6px;
            transition: all 0.2s ease;
        }}

        .tab-btn:hover {{ color: var(--text-normal); background-color: #383a40; }}

        .tab-btn.active {{
            background-color: var(--accent-red);
            color: #ffffff;
            border-color: var(--accent-red);
        }}

        .tab-btn .status-dot {{
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background-color: #5c6068;
        }}

        .tab-btn.running .status-dot {{
            background-color: var(--success-color);
            box-shadow: 0 0 6px var(--success-color);
        }}
        
        .close-tab {{
            margin-left: 6px;
            color: var(--text-muted);
            font-weight: 800;
            font-size: 14px;
            cursor: pointer;
            transition: color 0.2s;
        }}
        .close-tab:hover {{ color: var(--error-color); }}
        .tab-btn.active .close-tab {{ color: rgba(255,255,255,0.6); }}
        .tab-btn.active .close-tab:hover {{ color: #fff; }}

        .add-tab-btn {{
            background-color: rgba(255, 255, 255, 0.05);
            color: var(--text-normal);
            border: 1px dashed rgba(255, 255, 255, 0.2);
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 700;
            cursor: pointer;
        }}
        .add-tab-btn:hover {{ background-color: rgba(255, 255, 255, 0.1); }}

        .process-tab-content {{ display: none; }}
        .process-tab-content.active {{ display: block; }}

        .form-group {{ margin-bottom: 18px; }}

        label {{
            display: block;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-bottom: 8px;
            letter-spacing: 0.5px;
        }}

        input[type="text"],
        input[type="number"],
        textarea.input-message,
        select.input-interval-unit {{
            width: 100%;
            padding: 12px 14px;
            background-color: var(--input-bg);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 6px;
            color: var(--text-normal);
            font-size: 14px;
            outline: none;
            transition: all 0.2s ease;
            font-family: inherit;
        }}

        textarea.input-message {{
            resize: vertical;
            min-height: 120px;
            line-height: 1.4;
        }}

        input[type="text"]:focus,
        input[type="number"]:focus,
        textarea.input-message:focus,
        select.input-interval-unit:focus {{
            border-color: var(--accent-red);
            box-shadow: 0 0 0 2px rgba(218, 55, 61, 0.25);
        }}

        .btn-group {{ display: flex; gap: 10px; margin-top: 15px; }}

        button.action-btn {{
            flex: 1;
            padding: 14px;
            border: none;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .btn-start {{ background-color: var(--accent-red); color: #ffffff; }}
        .btn-start:hover {{ background-color: var(--accent-red-hover); }}

        .btn-stop {{
            background-color: var(--bg-tertiary);
            color: var(--text-normal);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        .btn-stop:hover {{ background-color: #3f4248; }}

        .btn-save {{ background-color: #23a55a; color: #ffffff; }}
        .btn-save:hover {{ background-color: #1f904e; }}

        .btn-clear {{ background-color: transparent; color: var(--text-muted); border: 1px dashed rgba(255, 255, 255, 0.2); }}
        .btn-clear:hover {{ color: var(--error-color); border-color: var(--error-color); }}

        .status-container {{
            margin-top: 20px;
            padding: 14px;
            background-color: var(--bg-tertiary);
            border-radius: 6px;
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 13px;
            color: var(--text-muted);
            border-left: 3px solid var(--accent-red);
        }}

        .status-dot-main {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background-color: #5c6068;
        }}

        .status-container.active {{ border-left-color: var(--success-color); color: var(--text-normal); }}
        .status-container.active .status-dot-main {{ background-color: var(--success-color); box-shadow: 0 0 8px var(--success-color); }}
        .status-container.error {{ border-left-color: var(--error-color); color: var(--text-normal); }}
        .status-container.error .status-dot-main {{ background-color: var(--error-color); }}
    </style>
</head>
<body>

    <div class="top-nav">
        <a href="/">← Back to Home Page</a>
        <span class="pro-header-tag">Pro Mode Unlocked</span>
    </div>

    <div class="tool-container">
        <div class="card">
            <div class="header">
                <div class="header-title">
                    <h2>AutoSender <span>PRO</span></h2>
                </div>
                <span class="badge pro">PRO UNLIMITED</span>
            </div>

            <div class="tabs-bar" id="tabsBar">
                <button class="tab-btn active" id="tab-btn-1" onclick="switchTab(1)">
                    <span class="status-dot"></span> Process #1
                </button>
                <button class="add-tab-btn" onclick="addNewProcessTab()">+</button>
            </div>

            <div id="tabContents">
                <div class="process-tab-content active" id="process-content-1">
                    <div class="form-group">
                        <label>License Key</label>
                        <input type="text" class="input-key" placeholder="Enter valid Pro key">
                    </div>
                    <div class="form-group">
                        <label>Discord Account Token</label>
                        <input type="text" class="input-token" placeholder="mfa.X9k1...">
                    </div>
                    <div class="form-group">
                        <label>Discord Channel ID</label>
                        <input type="text" class="input-channel" placeholder="109283746592817264">
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
                        <button class="action-btn btn-start" onclick="startProcess(1)">Start Pro Process</button>
                        <button class="action-btn btn-stop" onclick="stopProcess(1)">Stop Process</button>
                    </div>

                    <div class="status-container" id="status-1">
                        <div class="status-dot-main"></div>
                        <span class="status-text">Status: Waiting for Pro Key activation...</span>
                    </div>
                </div>
            </div>

            <div class="pro-banner" style="border-color:#5865F2;color:#9aa4ff;background-color:rgba(88,101,242,.12);margin-top:18px;">
                🧪 Security Research Lab: tests this app's session isolation locally. No Discord request is made.
            </div>
            <div class="btn-group">
                <button class="action-btn btn-start" style="background:#5865F2;" onclick="runSecurityLab()">Run Session Isolation Test</button>
            </div>
            <div class="status-container" id="security-lab-status">
                <div class="status-dot-main"></div>
                <span class="status-text">Security lab idle.</span>
            </div>
        </div>
    </div>

    <script>
        let tabCount = 1;

        // Each Pro UI tab gets its own independent session/device identity.
        // This is session isolation only, not hardware/device fingerprint spoofing.
        const TAB_DEVICE_IDS = {
            1: (window.crypto && crypto.randomUUID)
                ? crypto.randomUUID()
                : ('p-' + Date.now() + '-' + Math.random().toString(36).slice(2))
        };

        function makeTabDeviceId(id) {{
            if (!TAB_DEVICE_IDS[id]) {{
                TAB_DEVICE_IDS[id] = (window.crypto && crypto.randomUUID)
                    ? crypto.randomUUID()
                    : ('p-' + Date.now() + '-' + id + '-' + Math.random().toString(36).slice(2));
            }}
            return TAB_DEVICE_IDS[id];
        }}

        window.addEventListener('load', () => {{
            loadProConfigs();
        }});

        window.addEventListener('beforeunload', () => {{
            const body = new Blob([JSON.stringify({{ client_id: AUTO_CLIENT_ID }})], {{ type: 'application/json' }});
            navigator.sendBeacon('/api/stopall', body);
        }});

        async function runSecurityLab() {{
            const statusBox = document.getElementById('security-lab-status');
            const statusText = statusBox.querySelector('.status-text');

            const victimClient = makeTabDeviceId(1);
            const attackerClient = (window.crypto && crypto.randomUUID)
                ? crypto.randomUUID()
                : ('lab-attacker-' + Date.now());

            statusBox.className = 'status-container';
            statusText.innerText = 'Running local session-isolation test...';

            try {{
                const res = await fetch('/api/security-lab/session-hijack', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        victim_client_id: victimClient,
                        victim_process_id: '1',
                        attacker_client_id: attackerClient
                    }})
                }});

                const data = await res.json();

                if (!res.ok) {{
                    statusBox.className = 'status-container error';
                    statusText.innerText = data.error || 'Security lab test failed.';
                    return;
                }}

                if (data.vulnerability_demo) {{
                    statusBox.className = 'status-container error';
                    statusText.innerText =
                        'LAB RESULT: session identity can be addressed by client-supplied identifiers. This is the finding to document and fix.';
                }} else {{
                    statusBox.className = 'status-container active';
                    statusText.innerText =
                        'LAB RESULT: session isolation held in this simulation.';
                }}
            }} catch (err) {{
                statusBox.className = 'status-container error';
                statusText.innerText = 'Security lab request failed.';
            }}
        }}

        function saveAllProConfigs() {{
            const configs = [];
            const activeContents = document.querySelectorAll('.process-tab-content');

            activeContents.forEach((c) => {{
                configs.push({{
                    key: c.querySelector('.input-key').value,
                    token: c.querySelector('.input-token').value,
                    channelId: c.querySelector('.input-channel').value,
                    message: c.querySelector('.input-message').value,
                    intervalVal: c.querySelector('.input-interval-val').value,
                    intervalUnit: c.querySelector('.input-interval-unit').value
                }});
            }});

            localStorage.setItem('autosender_pro_config', JSON.stringify(configs));
            
            activeContents.forEach((c, idx) => {{
                const statusText = c.querySelector('.status-text');
                if (statusText) statusText.innerText = 'All Pro tab configurations saved!';
            }});
        }}

        function loadProConfigs() {{
            const savedData = localStorage.getItem('autosender_pro_config');
            if (savedData) {{
                try {{
                    const configs = JSON.parse(savedData);
                    if (Array.isArray(configs) && configs.length > 0) {{
                        // Fill tab 1
                        fillTabFields(1, configs[0]);
                        
                        // Dynamically re-create extra tabs if saved
                        for (let i = 1; i < configs.length; i++) {{
                            addNewProcessTab();
                            fillTabFields(tabCount, configs[i]);
                        }}

                        const activeContents = document.querySelectorAll('.process-tab-content');
                        activeContents.forEach((c) => {{
                            const statusText = c.querySelector('.status-text');
                            if (statusText) statusText.innerText = 'Saved Pro session restored!';
                        }});
                    }}
                }} catch (e) {{
                    console.error('Failed to load Pro config:', e);
                }}
            }}
        }}

        function fillTabFields(id, config) {{
            const content = document.getElementById(`process-content-${{id}}`);
            if (!content || !config) return;

            if (config.key) content.querySelector('.input-key').value = config.key;
            if (config.token) content.querySelector('.input-token').value = config.token;
            if (config.channelId) content.querySelector('.input-channel').value = config.channelId;
            if (config.message) content.querySelector('.input-message').value = config.message;
            if (config.intervalVal) content.querySelector('.input-interval-val').value = config.intervalVal;
            if (config.intervalUnit) content.querySelector('.input-interval-unit').value = config.intervalUnit;
        }}

        function clearProConfigs() {{
            localStorage.removeItem('autosender_pro_config');
            location.reload();
        }}

        function switchTab(id) {{
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.process-tab-content').forEach(c => c.classList.remove('active'));

            const selectedBtn = document.getElementById(`tab-btn-${{id}}`);
            const selectedContent = document.getElementById(`process-content-${{id}}`);

            if (selectedBtn && selectedContent) {{
                selectedBtn.classList.add('active');
                selectedContent.classList.add('active');
            }}
        }}

        function addNewProcessTab() {{
            tabCount++;
            const tabId = tabCount;
            makeTabDeviceId(tabId);

            const tabsBar = document.getElementById('tabsBar');
            const addBtn = tabsBar.querySelector('.add-tab-btn');

            const newTabBtn = document.createElement('button');
            newTabBtn.className = 'tab-btn';
            newTabBtn.id = `tab-btn-${{tabId}}`;
            newTabBtn.onclick = () => switchTab(tabId);
            newTabBtn.innerHTML = `<span class="status-dot"></span> Process #${{tabId}} <span class="close-tab" onclick="closeTab(event, ${{tabId}})">×</span>`;

            tabsBar.insertBefore(newTabBtn, addBtn);

            const tabContents = document.getElementById('tabContents');
            const newContent = document.createElement('div');
            newContent.className = 'process-tab-content';
            newContent.id = `process-content-${{tabId}}`;
            
            let mainKey = document.querySelector('#process-content-1 .input-key') ? document.querySelector('#process-content-1 .input-key').value : '';

            newContent.innerHTML = `
                <div class="form-group">
                    <label>License Key <span style="font-weight: 400; color: #5c6068;">(Inherited from Tab 1)</span></label>
                    <input type="text" class="input-key" value="${{mainKey}}" placeholder="Enter valid Pro key">
                </div>
                <div class="form-group">
                    <label>Discord Account Token</label>
                    <input type="text" class="input-token" placeholder="mfa.X9k1...">
                </div>
                <div class="form-group">
                    <label>Discord Channel ID</label>
                    <input type="text" class="input-channel" placeholder="109283746592817264">
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
                    <button class="action-btn btn-start" onclick="startProcess(${{tabId}})">Start Pro Process</button>
                    <button class="action-btn btn-stop" onclick="stopProcess(${{tabId}})">Stop Process</button>
                </div>
                <div class="status-container" id="status-${{tabId}}">
                    <div class="status-dot-main"></div>
                    <span class="status-text">Status: Waiting for Pro Key activation...</span>
                </div>
            `;

            tabContents.appendChild(newContent);
            switchTab(tabId);
        }}

        async function closeTab(event, id) {{
            event.stopPropagation();
            
            await stopProcess(id);
            
            const tabBtn = document.getElementById(`tab-btn-${{id}}`);
            const tabContent = document.getElementById(`process-content-${{id}}`);
            if(tabBtn) tabBtn.remove();
            if(tabContent) tabContent.remove();
            
            switchTab(1);
        }}

        async function startProcess(id) {{
            const content = document.getElementById(`process-content-${{id}}`);
            const key = content.querySelector('.input-key').value;
            const token = content.querySelector('.input-token').value;
            const channelId = content.querySelector('.input-channel').value;
            const message = content.querySelector('.input-message').value;
            
            const intervalVal = parseInt(content.querySelector('.input-interval-val').value) || 1;
            const intervalUnit = parseInt(content.querySelector('.input-interval-unit').value) || 60;
            let totalSeconds = intervalVal * intervalUnit;
            if (totalSeconds < 10) totalSeconds = 10;

            const statusBox = document.getElementById(`status-${{id}}`);
            const statusText = statusBox.querySelector('.status-text');

            try {{
                const res = await fetch('/api/start', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        process_id: id,
                        client_id: makeTabDeviceId(id),
                        key: key,
                        token: token,
                        channel_id: channelId,
                        message: message,
                        interval: totalSeconds
                    }})
                }});

                const data = await res.json();

                if (res.ok) {{
                    statusBox.className = 'status-container active';
                    statusText.innerText = data.message;
                    document.getElementById(`tab-btn-${{id}}`).classList.add('running');
                }} else {{
                    statusBox.className = 'status-container error';
                    statusText.innerText = data.message || 'Error starting process.';
                }}
            }} catch (err) {{
                statusBox.className = 'status-container error';
                statusText.innerText = 'Network Error: Cannot connect to server.';
            }}
        }}

        async function stopProcess(id) {{
            const statusBox = document.getElementById(`status-${{id}}`);
            if(!statusBox) return;
            const statusText = statusBox.querySelector('.status-text');

            try {{
                const res = await fetch('/api/stop', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ process_id: id, client_id: AUTO_CLIENT_ID }})
                }});

                const data = await res.json();
                statusBox.className = 'status-container';
                statusText.innerText = data.message;
                const tabBtn = document.getElementById(`tab-btn-${{id}}`);
                if(tabBtn) tabBtn.classList.remove('running');
            }} catch (err) {{
                statusBox.className = 'status-container error';
                statusText.innerText = 'Failed to stop process.';
            }}
        }}
    </script>
</body>
</html>
"""

# ==============================================================================
# 3. BACKGROUND WORKER & DISCORD POSTER LOGIC
# ==============================================================================
def background_poster(session_key, process_id, token, channel_id, message, interval_sec, is_pro_user):
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": token.strip(),
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT
    }

    token_hash = get_token_hash(token)

    # Initialize or migrate the usage record.
    get_free_usage(token_hash)

    while active_sessions.get(session_key, {}).get("is_running", False):
        
        # --- FREE LIMIT CHECK ---
        current_usage = get_free_usage(token_hash)
        
        if not is_pro_user and current_usage >= FREE_LIMIT:
            print(f"[PROCESS #{process_id} STOPPED] Token hit {FREE_LIMIT} daily limit cap.")
            active_sessions[session_key]["is_running"] = False
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
            if not active_sessions.get(session_key, {}).get("is_running", False):
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

@app.route('/api/security-lab/session-hijack', methods=['POST'])
def security_lab_session_hijack():
    """
    LOCAL SECURITY RESEARCH LAB ONLY.
    Simulates one browser client trying to stop another client's process.
    It never contacts Discord and never sends a message.
    """
    data = request.get_json(silent=True) or {}
    victim_client = str(data.get('victim_client_id', '')).strip()
    victim_process = str(data.get('victim_process_id', '1')).strip() or '1'
    attacker_client = str(data.get('attacker_client_id', '')).strip()

    if not victim_client or not attacker_client:
        return jsonify({"error": "Both victim_client_id and attacker_client_id are required."}), 400

    victim_key = make_session_key(victim_client, victim_process)
    attacker_key = make_session_key(attacker_client, victim_process)

    # Create a harmless simulated victim session for the lab.
    active_sessions[victim_key] = {
        "is_running": True,
        "client_id": victim_client,
        "process_id": victim_process,
        "lab": True,
    }

    # This mirrors the current ownership model of /api/stop:
    # identity is taken from the request body and used as the session owner.
    before = bool(active_sessions.get(victim_key, {}).get("is_running", False))

    # Attacker tries to address the victim by reusing the victim's identifiers.
    simulated_request_client = victim_client
    simulated_request_key = make_session_key(simulated_request_client, victim_process)
    can_address_victim = simulated_request_key == victim_key

    return jsonify({
        "lab": True,
        "attacker_client_id": attacker_client,
        "victim_client_id": victim_client,
        "process_id": victim_process,
        "vulnerability_demo": can_address_victim,
        "victim_running_before": before,
        "note": "This is a local session-ownership simulation. No Discord request is made."
    }), 200

@app.route('/api/start', methods=['POST'])
def start_bot():
    data = request.json or {}
    process_id = str(data.get('process_id', '1'))
    client_id = str(data.get('client_id', 'legacy')).strip() or 'legacy'
    session_key = make_session_key(client_id, process_id)
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

    # Stop only the same browser client's previous run for this process tab.
    if session_key in active_sessions:
        active_sessions[session_key]["is_running"] = False

    active_sessions[session_key] = {"is_running": True, "client_id": client_id, "process_id": process_id}

    worker_thread = threading.Thread(
        target=background_poster,
        args=(session_key, process_id, token, channel_id, message, interval_sec, is_pro),
        daemon=True
    )
    worker_thread.start()

    status_msg = "Process Running (Pro License Active)" if is_pro else f"Process Running (Free Tier: {current_usage}/{FREE_LIMIT} Used)"
    return jsonify({"message": status_msg, "is_pro": is_pro}), 200

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    data = request.json or {}
    process_id = str(data.get('process_id'))
    client_id = str(data.get('client_id', 'legacy')).strip() or 'legacy'
    session_key = make_session_key(client_id, process_id)

    if session_key in active_sessions:
        active_sessions[session_key]["is_running"] = False
        return jsonify({"message": f"Process #{process_id} Stopped."}), 200

    return jsonify({"message": f"Process #{process_id} is not running."}), 400

@app.route('/api/stopall', methods=['POST'])
def stop_all_bots():
    data = request.get_json(silent=True) or {}
    client_id = str(data.get('client_id', 'legacy')).strip() or 'legacy'
    stop_client_sessions(client_id)
    return jsonify({"message": "All processes for this browser session stopped."}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
