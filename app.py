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
free_usage_tracker = load_free_tracker()  # Format: { "discord_token_hash": count }
active_sessions = {}

# --- DAILY MIDNIGHT RESET SCHEDULER ---
def daily_reset_scheduler():
    """Resets free-tier message counts at 12:00 AM every day."""
    last_reset_date = datetime.now().date()
    while True:
        now = datetime.now()
        if now.date() != last_reset_date and now.hour == 0 and now.minute == 0:
            with db_lock:
                for token_hash in free_usage_tracker:
                    free_usage_tracker[token_hash] = 0
                save_free_tracker(free_usage_tracker)
            last_reset_date = now.date()
            print("[SYSTEM] 12:00 AM Midnight reached: All free message limits have been reset!")
        time.sleep(30)

# Start midnight reset background thread
reset_thread = threading.Thread(target=daily_reset_scheduler, daemon=True)
reset_thread.start()

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
            <p>Start free with 300 messages or upgrade for unlimited watermark-free access.</p>
        </div>

        <div class="pricing-grid">
            <div class="price-card">
                <h3>Free Tier</h3>
                <div class="price">$0 <span>/ forever</span></div>
                <ul class="features-list">
                    <li>300 Free Messages Limit</li>
                    <li>Automatic Site Watermark</li>
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
# 2. AUTO-SENDER DASHBOARD (FREE) - FULLSCREEN MODERNIZED UI
# ==============================================================================
FREE_TOOL_TEMPLATE = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoSender v3 - Free Process Dashboard</title>
    <link rel="icon" type="image/svg+xml" href="{FAVICON_URI}">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-primary: #0e1013;
            --bg-secondary: #16181d;
            --bg-tertiary: #1f2228;
            --accent-red: #da373d;
            --accent-red-hover: #ff474d;
            --text-normal: #f2f3f5;
            --text-muted: #949ba4;
            --input-bg: #111317;
            --border-color: rgba(255, 255, 255, 0.08);
            --success-color: #23a55a;
            --error-color: #f23f43;
            --accent-blue: #5865f2;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }}

        ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
        ::-webkit-scrollbar-track {{ background: var(--bg-primary); }}
        ::-webkit-scrollbar-thumb {{ background: var(--bg-tertiary); border-radius: 4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: var(--accent-red); }}

        body {{
            background-color: var(--bg-primary);
            color: var(--text-normal);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }}

        .top-navbar {{
            width: 100%;
            background-color: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
            padding: 14px 32px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        .brand {{
            display: flex;
            align-items: center;
            gap: 12px;
            text-decoration: none;
            color: var(--text-normal);
            font-size: 18px;
            font-weight: 800;
        }}

        .brand span {{ color: var(--accent-red); }}

        .badge-free {{
            background: rgba(218, 55, 61, 0.15);
            color: var(--accent-red);
            border: 1px solid rgba(218, 55, 61, 0.35);
            font-size: 11px;
            font-weight: 800;
            padding: 4px 10px;
            border-radius: 20px;
            text-transform: uppercase;
        }}

        .nav-links {{
            display: flex;
            align-items: center;
            gap: 20px;
        }}

        .nav-links a {{
            color: var(--text-muted);
            text-decoration: none;
            font-size: 13px;
            font-weight: 600;
            transition: color 0.2s;
        }}

        .nav-links a:hover {{ color: var(--text-normal); }}

        .upgrade-btn {{
            background: var(--accent-red);
            color: #fff !important;
            padding: 7px 16px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 700;
            transition: 0.2s;
        }}

        .upgrade-btn:hover {{
            background: var(--accent-red-hover);
        }}

        .main-fullscreen {{
            flex: 1;
            padding: 24px 32px;
            display: grid;
            grid-template-columns: 1.4fr 1fr;
            gap: 24px;
            max-width: 1600px;
            width: 100%;
            margin: 0 auto;
        }}

        .panel-card {{
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 18px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        }}

        .panel-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--border-color);
        }}

        .panel-header h3 {{
            font-size: 16px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .form-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
        }}

        .full-width {{
            grid-column: span 2;
        }}

        .form-group {{
            display: flex;
            flex-direction: column;
            gap: 6px;
        }}

        .form-group label {{
            font-size: 12px;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            display: flex;
            justify-content: space-between;
        }}

        .form-group label span {{
            text-transform: none;
            font-weight: 400;
            color: #6a6f7a;
        }}

        input[type="text"],
        input[type="number"],
        textarea.input-message,
        select.input-interval-unit {{
            width: 100%;
            background: var(--input-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 12px 14px;
            color: var(--text-normal);
            font-size: 13px;
            outline: none;
            transition: all 0.2s;
        }}

        textarea.input-message {{
            resize: vertical;
            min-height: 140px;
            line-height: 1.5;
            font-family: inherit;
        }}

        input[type="text"]:focus,
        input[type="number"]:focus,
        textarea.input-message:focus,
        select.input-interval-unit:focus {{
            border-color: var(--accent-red);
            box-shadow: 0 0 0 2px rgba(218, 55, 61, 0.2);
        }}

        .interval-inputs {{
            display: flex;
            gap: 10px;
        }}

        .btn-row {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-top: 6px;
        }}

        button.action-btn {{
            padding: 12px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 700;
            border: none;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            transition: 0.2s;
        }}

        .btn-start {{
            background: var(--accent-red);
            color: #fff;
        }}
        .btn-start:hover {{ background: var(--accent-red-hover); }}

        .btn-stop {{
            background: var(--bg-tertiary);
            color: var(--text-normal);
            border: 1px solid var(--border-color);
        }}
        .btn-stop:hover {{ background: #2a2e36; }}

        .btn-save {{
            background: var(--success-color);
            color: #fff;
        }}
        .btn-save:hover {{ background: #1e8e4d; }}

        .btn-clear {{
            background: transparent;
            color: var(--text-muted);
            border: 1px dashed var(--border-color);
        }}
        .btn-clear:hover {{ color: var(--error-color); border-color: var(--error-color); }}

        /* Right Panel Cards */
        .status-box {{
            background: var(--input-bg);
            border: 1px solid var(--border-color);
            border-left: 4px solid #5c6068;
            padding: 16px;
            border-radius: 8px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}

        .status-box.active {{
            border-left-color: var(--success-color);
        }}

        .status-box.error {{
            border-left-color: var(--error-color);
        }}

        .status-pill {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
            font-weight: 700;
            color: var(--text-muted);
        }}

        .status-pill .dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #5c6068;
        }}

        .status-box.active .dot {{
            background: var(--success-color);
            box-shadow: 0 0 8px var(--success-color);
        }}

        .status-box.error .dot {{
            background: var(--error-color);
        }}

        .status-msg {{
            font-size: 14px;
            color: var(--text-normal);
            font-weight: 500;
        }}

        .guide-box {{
            background: rgba(88, 101, 242, 0.06);
            border: 1px solid rgba(88, 101, 242, 0.2);
            border-radius: 8px;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }}

        .guide-title {{
            font-size: 13px;
            font-weight: 700;
            color: var(--accent-blue);
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .guide-box ol {{
            padding-left: 18px;
            font-size: 12px;
            color: var(--text-muted);
            line-height: 1.7;
        }}

        .notice-card {{
            background: rgba(218, 55, 61, 0.08);
            border: 1px solid rgba(218, 55, 61, 0.25);
            border-radius: 8px;
            padding: 14px;
            font-size: 12px;
            color: var(--text-muted);
            line-height: 1.6;
        }}

        .notice-card strong {{
            color: var(--accent-red);
        }}

        @media (max-width: 1024px) {{
            .main-fullscreen {{
                grid-template-columns: 1fr;
            }}
            .form-grid {{
                grid-template-columns: 1fr;
            }}
            .full-width {{
                grid-column: span 1;
            }}
        }}
    </style>
</head>
<body>

    <nav class="top-navbar">
        <div style="display: flex; align-items: center; gap: 16px;">
            <a href="/" class="brand">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#da373d" stroke-width="2.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
                AutoSender <span>v3</span>
            </a>
            <span class="badge-free">Free Mode Dashboard</span>
        </div>
        <div class="nav-links">
            <a href="/">← Back to Home</a>
            <a href="https://discord.gg/X8KuxXM5r" target="_blank">Support Discord</a>
            <a href="/pro" class="upgrade-btn">Unlock Pro (Multi-Process) →</a>
        </div>
    </nav>

    <main class="main-fullscreen">
        <!-- Configuration Panel -->
        <section class="panel-card" id="process-content-1">
            <div class="panel-header">
                <h3>⚙️ Automation Settings</h3>
                <span style="font-size: 12px; color: var(--text-muted);">Process #1 (Single Active)</span>
            </div>

            <div class="form-grid">
                <div class="form-group full-width">
                    <label>Discord Account Token <span>(Kept secure & client-side only)</span></label>
                    <input type="text" class="input-token" placeholder="Paste your authorization token (e.g., mfa.X9k1...)">
                </div>

                <div class="form-group full-width">
                    <label>Discord Target Channel ID <span>(Right-click channel → Copy ID)</span></label>
                    <input type="text" class="input-channel" placeholder="Paste target channel numerical ID (e.g. 109283746592817264)">
                </div>

                <div class="form-group full-width">
                    <label>Message Content <span>(Supports Markdown, mentions & emojis)</span></label>
                    <textarea class="input-message" placeholder="Type or paste your multi-line Discord advertisement message here..."></textarea>
                </div>

                <div class="form-group full-width">
                    <label>Interval Between Sends <span>(Minimum safe limit: 10s)</span></label>
                    <div class="interval-inputs">
                        <input type="number" class="input-interval-val" value="1" min="1">
                        <select class="input-interval-unit">
                            <option value="1">Seconds</option>
                            <option value="60" selected>Minutes</option>
                            <option value="3600">Hours</option>
                        </select>
                    </div>
                </div>
            </div>

            <div class="btn-row">
                <button class="action-btn btn-save" onclick="saveProcessConfig()">💾 Save Config</button>
                <button class="action-btn btn-clear" onclick="clearProcessConfig()">🗑️ Clear Saved</button>
            </div>

            <div class="btn-row">
                <button class="action-btn btn-start" onclick="startProcess(1)">▶ Start Automation</button>
                <button class="action-btn btn-stop" onclick="stopProcess(1)">⏹ Stop Automation</button>
            </div>
        </section>

        <!-- Right Side: Live Monitor & Setup Instructions -->
        <section class="panel-card">
            <div class="panel-header">
                <h3>📊 Live Status & Monitoring</h3>
                <span style="font-size: 12px; color: var(--text-muted);">Real-time Telemetry</span>
            </div>

            <div class="status-box" id="status-1">
                <div class="status-pill">
                    <div class="dot"></div>
                    <span>SYSTEM STATUS</span>
                </div>
                <div class="status-msg status-text">Process Ready & Idle. Fill the settings and click Start.</div>
            </div>

            <div class="guide-box">
                <div class="guide-title">
                    <span>💡 Quick Start Instructions</span>
                </div>
                <ol>
                    <li>Obtain your user authorization token from Discord developer console.</li>
                    <li>Enable Developer Mode in Discord and copy your destination Channel ID.</li>
                    <li>Write your promotional message and choose your delivery interval.</li>
                    <li>Hit <strong>Save Config</strong> to persist fields, then press <strong>Start Automation</strong>.</li>
                </ol>
            </div>

            <div class="notice-card">
                <strong>Free Tier Active:</strong> Includes a 300 messages daily limit which resets at 12:00 AM midnight. Messages sent in Free tier automatically include the site watermark. Need clean messages or multiple parallel tabs? Upgrade to <strong>Pro Mode</strong>.
            </div>
        </section>
    </main>

    <script>
        window.addEventListener('load', () => {{
            loadProcessConfig();
        }});

        window.addEventListener('beforeunload', () => {{
            navigator.sendBeacon('/api/stopall');
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
                    statusText.innerText = 'Restored saved configuration from browser storage!';
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
                        key: '',
                        token: token,
                        channel_id: channelId,
                        message: message,
                        interval: totalSeconds
                    }})
                }});

                const data = await res.json();

                if (res.ok) {{
                    statusBox.className = 'status-box active';
                    statusText.innerText = data.message;
                }} else {{
                    statusBox.className = 'status-box error';
                    statusText.innerText = data.message || 'Error starting process.';
                }}
            }} catch (err) {{
                statusBox.className = 'status-box error';
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
                    body: JSON.stringify({{ process_id: id }})
                }});

                const data = await res.json();
                statusBox.className = 'status-box';
                statusText.innerText = data.message;
            }} catch (err) {{
                statusBox.className = 'status-box error';
                statusText.innerText = 'Failed to stop process.';
            }}
        }}
    </script>
</body>
</html>
"""

# ==============================================================================
# 2.5 AUTO-SENDER DASHBOARD (PRO VERSION) - FULLSCREEN MODERNIZED UI
# ==============================================================================
PRO_TOOL_TEMPLATE = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoSender PRO - Multi-Process Dashboard</title>
    <link rel="icon" type="image/svg+xml" href="{FAVICON_URI}">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-primary: #0a0b0d;
            --bg-secondary: #121418;
            --bg-tertiary: #1b1d24;
            --accent-red: #da373d;
            --accent-red-hover: #ff474d;
            --text-normal: #f2f3f5;
            --text-muted: #949ba4;
            --input-bg: #0d0f12;
            --border-color: rgba(255, 255, 255, 0.08);
            --success-color: #23a55a;
            --error-color: #f23f43;
            --accent-gold: #f59e0b;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }}

        ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
        ::-webkit-scrollbar-track {{ background: var(--bg-primary); }}
        ::-webkit-scrollbar-thumb {{ background: var(--bg-tertiary); border-radius: 4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: var(--accent-red); }}

        body {{
            background-color: var(--bg-primary);
            color: var(--text-normal);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }}

        .top-navbar {{
            width: 100%;
            background-color: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
            padding: 14px 32px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        .brand {{
            display: flex;
            align-items: center;
            gap: 12px;
            text-decoration: none;
            color: var(--text-normal);
            font-size: 18px;
            font-weight: 800;
        }}

        .brand span {{ color: var(--accent-red); }}

        .badge-pro {{
            background: linear-gradient(135deg, rgba(218, 55, 61, 0.2), rgba(245, 158, 11, 0.2));
            color: #ffb74d;
            border: 1px solid rgba(245, 158, 11, 0.4);
            font-size: 11px;
            font-weight: 800;
            padding: 4px 10px;
            border-radius: 20px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .nav-links {{
            display: flex;
            align-items: center;
            gap: 20px;
        }}

        .nav-links a {{
            color: var(--text-muted);
            text-decoration: none;
            font-size: 13px;
            font-weight: 600;
            transition: color 0.2s;
        }}

        .nav-links a:hover {{ color: var(--text-normal); }}

        /* Tabs Bar */
        .tabs-container {{
            width: 100%;
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
            padding: 8px 32px;
            display: flex;
            align-items: center;
            gap: 8px;
            overflow-x: auto;
        }}

        .tab-btn {{
            background: var(--bg-tertiary);
            color: var(--text-muted);
            border: 1px solid var(--border-color);
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: 0.2s;
            white-space: nowrap;
        }}

        .tab-btn:hover {{
            background: #252830;
            color: var(--text-normal);
        }}

        .tab-btn.active {{
            background: var(--accent-red);
            color: #fff;
            border-color: var(--accent-red);
        }}

        .tab-btn .dot {{
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: #5c6068;
        }}

        .tab-btn.running .dot {{
            background: var(--success-color);
            box-shadow: 0 0 6px var(--success-color);
        }}

        .tab-btn .close-btn {{
            margin-left: 6px;
            font-weight: 800;
            font-size: 14px;
            color: var(--text-muted);
            cursor: pointer;
        }}

        .tab-btn .close-btn:hover {{ color: #ff5f56; }}
        .tab-btn.active .close-btn {{ color: rgba(255,255,255,0.7); }}
        .tab-btn.active .close-btn:hover {{ color: #fff; }}

        .add-tab-btn {{
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-normal);
            border: 1px dashed var(--border-color);
            padding: 7px 14px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 700;
            cursor: pointer;
            transition: 0.2s;
        }}

        .add-tab-btn:hover {{
            background: rgba(255, 255, 255, 0.1);
        }}

        /* Fullscreen Layout */
        .main-fullscreen {{
            flex: 1;
            padding: 24px 32px;
            display: grid;
            grid-template-columns: 1.4fr 1fr;
            gap: 24px;
            max-width: 1600px;
            width: 100%;
            margin: 0 auto;
        }}

        .panel-card {{
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 18px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        }}

        .panel-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--border-color);
        }}

        .panel-header h3 {{
            font-size: 16px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .process-tab-content {{ display: none; }}
        .process-tab-content.active {{ display: flex; flex-direction: column; gap: 18px; }}

        .form-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
        }}

        .full-width {{ grid-column: span 2; }}

        .form-group {{
            display: flex;
            flex-direction: column;
            gap: 6px;
        }}

        .form-group label {{
            font-size: 12px;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            display: flex;
            justify-content: space-between;
        }}

        .form-group label span {{
            text-transform: none;
            font-weight: 400;
            color: #6a6f7a;
        }}

        input[type="text"],
        input[type="number"],
        textarea.input-message,
        select.input-interval-unit {{
            width: 100%;
            background: var(--input-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 12px 14px;
            color: var(--text-normal);
            font-size: 13px;
            outline: none;
            transition: all 0.2s;
        }}

        textarea.input-message {{
            resize: vertical;
            min-height: 140px;
            line-height: 1.5;
            font-family: inherit;
        }}

        input[type="text"]:focus,
        input[type="number"]:focus,
        textarea.input-message:focus,
        select.input-interval-unit:focus {{
            border-color: var(--accent-red);
            box-shadow: 0 0 0 2px rgba(218, 55, 61, 0.2);
        }}

        .interval-inputs {{
            display: flex;
            gap: 10px;
        }}

        .btn-row {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-top: 6px;
        }}

        button.action-btn {{
            padding: 12px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 700;
            border: none;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            transition: 0.2s;
        }}

        .btn-start {{ background: var(--accent-red); color: #fff; }}
        .btn-start:hover {{ background: var(--accent-red-hover); }}

        .btn-stop {{ background: var(--bg-tertiary); color: var(--text-normal); border: 1px solid var(--border-color); }}
        .btn-stop:hover {{ background: #2a2e36; }}

        .btn-save {{ background: var(--success-color); color: #fff; }}
        .btn-save:hover {{ background: #1e8e4d; }}

        .btn-clear {{ background: transparent; color: var(--text-muted); border: 1px dashed var(--border-color); }}
        .btn-clear:hover {{ color: var(--error-color); border-color: var(--error-color); }}

        /* Status & Monitoring */
        .status-box {{
            background: var(--input-bg);
            border: 1px solid var(--border-color);
            border-left: 4px solid #5c6068;
            padding: 16px;
            border-radius: 8px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}

        .status-box.active {{ border-left-color: var(--success-color); }}
        .status-box.error {{ border-left-color: var(--error-color); }}

        .status-pill {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
            font-weight: 700;
            color: var(--text-muted);
        }}

        .status-pill .dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #5c6068;
        }}

        .status-box.active .dot {{
            background: var(--success-color);
            box-shadow: 0 0 8px var(--success-color);
        }}

        .status-box.error .dot {{ background: var(--error-color); }}

        .status-msg {{
            font-size: 14px;
            color: var(--text-normal);
            font-weight: 500;
        }}

        .pro-active-banner {{
            background: rgba(35, 165, 90, 0.1);
            border: 1px solid rgba(35, 165, 90, 0.3);
            color: #23a55a;
            padding: 14px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 600;
            line-height: 1.5;
        }}

        .pro-tips-card {{
            background: rgba(245, 158, 11, 0.06);
            border: 1px solid rgba(245, 158, 11, 0.2);
            border-radius: 8px;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}

        .pro-tips-card h4 {{
            color: #ffb74d;
            font-size: 13px;
        }}

        .pro-tips-card ul {{
            padding-left: 18px;
            font-size: 12px;
            color: var(--text-muted);
            line-height: 1.7;
        }}

        @media (max-width: 1024px) {{
            .main-fullscreen {{ grid-template-columns: 1fr; }}
            .form-grid {{ grid-template-columns: 1fr; }}
            .full-width {{ grid-column: span 1; }}
        }}
    </style>
</head>
<body>

    <nav class="top-navbar">
        <div style="display: flex; align-items: center; gap: 16px;">
            <a href="/" class="brand">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#da373d" stroke-width="2.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
                AutoSender <span>PRO</span>
            </a>
            <span class="badge-pro">★ Pro Unlimited Suite</span>
        </div>
        <div class="nav-links">
            <a href="/">← Back to Home</a>
            <a href="https://discord.gg/X8KuxXM5r" target="_blank">Pro Support Discord</a>
        </div>
    </nav>

    <div class="tabs-container" id="tabsBar">
        <button class="tab-btn active" id="tab-btn-1" onclick="switchTab(1)">
            <span class="dot"></span> Process #1
        </button>
        <button class="add-tab-btn" onclick="addNewProcessTab()">+ New Process Tab</button>
    </div>

    <main class="main-fullscreen">
        <!-- Tab Content Manager -->
        <section class="panel-card" id="tabContents">
            <div class="process-tab-content active" id="process-content-1">
                <div class="panel-header">
                    <h3>⚡ Process #1 Configuration</h3>
                    <span style="font-size: 12px; color: var(--text-muted);">Pro Mode Active</span>
                </div>

                <div class="form-grid">
                    <div class="form-group full-width">
                        <label>License Key <span>(Auto-inherited to new tabs)</span></label>
                        <input type="text" class="input-key" placeholder="Enter your valid Pro license key">
                    </div>

                    <div class="form-group full-width">
                        <label>Discord Account Token <span>(Stored securely in local browser session)</span></label>
                        <input type="text" class="input-token" placeholder="Paste Discord Account Authorization Token">
                    </div>

                    <div class="form-group full-width">
                        <label>Target Channel ID <span>(Paste ID of destination channel)</span></label>
                        <input type="text" class="input-channel" placeholder="Paste target numerical Channel ID">
                    </div>

                    <div class="form-group full-width">
                        <label>Message Payload <span>(No watermarks appended in Pro mode)</span></label>
                        <textarea class="input-message" placeholder="Type your multi-line message advertisement here..."></textarea>
                    </div>

                    <div class="form-group full-width">
                        <label>Interval Delay <span>(Minimum safe limit: 10s)</span></label>
                        <div class="interval-inputs">
                            <input type="number" class="input-interval-val" value="1" min="1">
                            <select class="input-interval-unit">
                                <option value="1">Seconds</option>
                                <option value="60" selected>Minutes</option>
                                <option value="3600">Hours</option>
                            </select>
                        </div>
                    </div>
                </div>

                <div class="btn-row">
                    <button class="action-btn btn-save" onclick="saveAllProConfigs()">💾 Save All Tabs</button>
                    <button class="action-btn btn-clear" onclick="clearProConfigs()">🗑️ Clear All Tabs</button>
                </div>

                <div class="btn-row">
                    <button class="action-btn btn-start" onclick="startProcess(1)">▶ Start Pro Process</button>
                    <button class="action-btn btn-stop" onclick="stopProcess(1)">⏹ Stop Process</button>
                </div>
            </div>
        </section>

        <!-- Live Diagnostics & Pro Telemetry -->
        <section class="panel-card">
            <div class="panel-header">
                <h3>📊 Active Process Diagnostics</h3>
                <span style="font-size: 12px; color: var(--text-muted);">Multi-Thread Monitor</span>
            </div>

            <div class="status-box" id="status-1">
                <div class="status-pill">
                    <div class="dot"></div>
                    <span>DIAGNOSTICS & STATUS</span>
                </div>
                <div class="status-msg status-text">Waiting for Pro Key activation & Start command...</div>
            </div>

            <div class="pro-active-banner">
                ✨ <strong>Pro Privileges Active:</strong> All message watermarks are removed. You can execute multiple channels and processes in parallel.
            </div>

            <div class="pro-tips-card">
                <h4>🎯 Pro Usage Tips</h4>
                <ul>
                    <li>Click <strong>+ New Process Tab</strong> to automate different channels simultaneously.</li>
                    <li>Your License Key is automatically shared between all opened tabs.</li>
                    <li>Use <strong>Save All Tabs</strong> before closing to store your setup locally.</li>
                </ul>
            </div>
        </section>
    </main>

    <script>
        let tabCount = 1;

        window.addEventListener('load', () => {{
            loadProConfigs();
        }});

        window.addEventListener('beforeunload', () => {{
            navigator.sendBeacon('/api/stopall');
        }});

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
            
            const activeStatusText = document.querySelector('.status-text');
            if (activeStatusText) activeStatusText.innerText = 'All Pro tab configurations saved to browser storage!';
        }}

        function loadProConfigs() {{
            const savedData = localStorage.getItem('autosender_pro_config');
            if (savedData) {{
                try {{
                    const configs = JSON.parse(savedData);
                    if (Array.isArray(configs) && configs.length > 0) {{
                        fillTabFields(1, configs[0]);
                        
                        for (let i = 1; i < configs.length; i++) {{
                            addNewProcessTab();
                            fillTabFields(tabCount, configs[i]);
                        }}

                        const activeStatusText = document.querySelector('.status-text');
                        if (activeStatusText) activeStatusText.innerText = 'Restored saved Pro sessions from local storage!';
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

            const tabsBar = document.getElementById('tabsBar');
            const addBtn = tabsBar.querySelector('.add-tab-btn');

            const newTabBtn = document.createElement('button');
            newTabBtn.className = 'tab-btn';
            newTabBtn.id = `tab-btn-${{tabId}}`;
            newTabBtn.onclick = () => switchTab(tabId);
            newTabBtn.innerHTML = `<span class="dot"></span> Process #${{tabId}} <span class="close-btn" onclick="closeTab(event, ${{tabId}})">×</span>`;

            tabsBar.insertBefore(newTabBtn, addBtn);

            const tabContents = document.getElementById('tabContents');
            const newContent = document.createElement('div');
            newContent.className = 'process-tab-content';
            newContent.id = `process-content-${{tabId}}`;
            
            let mainKey = document.querySelector('#process-content-1 .input-key') ? document.querySelector('#process-content-1 .input-key').value : '';

            newContent.innerHTML = `
                <div class="panel-header">
                    <h3>⚡ Process #${{tabId}} Configuration</h3>
                    <span style="font-size: 12px; color: var(--text-muted);">Pro Mode Active</span>
                </div>
                <div class="form-grid">
                    <div class="form-group full-width">
                        <label>License Key <span>(Inherited from Tab 1)</span></label>
                        <input type="text" class="input-key" value="${{mainKey}}" placeholder="Enter your valid Pro license key">
                    </div>
                    <div class="form-group full-width">
                        <label>Discord Account Token</label>
                        <input type="text" class="input-token" placeholder="Paste Discord Account Authorization Token">
                    </div>
                    <div class="form-group full-width">
                        <label>Target Channel ID</label>
                        <input type="text" class="input-channel" placeholder="Paste target numerical Channel ID">
                    </div>
                    <div class="form-group full-width">
                        <label>Message Payload</label>
                        <textarea class="input-message" placeholder="Type your multi-line message advertisement here..."></textarea>
                    </div>
                    <div class="form-group full-width">
                        <label>Interval Delay <span>(Minimum safe limit: 10s)</span></label>
                        <div class="interval-inputs">
                            <input type="number" class="input-interval-val" value="1" min="1">
                            <select class="input-interval-unit">
                                <option value="1">Seconds</option>
                                <option value="60" selected>Minutes</option>
                                <option value="3600">Hours</option>
                            </select>
                        </div>
                    </div>
                </div>
                <div class="btn-row">
                    <button class="action-btn btn-save" onclick="saveAllProConfigs()">💾 Save All Tabs</button>
                    <button class="action-btn btn-clear" onclick="clearProConfigs()">🗑️ Clear All Tabs</button>
                </div>
                <div class="btn-row">
                    <button class="action-btn btn-start" onclick="startProcess(${{tabId}})">▶ Start Pro Process</button>
                    <button class="action-btn btn-stop" onclick="stopProcess(${{tabId}})">⏹ Stop Process</button>
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

            const statusBox = document.getElementById('status-1');
            const statusText = statusBox.querySelector('.status-text');

            try {{
                const res = await fetch('/api/start', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        process_id: id,
                        key: key,
                        token: token,
                        channel_id: channelId,
                        message: message,
                        interval: totalSeconds
                    }})
                }});

                const data = await res.json();

                if (res.ok) {{
                    statusBox.className = 'status-box active';
                    statusText.innerText = `Process #${{id}}: ` + data.message;
                    document.getElementById(`tab-btn-${{id}}`).classList.add('running');
                }} else {{
                    statusBox.className = 'status-box error';
                    statusText.innerText = `Process #${{id}} Error: ` + (data.message || 'Failed to start.');
                }}
            }} catch (err) {{
                statusBox.className = 'status-box error';
                statusText.innerText = 'Network Error: Cannot connect to server.';
            }}
        }}

        async function stopProcess(id) {{
            const statusBox = document.getElementById('status-1');
            const statusText = statusBox.querySelector('.status-text');

            try {{
                const res = await fetch('/api/stop', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ process_id: id }})
                }});

                const data = await res.json();
                statusBox.className = 'status-box';
                statusText.innerText = `Process #${{id}}: ` + data.message;
                const tabBtn = document.getElementById(`tab-btn-${{id}}`);
                if(tabBtn) tabBtn.classList.remove('running');
            }} catch (err) {{
                statusBox.className = 'status-box error';
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
def background_poster(process_id, token, channel_id, message, interval_sec, is_pro_user):
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": token.strip(),
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT
    }

    token_hash = get_token_hash(token)
    
    with db_lock:
        if token_hash not in free_usage_tracker:
            free_usage_tracker[token_hash] = 0
            save_free_tracker(free_usage_tracker)

    while active_sessions.get(process_id, {}).get("is_running", False):
        
        # --- FREE LIMIT CHECK ---
        with db_lock:
            current_usage = free_usage_tracker.get(token_hash, 0)
        
        if not is_pro_user and current_usage >= FREE_LIMIT:
            print(f"[PROCESS #{process_id} STOPPED] Token hit 300 limit cap.")
            active_sessions[process_id]["is_running"] = False
            break

        # --- WATERMARK SEPARATION LOGIC ---
        final_message = message
        if not is_pro_user:
            final_message += "\n\n_Sent via AutoSender.lol_"

        payload = {"content": final_message}

        try:
            res = requests.post(url, headers=headers, json=payload, timeout=10)
            if res.status_code in (200, 201):
                if not is_pro_user:
                    with db_lock:
                        free_usage_tracker[token_hash] = free_usage_tracker.get(token_hash, 0) + 1
                        save_free_tracker(free_usage_tracker)
                        current = free_usage_tracker[token_hash]
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

    # Key validation
    is_pro = verify_key(user_key) if user_key else False
    
    # ENFORCE FREE SINGLE-PROCESS RULE
    if not is_pro and process_id != '1':
        return jsonify({
            "message": "Free Tier is restricted to Process #1 only. Upgrade to Pro for multi-process automation."
        }), 403

    token_hash = get_token_hash(token)

    with db_lock:
        current_usage = free_usage_tracker.get(token_hash, 0)

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
