"""
╔══════════════════════════════════════════════════════════╗
║   🌐 AI AGENT — LIVE SERVER v2 (Button UI + Excel)      ║
║   Run: python server.py                                 ║
║   Then open: http://localhost:5000                      ║
╚══════════════════════════════════════════════════════════╝

pip install flask openpyxl
python server.py
"""

import sys, os, threading, queue, json, time, glob
from datetime import datetime

_real_stdout = sys.stdout
_real_stderr = sys.stderr

# ══════════════════════════════════════════════════════════
# SHARED STATE
# ══════════════════════════════════════════════════════════

_output_queue  = queue.Queue()   # agent  → dashboard (SSE)
_command_queue = queue.Queue()   # HTTP   → main thread (commands)
_input_queue   = queue.Queue()   # HTTP   → main thread (input answers)
_waiting_for_input = threading.Event()

_stats = {
    "applied": 0, "scraped": 0, "skipped": 0, "errors": 0,
    "running": False, "current": "", "browser_ready": False,
}

# Runtime-editable profile (starts from ai_agent.MY_PROFILE, editable via dashboard)
_runtime_profile = {}

# ══════════════════════════════════════════════════════════
# CAPTURED STDOUT
# ══════════════════════════════════════════════════════════

class _AgentStdout:
    def write(self, text):
        _real_stdout.write(text); _real_stdout.flush()
        s = text.rstrip()
        if s:
            _output_queue.put({"type": "log", "text": s})
            _parse_stats(s)
    def flush(self): _real_stdout.flush()
    def fileno(self): return _real_stdout.fileno()

def _parse_stats(text):
    t = text.lower()
    if "🎉 applied!" in t or "applied! total:" in t: _stats["applied"] += 1
    if "✅ scraped" in t and "unique" in t:
        try:
            nums = [int(s) for s in t.split() if s.isdigit()]
            if nums: _stats["scraped"] = max(nums)
        except: pass
    if "🚫 external" in t or "skipped (external)" in t: _stats["skipped"] += 1
    if "❌" in text and "nav error" not in t: _stats["errors"] += 1

# ══════════════════════════════════════════════════════════
# PATCHED input()
# ══════════════════════════════════════════════════════════

def _patched_input(prompt=""):
    p = str(prompt).strip()
    _real_stdout.write(f"\n[INPUT REQUESTED] {p}\n"); _real_stdout.flush()
    _output_queue.put({"type": "input_request", "prompt": p})
    _waiting_for_input.set()
    try:
        ans = _input_queue.get(timeout=300)
        _real_stdout.write(f"[INPUT RECEIVED] {ans}\n"); _real_stdout.flush()
        _output_queue.put({"type": "input_given", "value": ans})
        return ans
    except queue.Empty:
        return "yes"
    finally:
        _waiting_for_input.clear()

import builtins
builtins.input = _patched_input
sys.stdout = _AgentStdout()

_agent_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _agent_dir)
import ai_agent

# Apply runtime profile overrides
def _sync_profile():
    """Push _runtime_profile edits into ai_agent.MY_PROFILE."""
    for k, v in _runtime_profile.items():
        if k in ai_agent.MY_PROFILE:
            ai_agent.MY_PROFILE[k] = v
    # Rebuild QUICK_ANSWERS with new values
    ai_agent.QUICK_ANSWERS.update({
        "notice period":       ai_agent.MY_PROFILE["notice_period"],
        "current ctc":         ai_agent.MY_PROFILE["current_ctc"],
        "expected ctc":        ai_agent.MY_PROFILE["expected_ctc"],
        "experience":          ai_agent.MY_PROFILE["experience_years"],
        "years of experience": ai_agent.MY_PROFILE["experience_years"],
        "first name":          ai_agent.MY_PROFILE["first_name"],
        "last name":           ai_agent.MY_PROFILE["last_name"],
        "full name":           ai_agent.MY_PROFILE["name"],
        "email":               ai_agent.MY_PROFILE["email"],
        "phone":               ai_agent.MY_PROFILE["phone"],
        "location":            ai_agent.MY_PROFILE["location"],
    })

# ══════════════════════════════════════════════════════════
# FLASK
# ══════════════════════════════════════════════════════════

from flask import Flask, Response, request, jsonify, send_from_directory, send_file
app = Flask(__name__)

@app.route("/")
def index():
    return send_from_directory(_agent_dir, "dashboard.html")

@app.route("/events")
def events():
    def generate():
        yield f"data: {json.dumps({'type':'connected','stats':dict(_stats),'profile':dict(ai_agent.MY_PROFILE)})}\n\n"
        while True:
            try:
                msg = _output_queue.get(timeout=3)
                yield f"data: {json.dumps(msg)}\n\n"
            except queue.Empty:
                yield f"data: {json.dumps({'type':'ping'})}\n\n"
    return Response(generate(), mimetype="text/event-stream",
        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no",
                 "Connection":"keep-alive","Access-Control-Allow-Origin":"*"})

@app.route("/status")
def status():
    return jsonify(dict(_stats))

@app.route("/command", methods=["POST"])
def command():
    if _stats["running"]:
        return jsonify({"error": "Agent already running"}), 400
    data = request.get_json(force=True) or {}
    cmd  = data.get("command","").strip()
    if not cmd: return jsonify({"error": "Empty command"}), 400
    _command_queue.put(cmd)
    return jsonify({"status": "queued"})

@app.route("/respond", methods=["POST"])
def respond():
    data = request.get_json(force=True) or {}
    _input_queue.put(data.get("value","yes"))
    return jsonify({"status":"ok"})

@app.route("/stop", methods=["POST"])
def stop_route():
    _stats["running"] = False
    _output_queue.put({"type":"log","text":"⛔ Stop requested."})
    _output_queue.put({"type":"done","stats":dict(_stats)})
    return jsonify({"status":"stopped"})

# ── Profile endpoints ─────────────────────────────────────
@app.route("/profile", methods=["GET"])
def get_profile():
    return jsonify(dict(ai_agent.MY_PROFILE))

@app.route("/profile", methods=["POST"])
def update_profile():
    data = request.get_json(force=True) or {}
    for k, v in data.items():
        if k in ai_agent.MY_PROFILE:
            ai_agent.MY_PROFILE[k] = str(v)
            _runtime_profile[k] = str(v)
    _sync_profile()
    return jsonify({"status":"saved","profile":dict(ai_agent.MY_PROFILE)})

# ── Excel endpoints ───────────────────────────────────────
@app.route("/excel_list")
def excel_list():
    """Return list of recent Excel files on Desktop."""
    desktop = os.path.expanduser("~") + "\\Desktop"
    pattern = os.path.join(desktop, "*.xlsx")
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)[:10]
    result = []
    for f in files:
        result.append({
            "name": os.path.basename(f),
            "path": f,
            "size": os.path.getsize(f),
            "modified": datetime.fromtimestamp(os.path.getmtime(f)).strftime("%d %b %Y %H:%M"),
        })
    return jsonify(result)

@app.route("/excel_data")
def excel_data():
    """Return latest Excel file content as JSON for dashboard table."""
    name = request.args.get("name","")
    desktop = os.path.expanduser("~") + "\\Desktop"

    if name:
        path = os.path.join(desktop, name)
    else:
        # Latest xlsx
        files = sorted(glob.glob(os.path.join(desktop,"*.xlsx")),
                       key=os.path.getmtime, reverse=True)
        if not files:
            return jsonify({"headers":[],"rows":[],"file":""})
        path = files[0]

    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb.active
        rows_raw = list(ws.iter_rows(values_only=True))
        if len(rows_raw) < 2:
            return jsonify({"headers":[],"rows":[],"file":os.path.basename(path)})
        headers = [str(c) if c else "" for c in rows_raw[1]]  # row 2 = headers (row 1 is title)
        rows = []
        for row in rows_raw[2:]:
            rows.append([str(c) if c is not None else "" for c in row])
        return jsonify({"headers":headers,"rows":rows,"file":os.path.basename(path)})
    except Exception as e:
        return jsonify({"error":str(e),"headers":[],"rows":[],"file":""})

@app.route("/excel_download")
def excel_download():
    name = request.args.get("name","")
    desktop = os.path.expanduser("~") + "\\Desktop"
    path = os.path.join(desktop, name)
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return "File not found", 404

def _run_flask():
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True, use_reloader=False)

# ══════════════════════════════════════════════════════════
# MAIN THREAD — owns Playwright
# ══════════════════════════════════════════════════════════

def main():
    _real_stdout.write("="*60+"\n  🤖 AI AGENT LIVE SERVER v2\n"+"="*60+"\n")
    _real_stdout.write("  Dashboard → http://localhost:5000\n\n")

    threading.Thread(target=_run_flask, daemon=True).start()
    _real_stdout.write("  ✅ Flask started → http://localhost:5000\n\n")

    from playwright.sync_api import sync_playwright
    _output_queue.put({"type":"log","text":"🚀 Starting browser — please wait…"})

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=ai_agent.AGENT_PROFILE,
                channel="chrome", headless=False, slow_mo=80,
                args=["--start-maximized","--disable-blink-features=AutomationControlled"],
                no_viewport=True,
                ignore_default_args=["--enable-automation"],
            )
        except Exception as e:
            _output_queue.put({"type":"log","text":f"❌ Browser failed: {e}"})
            try:
                while True: time.sleep(1)
            except KeyboardInterrupt: return

        page = browser.new_page()
        page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        _stats["browser_ready"] = True
        _output_queue.put({"type":"browser_ready"})
        _output_queue.put({"type":"log","text":"✅ Browser ready — Chrome profile loaded"})

        if not os.path.exists(ai_agent.MY_PROFILE["resume_path"]):
            _output_queue.put({"type":"log","text":f"⚠️  Resume not found: {ai_agent.MY_PROFILE['resume_path']}"})
        else:
            _output_queue.put({"type":"log","text":"✅ Resume found: Param_SoftwareEngineer.pdf"})

        _output_queue.put({"type":"log","text":"🚀 Agent online — use the dashboard buttons to start"})

        try:
            while True:
                try: cmd = _command_queue.get(timeout=1)
                except queue.Empty: continue

                _stats.update({"running":True,"applied":0,"scraped":0,"skipped":0,"errors":0,"current":cmd})
                _output_queue.put({"type":"start","command":cmd})

                try:
                    parsed = ai_agent.parse_command(cmd)
                    _output_queue.put({"type":"intent",
                        "intent":  parsed.get("intent","unknown"),
                        "job":     parsed.get("job_title",""),
                        "location":parsed.get("location",""),
                        "max":     parsed.get("max_apply",5)})
                    ai_agent.execute(parsed, browser, page)
                except Exception as e:
                    import traceback
                    _output_queue.put({"type":"log","text":f"❌ Error: {e}"})
                    _real_stdout.write(traceback.format_exc())
                    _stats["errors"] += 1
                finally:
                    _stats.update({"running":False,"current":""})
                    _output_queue.put({"type":"done","stats":dict(_stats)})

        except KeyboardInterrupt:
            _real_stdout.write("\n👋 Shutting down…\n")
        finally:
            try: browser.close()
            except: pass

if __name__ == "__main__":
    main()