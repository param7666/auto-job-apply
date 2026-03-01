"""
╔══════════════════════════════════════════════════════════╗
║   🌐 AI AGENT — LIVE SERVER (Thread-Safe Fix)           ║
║   Run: python server.py                                 ║
║   Then open: http://localhost:5000                      ║
║   Developer: Parmeshwar Gurlewad                        ║
╚══════════════════════════════════════════════════════════╝

Install Flask first:  pip install flask
Then run:             python server.py

KEY FIX: Playwright sync_api is NOT thread-safe.
  - Main thread  → owns the browser + runs all Playwright calls
  - Flask thread → handles HTTP requests, puts commands in a queue
  - Commands are passed via queue from Flask → main thread
"""

import sys
import os
import threading
import queue
import json
import time
from datetime import datetime

# ── Save real stdout BEFORE any patching ──────────────────
_real_stdout = sys.stdout
_real_stderr = sys.stderr

# ══════════════════════════════════════════════════════════
# SHARED QUEUES & STATE
# ══════════════════════════════════════════════════════════

_output_queue  = queue.Queue()   # agent → dashboard (SSE)
_command_queue = queue.Queue()   # HTTP  → main thread (commands)
_input_queue   = queue.Queue()   # HTTP  → main thread (input answers)

_waiting_for_input = threading.Event()

_stats = {
    "applied":       0,
    "scraped":       0,
    "skipped":       0,
    "errors":        0,
    "running":       False,
    "current":       "",
    "browser_ready": False,
}

# ══════════════════════════════════════════════════════════
# CAPTURED STDOUT
# ══════════════════════════════════════════════════════════

class _AgentStdout:
    def write(self, text):
        _real_stdout.write(text)
        _real_stdout.flush()
        stripped = text.rstrip()
        if stripped:
            _output_queue.put({"type": "log", "text": stripped})
            _parse_stats(stripped)

    def flush(self):
        _real_stdout.flush()

    def fileno(self):
        return _real_stdout.fileno()


def _parse_stats(text):
    t = text.lower()
    if "🎉 applied!" in t or "applied! total:" in t:
        _stats["applied"] += 1
    if "✅ scraped" in t and "unique" in t:
        try:
            nums = [int(s) for s in t.split() if s.isdigit()]
            if nums:
                _stats["scraped"] = max(nums)
        except:
            pass
    if "🚫 external" in t or "skipped (external)" in t:
        _stats["skipped"] += 1
    if "❌" in text and "nav error" not in t:
        _stats["errors"] += 1

# ══════════════════════════════════════════════════════════
# PATCHED input()
# ══════════════════════════════════════════════════════════

def _patched_input(prompt=""):
    prompt_str = str(prompt).strip()
    _real_stdout.write(f"\n[INPUT REQUESTED] {prompt_str}\n")
    _real_stdout.flush()
    _output_queue.put({"type": "input_request", "prompt": prompt_str})
    _waiting_for_input.set()
    try:
        answer = _input_queue.get(timeout=300)
        _real_stdout.write(f"[INPUT RECEIVED] {answer}\n")
        _real_stdout.flush()
        _output_queue.put({"type": "input_given", "value": answer})
        return answer
    except queue.Empty:
        _real_stdout.write("[INPUT TIMEOUT — defaulting to 'yes']\n")
        _real_stdout.flush()
        return "yes"
    finally:
        _waiting_for_input.clear()

# ══════════════════════════════════════════════════════════
# PATCH BEFORE IMPORTING ai_agent
# ══════════════════════════════════════════════════════════

import builtins
builtins.input = _patched_input
sys.stdout = _AgentStdout()

_agent_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _agent_dir)
import ai_agent

# ══════════════════════════════════════════════════════════
# FLASK APP  (runs in daemon thread, never touches Playwright)
# ══════════════════════════════════════════════════════════

from flask import Flask, Response, request, jsonify, send_from_directory

app = Flask(__name__)


@app.route("/")
def index():
    return send_from_directory(_agent_dir, "dashboard.html")


@app.route("/events")
def events():
    def generate():
        yield f"data: {json.dumps({'type': 'connected', 'stats': dict(_stats)})}\n\n"
        while True:
            try:
                msg = _output_queue.get(timeout=3)
                yield f"data: {json.dumps(msg)}\n\n"
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Connection":                  "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.route("/status")
def status():
    return jsonify(dict(_stats))


@app.route("/command", methods=["POST"])
def command():
    if _stats["running"]:
        return jsonify({"error": "Agent is already running. Wait for it to finish."}), 400

    data = request.get_json(force=True) or {}
    cmd  = data.get("command", "").strip()
    if not cmd:
        return jsonify({"error": "Empty command"}), 400

    # Just put it in the queue — main thread will pick it up
    _command_queue.put(cmd)
    return jsonify({"status": "queued"})


@app.route("/respond", methods=["POST"])
def respond():
    data = request.get_json(force=True) or {}
    val  = data.get("value", "yes")
    _input_queue.put(val)
    return jsonify({"status": "ok"})


@app.route("/stop", methods=["POST"])
def stop_route():
    _stats["running"] = False
    _output_queue.put({"type": "log",  "text": "⛔ Stop requested by user."})
    _output_queue.put({"type": "done", "stats": dict(_stats)})
    return jsonify({"status": "stopped"})


def _run_flask():
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True, use_reloader=False)

# ══════════════════════════════════════════════════════════
# MAIN THREAD — owns Playwright, loops on command queue
# ══════════════════════════════════════════════════════════

def main():
    _real_stdout.write("=" * 60 + "\n")
    _real_stdout.write("  🤖 AI AGENT LIVE SERVER\n")
    _real_stdout.write("=" * 60 + "\n")
    _real_stdout.write("  Dashboard → http://localhost:5000\n")
    _real_stdout.write("  Press Ctrl+C to quit\n")
    _real_stdout.write("=" * 60 + "\n\n")

    # Start Flask in background thread
    threading.Thread(target=_run_flask, daemon=True).start()
    _real_stdout.write("  ✅ Flask started → http://localhost:5000\n\n")

    # ── Playwright lives here — in the MAIN thread ────────
    from playwright.sync_api import sync_playwright

    _real_stdout.write("  🚀 Opening browser…\n")
    _output_queue.put({"type": "log", "text": "🚀 Starting browser — please wait…"})

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=ai_agent.AGENT_PROFILE,
                channel="chrome",
                headless=False,
                slow_mo=80,
                args=["--start-maximized",
                      "--disable-blink-features=AutomationControlled"],
                no_viewport=True,
                ignore_default_args=["--enable-automation"],
            )
        except Exception as e:
            _output_queue.put({"type": "log", "text": f"❌ Browser launch failed: {e}"})
            _real_stdout.write(f"Browser launch failed: {e}\n")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                return

        page = browser.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )

        _stats["browser_ready"] = True
        _output_queue.put({"type": "browser_ready"})
        _output_queue.put({"type": "log", "text": "✅ Browser ready — Chrome profile loaded"})

        if not os.path.exists(ai_agent.MY_PROFILE["resume_path"]):
            _output_queue.put({"type": "log",
                               "text": f"⚠️  Resume not found: {ai_agent.MY_PROFILE['resume_path']}"})
        else:
            _output_queue.put({"type": "log", "text": "✅ Resume found: Param_SoftwareEngineer.pdf"})

        _output_queue.put({"type": "log", "text": "🚀 Agent online and waiting for commands"})

        # ── Command loop — everything Playwright runs here ─
        try:
            while True:
                try:
                    cmd = _command_queue.get(timeout=1)
                except queue.Empty:
                    continue

                # Reset session stats
                _stats["running"] = True
                _stats["applied"] = 0
                _stats["scraped"] = 0
                _stats["skipped"] = 0
                _stats["errors"]  = 0
                _stats["current"] = cmd

                _output_queue.put({"type": "start", "command": cmd})

                try:
                    parsed = ai_agent.parse_command(cmd)
                    _output_queue.put({
                        "type":     "intent",
                        "intent":   parsed.get("intent", "unknown"),
                        "job":      parsed.get("job_title", ""),
                        "location": parsed.get("location", ""),
                        "max":      parsed.get("max_apply", 5),
                    })
                    # ✅ execute() called in main thread = Playwright happy
                    ai_agent.execute(parsed, browser, page)

                except Exception as e:
                    import traceback
                    _output_queue.put({"type": "log", "text": f"❌ Error: {e}"})
                    _real_stdout.write(traceback.format_exc())
                    _stats["errors"] += 1

                finally:
                    _stats["running"] = False
                    _stats["current"] = ""
                    _output_queue.put({"type": "done", "stats": dict(_stats)})

        except KeyboardInterrupt:
            _real_stdout.write("\n👋 Shutting down…\n")
        finally:
            try:
                browser.close()
            except:
                pass


if __name__ == "__main__":
    main()