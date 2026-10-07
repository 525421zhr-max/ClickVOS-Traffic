"""Start/stop the local GPU gateway and a loopback-only connection page in WSL."""
from __future__ import annotations

import argparse
import html
import json
import os
import secrets
import signal
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "outputs/tasks/unified-site-v1/runtime"
SETTINGS = RUNTIME / "settings.json"
SITE = "https://clickvos-traffic-portfolio.elven-trail-5448.chatgpt.site"


def connection_page():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.path != "/" or self.headers.get("Host") not in ("127.0.0.1:7882", "localhost:7882"):
                self.send_error(404)
                return
            settings = json.loads(SETTINGS.read_text())
            endpoint_file = RUNTIME / "tunnel-url.txt"
            endpoint = endpoint_file.read_text().strip() if endpoint_file.exists() else ""
            local = "http://127.0.0.1:7880/#workbench?" + urlencode({"service": "http://127.0.0.1:7880", "key": settings["token"]})
            remote = SITE + "/#workbench?" + urlencode({"service": endpoint, "key": settings["token"]})
            remote_link = f'<a href="{html.escape(remote, quote=True)}">打开在线网站并连接本机 GPU</a>' if endpoint.startswith("https://") else '<p>在线连接尚未启动，可以先使用本机工作台。</p>'
            body = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>ClickVOS 连接入口</title><style>body{{font-family:system-ui,sans-serif;background:#f8faf7;color:#173c3b;max-width:650px;margin:12vh auto;padding:24px;line-height:1.8}}h1{{font-size:30px}}a{{display:block;background:#1e6560;color:white;padding:12px 18px;margin:18px 0;text-decoration:none;border-radius:4px}}a.local{{background:#edf3ed;color:#173c3b}}small{{color:#526962}}</style><h1>连接你的标注工作台</h1><p>打开后即可上传交通视频、点选目标、运行分割和下载标注包。</p>{remote_link}<a class="local" href="{html.escape(local, quote=True)}">打开本机工作台</a><small>此入口包含本次服务访问权限，请勿公开分享。电脑和服务需要保持运行；临时在线连接重启后会改变。本站为单人操作工作台。</small></html>'''.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)
    HTTPServer(("127.0.0.1", 7882), Handler).serve_forever()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("start", "stop", "connection"))
    parser.add_argument("--static-dir", type=Path, default=ROOT / "web/site")
    parser.add_argument("--checkpoint", type=Path, default=Path("/home/clickvos/sam2.1-hiera-tiny-modelscope-20260914/sam2.1_hiera_tiny.pt"))
    args = parser.parse_args()
    if args.action == "connection":
        connection_page()
        return
    RUNTIME.mkdir(parents=True, exist_ok=True)
    pids = RUNTIME / "processes.json"
    if args.action == "stop":
        if pids.exists():
            for pid in json.loads(pids.read_text()).values():
                command = Path(f"/proc/{pid}/cmdline")
                if command.exists() and any(name in command.read_bytes() for name in (b"clickvos.site_api", b"manage_unified_site.py")):
                    os.kill(pid, signal.SIGTERM)
            pids.unlink()
        print("Local workbench services stopped.")
        return
    if pids.exists():
        running = [Path(f"/proc/{pid}/cmdline").exists() for pid in json.loads(pids.read_text()).values()]
        if all(running):
            print("Workbench is already running. Open http://127.0.0.1:7882/.")
            return
        if any(running):
            raise SystemExit("A workbench service is still running. Use stop before restarting.")
    if not (args.static_dir / "index.html").is_file() or not args.checkpoint.is_file():
        raise SystemExit("Website files or model checkpoint missing.")
    config = json.loads((ROOT / "configs/default.json").read_text())
    config["task"]["tasks_root"] = str(ROOT / "outputs/tasks/unified-site-v1/tasks")
    config_path = RUNTIME / "config.json"
    config_path.write_text(json.dumps(config))
    settings = {"config": str(config_path), "checkpoint": str(args.checkpoint), "static_dir": str(args.static_dir.resolve()),
                "token": secrets.token_urlsafe(32), "port": 7880,
                "origins": [SITE, "http://127.0.0.1:7870", "http://127.0.0.1:7880", "http://localhost:7880"]}
    SETTINGS.write_text(json.dumps(settings))
    SETTINGS.chmod(0o600)
    (RUNTIME / "tunnel-url.txt").unlink(missing_ok=True)
    env = {**os.environ, "CLICKVOS_SITE_SETTINGS": str(SETTINGS)}
    children = {}
    for name, command in (("gateway", [sys.executable, "-m", "clickvos.site_api"]),
                          ("connection", [sys.executable, str(Path(__file__).resolve()), "connection"])):
        with (RUNTIME / (name + ".log")).open("ab") as log:
            child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        children[name] = child.pid
    pids.write_text(json.dumps(children))
    print("Workbench started. Open http://127.0.0.1:7882/ for the connection link.")


if __name__ == "__main__":
    main()
