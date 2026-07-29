import os
import time
import json
import hashlib
import threading
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
db_lock = threading.Lock()

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

# --- PRO KEY VALIDATION ---
def verify_key(key):
    if not key:
        return False
    try:
        res = requests.get(RAW_KEYS_URL, timeout=5)
        if res.status_code == 200:
            valid_keys = [k.strip() for k in res.text.splitlines() if k.strip()]
            return key.strip() in valid_keys
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

        ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
        ::-webkit-scrollbar-track {{ background: #0b0c0e; }}
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
                <a href="/app" class="btn-primary">Open Tool Dashboard</a>
                <a href="#pricing" class="btn-secondary">View Plans</a>
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
                    <li>Single Process Tab</li>
                    <li>Community Support</li>
                </ul>
                <a href="/app" class="btn-secondary" style="text-align: center;">Try Free Now</a>
            </div>

            <div class="price-card popular">
                <div class="popular-tag">Most Popular</div>
                <h3>Pro Key Tier</h3>
                <div class="price">$9.99 <span>/ month</span></div>
                <ul class="features-list">
                    <li>Unlimited Parallel Tab Processes</li>
                    <li><strong>No Message Watermarks</strong></li>
                    <li>Unlimited Lifetime Messages</li>
                    <li>Priority Backend Dispatch</li>
                </ul>
                <a href="/app" class="btn-primary" style="text-align: center;">Launch Pro Tool</a>
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
                <a href="/app" class="btn-secondary" style="text-align: center;">Get Lifetime</a>
            </div>
        </div>
    </section>

    <script>
        function triggerDemoLog() {{
            const terminal = document.getElementById('terminalLogs');
            const now = new Date().toTimeString().split(' ')[0];
            const sampleLogs = [
                `<div class="log-entry"><span class="log-time">[${{now}}]</span> <span class="log-tag">[PROC #2]</span> <span class="log-text">Triggering scheduled payload...</span></div>`,
                `<div class="log-entry"><span class="log-time">[${{now}}]</span> <span class="log-tag">[PROC #2]</span> <span class="log-success">HTTP 200 OK — Sent (3/300 free used)</span></div>`,
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
# 2. AUTO-SENDER DASHBOARD TOOL HTML & CSS
# ==============================================================================
TOOL_TEMPLATE = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoSender v3 Multi-Process Dashboard</title>
    <link rel="icon" type="image/svg+xml" href="{FAVICON_URI}">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-primary: #1e1f22;
            --bg-secondary: #2b2d31;
            --bg-tertiary: #313338;
            --scrollbar-auto: #1a1b1e;
            --scrollbar-thumb: #111214;
            --scrollbar-thumb-hover: #2b2d31;
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

        ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
        ::-webkit-scrollbar-track {{ background: var(--scrollbar-auto); border-radius: 4px; }}
        ::-webkit-scrollbar-thumb {{ background: var(--scrollbar-thumb); border-radius: 4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: var(--scrollbar-thumb-hover); }}

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

        .top-nav-discord {{
            display: flex;
            align-items: center;
            gap: 6px;
            color: #5865F2 !important;
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
        .header-title span {{ color: var(--accent-red); }}

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
        input[type="number"] {{
            width: 100%;
            padding: 10px 12px;
            background-color: var(--input-bg);
            border: 1px solid rgba(0, 0, 0, 0.3);
            border-radius: 6px;
            color: var(--text-normal);
            font-size: 13px;
            outline: none;
            transition: all 0.2s ease;
        }}

        input[type="text"]:focus,
        input[type="number"]:focus {{
            border-color: var(--accent-red);
            box-shadow: 0 0 0 2px rgba(218, 55, 61, 0.25);
        }}

        .btn-group {{
            display: flex;
            gap: 10px;
            margin-top: 20px;
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
        <a href="https://discord.gg/X8KuxXM5r" target="_blank" class="top-nav-discord">
            <svg width="16" height="16" viewBox="0 0 127.14 96.36" fill="currentColor">
                <path d="M107.7,8.07A105.15,105.15,0,0,0,81.47,0a72.06,72.06,0,0,0-3.36,6.83A97.68,97.68,0,0,0,49,6.83,72.37,72.37,0,0,0,45.64,0,105.89,105.89,0,0,0,19.39,8.09C2.79,32.65-1.71,56.6.54,80.21h0A105.73,105.73,0,0,0,32.71,96.36,77.7,77.7,0,0,0,39.6,85.25a68.42,68.42,0,0,1-10.85-5.18c.91-.66,1.8-1.34,2.66-2a75.57,75.57,0,0,0,64.32,0c.87.71,1.76,1.39,2.66,2a68.68,68.68,0,0,1-10.87,5.19,77,77,0,0,0,6.89,11.1,105.25,105.25,0,0,0,32.19-16.14c2.64-27.38-4.51-51.11-18.91-72.15ZM42.45,65.69C36.18,65.69,31,60,31,53s5-12.74,11.43-12.74S54,45.91,53.87,53,48.83,65.69,42.45,65.69Zm42.24,0C78.41,65.69,73.25,60,73.25,53s5-12.74,11.44-12.74S96.23,45.91,96.1,53,91.08,65.69,84.69,65.69Z"/>
            </svg>
            Support Server
        </a>
    </div>

    <div class="tool-container">
        <div class="card">
            <div class="header">
                <div class="header-title">
                    <h2>AutoSender <span>v3</span></h2>
                </div>
                <span class="badge">Multi-Process Tool</span>
            </div>

            <!-- TABS NAV -->
            <div class="tabs-bar" id="tabsBar">
                <button class="tab-btn active" id="tab-btn-1" onclick="switchTab(1)">
                    <span class="status-dot"></span> Process #1
                </button>
                <button class="add-tab-btn" onclick="addNewProcessTab()">+</button>
            </div>

            <!-- PROCESS TABS CONTAINERS -->
            <div id="tabContents">
                <!-- Process 1 Tab (Default) -->
                <div class="process-tab-content active" id="process-content-1">
                    <div class="form-group">
                        <label>License Key <span style="font-weight: 400; color: #5c6068;">(Optional for 300 free msgs)</span></label>
                        <input type="text" class="input-key" placeholder="Leave blank for Free 300 tier">
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
                        <input type="text" class="input-message" placeholder="Hello world! Check out my shop.">
                    </div>
                    <div class="form-group">
                        <label>Interval (Seconds)</label>
                        <input type="number" class="input-interval" value="60" min="5">
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
    </div>

    <script>
        let tabCount = 1;

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
            newTabBtn.innerHTML = `<span class="status-dot"></span> Process #${{tabId}}`;

            tabsBar.insertBefore(newTabBtn, addBtn);

            const tabContents = document.getElementById('tabContents');
            const newContent = document.createElement('div');
            newContent.className = 'process-tab-content';
            newContent.id = `process-content-${{tabId}}`;
            newContent.innerHTML = `
                <div class="form-group">
                    <label>License Key <span style="font-weight: 400; color: #5c6068;">(Optional for 300 free msgs)</span></label>
                    <input type="text" class="input-key" placeholder="Leave blank for Free 300 tier">
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
                    <input type="text" class="input-message" placeholder="Hello world! Check out my shop.">
                </div>
                <div class="form-group">
                    <label>Interval (Seconds)</label>
                    <input type="number" class="input-interval" value="60" min="5">
                </div>

                <div class="btn-group">
                    <button class="action-btn btn-start" onclick="startProcess(${{tabId}})">Start Process</button>
                    <button class="action-btn btn-stop" onclick="stopProcess(${{tabId}})">Stop Process</button>
                </div>

                <div class="status-container" id="status-${{tabId}}">
                    <div class="status-dot-main"></div>
                    <span class="status-text">Process Ready. Idle.</span>
                </div>
            `;

            tabContents.appendChild(newContent);
            switchTab(tabId);
        }}

        async function startProcess(id) {{
            const content = document.getElementById(`process-content-${{id}}`);
            const key = content.querySelector('.input-key').value;
            const token = content.querySelector('.input-token').value;
            const channelId = content.querySelector('.input-channel').value;
            const message = content.querySelector('.input-message').value;
            const interval = content.querySelector('.input-interval').value;

            const statusBox = document.getElementById(`status-${{id}}`);
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
                        interval: interval
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
            const statusText = statusBox.querySelector('.status-text');

            try {{
                const res = await fetch('/api/stop', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ process_id: id }})
                }});

                const data = await res.json();
                statusBox.className = 'status-container';
                statusText.innerText = data.message;
                document.getElementById(`tab-btn-${{id}}`).classList.remove('running');
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
def background_poster(process_id, token, channel_id, message, interval_sec, is_pro_user):
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": token.strip(),
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT
    }

    # Hash token for secure tracking
    token_hash = get_token_hash(token)
    
    if token_hash not in free_usage_tracker:
        free_usage_tracker[token_hash] = 0
        save_free_tracker(free_usage_tracker)

    while active_sessions.get(process_id, {}).get("is_running", False):
        
        # --- FREE LIMIT CHECK ---
        if not is_pro_user and free_usage_tracker.get(token_hash, 0) >= FREE_LIMIT:
            print(f"[PROCESS #{process_id} STOPPED] Token hit 300 cap.")
            active_sessions[process_id]["is_running"] = False
            break

        # --- MANDATORY SERVER-SIDE WATERMARK ---
        final_message = message
        if not is_pro_user:
            final_message += "\n\n_Sent via memmbuni.pythonanywhere.com_"

        payload = {"content": final_message}

        try:
            res = requests.post(url, headers=headers, json=payload, timeout=10)
            if res.status_code in (200, 201):
                if not is_pro_user:
                    free_usage_tracker[token_hash] += 1
                    save_free_tracker(free_usage_tracker)  # Save state immediately
                    
                    current = free_usage_tracker[token_hash]
                    print(f"[PROC #{process_id} SUCCESS] ({current}/{FREE_LIMIT} Free Msgs Used)")
                else:
                    print(f"[PROC #{process_id} PRO SUCCESS] Sent!")
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
    return render_template_string(TOOL_TEMPLATE)

@app.route('/api/start', methods=['POST'])
def start_bot():
    data = request.json or {}
    process_id = str(data.get('process_id'))
    user_key = data.get('key', '').strip()
    token = data.get('token', '').strip()
    channel_id = data.get('channel_id', '').strip()
    message = data.get('message', '').strip()
    
    try:
        interval_sec = int(data.get('interval', 60))
        if interval_sec < 5:
            interval_sec = 5
    except ValueError:
        interval_sec = 60

    if not token or not channel_id:
        return jsonify({"message": "Discord Token and Channel ID are required!"}), 400

    is_pro = verify_key(user_key)
    token_hash = get_token_hash(token)

    # Check database before starting process
    if not is_pro and free_usage_tracker.get(token_hash, 0) >= FREE_LIMIT:
        return jsonify({
            "message": f"Free limit of {FREE_LIMIT} messages reached for this token! Buy a Pro key to continue."
        }), 403

    # Stop process if running
    if process_id in active_sessions:
        active_sessions[process_id]["is_running"] = False
        time.sleep(1)

    active_sessions[process_id] = {"is_running": True}

    worker_thread = threading.Thread(
        target=background_poster,
        args=(process_id, token, channel_id, message, interval_sec, is_pro),
        daemon=True
    )
    worker_thread.start()

    status_msg = "Process Running (Pro License)" if is_pro else f"Process Running (Free Tier: {free_usage_tracker.get(token_hash, 0)}/{FREE_LIMIT} Used)"
    return jsonify({"message": status_msg}), 200

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    data = request.json or {}
    process_id = str(data.get('process_id'))

    if process_id in active_sessions:
        active_sessions[process_id]["is_running"] = False
        return jsonify({"message": f"Process #{process_id} Stopped."}), 200

    return jsonify({"message": f"Process #{process_id} is not running."}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
