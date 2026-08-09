"""HTTP server that exposes this machine's system stats as JSON.

Run this on the computer you want to monitor:

    python -m server.server --port 8000
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from server.metrics import collect_stats


class StatsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/stats":
            self.send_response(404)
            self.end_headers()
            return

        body = json.dumps(collect_stats()).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description="Expose system stats over HTTP for the Pi monitor.")
    parser.add_argument("--host", default="0.0.0.0", help="Interface to bind to")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), StatsHandler)
    print(f"Serving stats on http://{args.host}:{args.port}/stats")
    server.serve_forever()


if __name__ == "__main__":
    main()
