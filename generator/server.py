"""Tiny HTTP server inside the generator container.

The Worker's cron hits POST /generate; we run the watcher in publish mode
(diff list against the API, generate splices, upload to R2/D1) and stream
its output back so it shows up in the Worker logs.
"""
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def _run(self):
        if self.path != "/generate":
            self.send_response(404)
            self.end_headers()
            return
        p = subprocess.run(
            ["python", "generator/watcher.py", "--publish"],
            capture_output=True, text=True, cwd="/app", timeout=60 * 20)
        body = (p.stdout + p.stderr).encode()
        self.send_response(200 if p.returncode == 0 else 500)
        self.send_header("content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body[-10000:])

    do_POST = _run
    do_GET = _run

    def log_message(self, fmt, *args):
        print(fmt % args)


if __name__ == "__main__":
    print("generator listening on :8080")
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
