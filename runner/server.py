from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import subprocess
import os

REPO_ROOT = os.environ.get("REPO_ROOT", "/workspace")

class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/run":
            return self._send(404, {"error": "not found"})

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            data = {}

        demo_dir = data.get("demo_dir", "data/demo")
        onboarding_dir = data.get("onboarding_dir", "data/onboarding")
        outputs_dir = data.get("outputs_dir", "outputs")

        cmd = [
            "python", "scripts/run_all.py",
            "--demo_dir", demo_dir,
            "--onboarding_dir", onboarding_dir,
            "--outputs_dir", outputs_dir,
        ]

        p = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
        self._send(200 if p.returncode == 0 else 500, {
            "returncode": p.returncode,
            "stdout": p.stdout[-12000:],
            "stderr": p.stderr[-12000:],
            "ran": " ".join(cmd),
            "cwd": REPO_ROOT
        })

def main():
    port = int(os.environ.get("PORT", "8000"))
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()

if __name__ == "__main__":
    main()