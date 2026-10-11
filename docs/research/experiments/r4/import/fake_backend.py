import http.server, json
class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def do_POST(self):
        n = 0
        if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
            while True:
                line = self.rfile.readline().strip()
                size = int(line, 16)
                if size == 0:
                    self.rfile.readline(); break
                self.rfile.read(size); self.rfile.readline(); n += size
        else:
            n = int(self.headers.get("Content-Length", "0")); left = n
            while left > 0:
                left -= len(self.rfile.read(min(65536, left)))
        body = json.dumps({"received": n, "path": self.path}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass
http.server.ThreadingHTTPServer(("0.0.0.0", 8000), H).serve_forever()
