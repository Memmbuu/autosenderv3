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
            gap: 15px;
        }}

        nav a {{
            color: var(--text-muted);
            text-decoration: none;
            font-size: 14px;
            font-weight: 600;
            transition: color 0.2s ease;
        }}

        nav a:hover {{ color: var(--text-normal); }}

        .nav-btn {{
            background-color: var(--bg-card);
            color: #ffffff !important;
            padding: 8px 16px;
            border-radius: 8px;
            border: 1px solid var(--border-color);
            transition: all 0.2s ease;
        }}

        .nav-btn-pro {{
            background-color: var(--accent-red);
            color: #ffffff !important;
            padding: 8px 18px;
            border-radius: 8px;
            transition: all 0.2s ease;
            box-shadow: 0 4px 14px rgba(218, 55, 61, 0.3);
        }}

        .nav-btn-pro:hover {{
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

        .pricing-section {{
            max-width: 1100px;
            margin: 0 auto;
            padding: 40px 40px 100px;
        }}

        .section-title {{ text-align: center; margin-bottom: 60px; }}
        .section-title h2 {{ font-size: 36px; font-weight: 800; letter-spacing: -1px; }}

        .pricing-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 24px;
        }}

        .price-card {{
            background-color: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 32px 24px;
            display: flex;
            flex-direction: column;
            position: relative;
        }}

        .price-card.popular {{
            border-color: var(--accent-red);
            box-shadow: 0 0 30px rgba(218, 55, 61, 0.2);
        }}

        .price-card h3 {{ font-size: 20px; font-weight: 700; margin-bottom: 8px; }}
        .price {{ font-size: 38px; font-weight: 900; margin-bottom: 16px; }}

        .features-list {{
            list-style: none;
            margin: 24px 0 32px;
            flex-grow: 1;
        }}

        .features-list li {{
            font-size: 14px;
            color: var(--text-muted);
            margin-bottom: 12px;
        }}

        @media (max-width: 900px) {{
            .hero {{ grid-template-columns: 1fr; }}
            .pricing-grid {{ grid-template-columns: 1fr; }}
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
            <a href="/app" class="nav-btn">Free Tool</a>
            <a href="/pro" class="nav-btn-pro">PRO Tool</a>
        </nav>
    </header>

    <section class="hero">
        <div class="hero-text">
            <h1>Automate Discord Messages <span>24/7 Effortlessly</span></h1>
            <p>Select between our Free tier with standard features or unlock Premium for unlimited water-mark free messaging.</p>
            <div class="hero-actions">
                <a href="/app" class="btn-secondary">Launch Free Version</a>
                <a href="/pro" class="btn-primary">Launch Pro Version</a>
            </div>
        </div>
    </section>

    <section class="pricing-section">
        <div class="section-title">
            <h2>Choose Your Version</h2>
        </div>

        <div class="pricing-grid">
            <div class="price-card">
                <h3>Free Tier</h3>
                <div class="price">$0</div>
                <ul class="features-list">
                    <li>✓ 300 Free Messages Limit</li>
                    <li>✓ Automatic Site Watermark Included</li>
                    <li>✓ Standard Process Engine</li>
                </ul>
                <a href="/app" class="btn-secondary" style="text-align: center;">Open Free Tool</a>
            </div>

            <div class="price-card popular">
                <h3>Pro Key Version</h3>
                <div class="price">Pro Key Required</div>
                <ul class="features-list">
                    <li>✓ <strong>NO Watermarks or Ads</strong></li>
                    <li>✓ <strong>Unlimited Lifetime Messages</strong></li>
                    <li>✓ Multi-Process Tab Management</li>
                </ul>
                <a href="/pro" class="btn-primary" style="text-align: center;">Open Pro Tool</a>
            </div>
        </div>
    </section>
</body>
</html>
"""

# ==============================================================================
# 2. FREE AUTO-SENDER DASHBOARD HTML
# ==============================================================================
FREE_TOOL_TEMPLATE = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoSender v3 - Free Dashboard</title>
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

        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }}

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

        .top-nav a {{ color: var(--text-muted); text-decoration: none; font-size: 13px; font-weight: 600; }}

        .card {{
            background-color: var(--bg-secondary);
            width: 100%;
            max-width: 520px;
            padding: 28px;
            border-radius: 12px;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
        }}

        .badge {{
            background-color: rgba(255, 255, 255, 0.1);
            color: var(--text-muted);
            font-size: 11px;
            font-weight: 700;
            padding: 4px 8px;
            border-radius: 6px;
            text-transform: uppercase;
        }}

        .form-group {{ margin-bottom: 16px; }}

        label {{
            display: block;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-bottom: 6px;
        }}

        input[type="text"], input[type="number"] {{
            width: 100%;
            padding: 10px 12px;
            background-color: var(--input-bg);
            border: 1px solid rgba(0, 0, 0, 0.3);
            border-radius: 6px;
            color: var(--text-normal);
            font-size: 13px;
            outline: none;
        }}

        .btn-group {{ display: flex; gap: 10px; margin-top: 20px; }}

        button.action-btn {{
            flex: 1;
            padding: 12px;
            border: none;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
        }}

        .btn-start {{ background-color: var(--accent-red); color: #ffffff; }}
        .btn-stop {{ background-color: var(--bg-tertiary); color: var(--text-normal); }}

        .status-container {{
            margin-top: 16px;
            padding: 10px 12px;
            background-color: var(--bg-tertiary);
            border-radius: 6px;
            font-size: 12px;
            color: var(--text-muted);
        }}

        .watermark-notice {{
            margin-top: 15px;
            background-color: rgba(218, 55, 61, 0.1);
            border: 1px dashed var(--accent-red);
            padding: 10px;
            border-radius: 6px;
            font-size: 12px;
            color: var(--text-muted);
            text-align: center;
        }}
    </style>
</head>
<body>

    <div class="top-nav">
        <a href="/">← Back to Home Page</a>
        <a href="/pro" style="color: var(--accent-red); font-weight: bold;">Upgrade to Pro (No Watermarks) →</a>
    </div>

    <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h2>AutoSender <span style="color: var(--accent-red);">Free</span></h2>
            <span class="badge">300 Msg Limit</span>
        </div>

        <div class="form-group">
            <label>Discord Account Token</label>
            <input type="text" id="token" placeholder="mfa.X9k1...">
        </div>
        <div class="form-group">
            <label>Discord Channel ID</label>
            <input type="text" id="channel" placeholder="109283746592817264">
        </div>
        <div class="form-group">
            <label>Message Content</label>
            <input type="text" id="message" placeholder="Hello world!">
        </div>
        <div class="form-group">
            <label>Interval (Seconds)</label>
            <input type="number" id="interval" value="60" min="5">
        </div>

        <div class="watermark-notice">
            ⚠️ <strong>Free Version Active:</strong> Messages will include watermark ad (<code>_Sent via memmbuni.pythonanywhere.com_</code>).
        </div>

        <div class="btn-group">
            <button class="action-btn btn-start" onclick="startFree()">Start Free Process</button>
            <button class="action-btn btn-stop" onclick="stopFree()">Stop Process</button>
        </div>

        <div class="status-container" id="status-box">Status: Ready. Idle.</div>
    </div>

    <script>
        async function startFree() {{
            const token = document.getElementById('token').value;
            const channelId = document.getElementById('channel').value;
            const message = document.getElementById('message').value;
            const interval = document.getElementById('interval').value;
            const statusBox = document.getElementById('status-box');

            try {{
                const res = await fetch('/api/free/start', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ token, channel_id: channelId, message, interval }})
                }});
                const data = await res.json();
                statusBox.innerText = "Status: " + data.message;
            }} catch (e) {{
                statusBox.innerText = "Status: Error connecting to server.";
            }}
        }}

        async function stopFree() {{
            const statusBox = document.getElementById('status-box');
            try {{
                const res = await fetch('/api/free/stop', {{ method: 'POST' }});
                const data = await res.json();
                statusBox.innerText = "Status: " + data.message;
            }} catch (e) {{
                statusBox.innerText = "Status: Failed to stop.";
            }}
        }}
    </script>
</body>
</html>
"""

# ==============================================================================
# 3. PREMIUM PRO AUTO-SENDER DASHBOARD HTML
# ==============================================================================
PRO_TOOL_TEMPLATE = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoSender v3 - PRO Dashboard</title>
    <link rel="icon" type="image/svg+xml" href="{FAVICON_URI}">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-primary: #0b0c0e;
            --bg-secondary: #121316;
            --bg-tertiary: #1a1b1e;
            --accent-red: #da373d;
            --accent-red-hover: #ff474d;
            --text-normal: #f2f3f5;
            --text-muted: #949ba4;
            --input-bg: #18191c;
            --success-color: #23a55a;
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }}

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

        .top-nav a {{ color: var(--text-muted); text-decoration: none; font-size: 13px; font-weight: 600; }}

        .card {{
            background-color: var(--bg-secondary);
            width: 100%;
            max-width: 520px;
            padding: 28px;
            border-radius: 12px;
            border: 1px solid var(--accent-red);
            box-shadow: 0 0 25px rgba(218, 55, 61, 0.25);
        }}

        .badge-pro {{
            background-color: var(--accent-red);
            color: #fff;
            font-size: 11px;
            font-weight: 800;
            padding: 4px 10px;
            border-radius: 6px;
            text-transform: uppercase;
        }}

        .form-group {{ margin-bottom: 16px; }}

        label {{
            display: block;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-bottom: 6px;
        }}

        input[type="text"], input[type="number"], input[type="password"] {{
            width: 100%;
            padding: 10px 12px;
            background-color: var(--input-bg);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 6px;
            color: var(--text-normal);
            font-size: 13px;
            outline: none;
        }}

        input:focus {{ border-color: var(--accent-red); }}

        .btn-group {{ display: flex; gap: 10px; margin-top: 20px; }}

        button.action-btn {{
            flex: 1;
            padding: 12px;
            border: none;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
        }}

        .btn-start {{ background-color: var(--accent-red); color: #ffffff; }}
        .btn-stop {{ background-color: var(--bg-tertiary); color: var(--text-normal); }}

        .status-container {{
            margin-top: 16px;
            padding: 10px 12px;
            background-color: var(--bg-tertiary);
            border-radius: 6px;
            font-size: 12px;
            color: var(--text-muted);
            border-left: 3px solid var(--accent-red);
        }}

        .pro-benefit {{
            margin-top: 15px;
            background-color: rgba(35, 165, 90, 0.1);
            border: 1px solid var(--success-color);
            padding: 10px;
            border-radius: 6px;
            font-size: 12px;
            color: var(--success-color);
            text-align: center;
        }}
    </style>
</head>
<body>

    <div class="top-nav">
        <a href="/">← Back to Home Page</a>
        <span style="color: var(--accent-red); font-weight: bold;">Pro Mode Unlocked</span>
    </div>

    <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h2>AutoSender <span style="color: var(--accent-red);">PRO</span></h2>
            <span class="badge-pro">PRO UNLIMITED</span>
        </div>

        <div class="form-group">
            <label>License Key</label>
            <input type="password" id="pro-key" placeholder="Enter valid Pro key">
        </div>
        <div class="form-group">
            <label>Discord Account Token</label>
            <input type="text" id="token" placeholder="mfa.X9k1...">
        </div>
        <div class="form-group">
            <label>Discord Channel ID</label>
            <input type="text" id="channel" placeholder="109283746592817264">
        </div>
        <div class="form-group">
            <label>Message Content</label>
            <input type="text" id="message" placeholder="Clean message without ads/watermarks">
        </div>
        <div class="form-group">
            <label>Interval (Seconds)</label>
            <input type="number" id="interval" value="60" min="5">
        </div>

        <div class="pro-benefit">
            ✨ <strong>Pro Mode:</strong> Watermarks completely disabled & Unlimited messages active!
        </div>

        <div class="btn-group">
            <button class="action-btn btn-start" onclick="startPro()">Start Pro Process</button>
            <button class="action-btn btn-stop" onclick="stopPro()">Stop Process</button>
        </div>

        <div class="status-container" id="status-box">Status: Waiting for Pro Key activation...</div>
    </div>

    <script>
        async function startPro() {{
            const key = document.getElementById('pro-key').value;
            const token = document.getElementById('token').value;
            const channelId = document.getElementById('channel').value;
            const message = document.getElementById('message').value;
            const interval = document.getElementById('interval').value;
            const statusBox = document.getElementById('status-box');

            if(!key) {{
                statusBox.innerText = "Status: Please enter a valid License Key!";
                return;
            }}

            try {{
                const res = await fetch('/api/pro/start', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ key, token, channel_id: channelId, message, interval }})
                }});
                const data = await res.json();
                statusBox.innerText = "Status: " + data.message;
            }} catch (e) {{
                statusBox.innerText = "Status: Error connecting to server.";
            }}
        }}

        async function stopPro() {{
            const statusBox = document.getElementById('status-box');
            try {{
                const res = await fetch('/api/pro/stop', {{ method: 'POST' }});
                const data = await res.json();
                statusBox.innerText = "Status: " + data.message;
            }} catch (e) {{
                statusBox.innerText = "Status: Failed to stop process.";
            }}
        }}
    </script>
</body>
</html>
"""

# ==============================================================================
# 4. BACKGROUND WORKER & DISCORD POSTER LOGIC
# ==============================================================================
def background_poster(process_id, token, channel_id, message, interval_sec, is_pro_user):
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": token.strip(),
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT
    }

    token_hash = get_token_hash(token)
    
    if not is_pro_user:
        with db_lock:
            if token_hash not in free_usage_tracker:
                free_usage_tracker[token_hash] = 0
                save_free_tracker(free_usage_tracker)

    while active_sessions.get(process_id, {}).get("is_running", False):
        
        # Free Tier check & cap
        if not is_pro_user:
            with db_lock:
                current_usage = free_usage_tracker.get(token_hash, 0)
            if current_usage >= FREE_LIMIT:
                print(f"[FREE PROC STOPPED] Token hit 300 free limit cap.")
                active_sessions[process_id]["is_running"] = False
                break

        # Append watermark only for free users
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
                    print(f"[FREE PROC SUCCESS] ({current}/{FREE_LIMIT} Used)")
                else:
                    print(f"[PRO PROC SUCCESS] Message sent clean (No Watermark).")
            else:
                print(f"[PROC ERROR {res.status_code}] {res.text}")
        except Exception as e:
            print(f"[PROC ERROR] {e}")

        for _ in range(int(interval_sec)):
            if not active_sessions.get(process_id, {}).get("is_running", False):
                break
            time.sleep(1)

# ==============================================================================
# 5. FLASK ROUTES & API ENDPOINTS
# ==============================================================================
@app.route('/')
def home():
    return render_template_string(HOME_TEMPLATE)

@app.route('/app')
def free_tool():
    return render_template_string(FREE_TOOL_TEMPLATE)

@app.route('/pro')
def pro_tool():
    return render_template_string(PRO_TOOL_TEMPLATE)

# --- FREE API ROUTE ---
@app.route('/api/free/start', methods=['POST'])
def start_free():
    data = request.json or {}
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
        return jsonify({"message": "Token and Channel ID are required!"}), 400

    token_hash = get_token_hash(token)

    with db_lock:
        current_usage = free_usage_tracker.get(token_hash, 0)

    if current_usage >= FREE_LIMIT:
        return jsonify({"message": f"Free limit of {FREE_LIMIT} messages reached! Switch to PRO version."}), 403

    process_id = f"free_{token_hash}"
    active_sessions[process_id] = {"is_running": True}

    worker = threading.Thread(
        target=background_poster,
        args=(process_id, token, channel_id, message, interval_sec, False),
        daemon=True
    )
    worker.start()

    return jsonify({"message": f"Free process active! ({current_usage}/{FREE_LIMIT} free messages used)"}), 200

@app.route('/api/free/stop', methods=['POST'])
def stop_free():
    for pid in list(active_sessions.keys()):
        if pid.startswith("free_"):
            active_sessions[pid]["is_running"] = False
    return jsonify({"message": "Free process stopped."}), 200

# --- PRO API ROUTE ---
@app.route('/api/pro/start', methods=['POST'])
def start_pro():
    data = request.json or {}
    key = data.get('key', '').strip()
    token = data.get('token', '').strip()
    channel_id = data.get('channel_id', '').strip()
    message = data.get('message', '').strip()
    
    try:
        interval_sec = int(data.get('interval', 60))
        if interval_sec < 5:
            interval_sec = 5
    except ValueError:
        interval_sec = 60

    if not verify_key(key):
        return jsonify({"message": "Invalid Pro Key! Access Denied."}), 403

    if not token or not channel_id:
        return jsonify({"message": "Token and Channel ID are required!"}), 400

    token_hash = get_token_hash(token)
    process_id = f"pro_{token_hash}"
    active_sessions[process_id] = {"is_running": True}

    worker = threading.Thread(
        target=background_poster,
        args=(process_id, token, channel_id, message, interval_sec, True),
        daemon=True
    )
    worker.start()

    return jsonify({"message": "Pro Mode Active! Watermarks removed & unlimited sends enabled."}), 200

@app.route('/api/pro/stop', methods=['POST'])
def stop_pro():
    for pid in list(active_sessions.keys()):
        if pid.startswith("pro_"):
            active_sessions[pid]["is_running"] = False
    return jsonify({"message": "Pro process stopped."}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
