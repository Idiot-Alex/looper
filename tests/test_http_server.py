import os
import sys
import subprocess
import tempfile
import time
import signal
import threading

HTTP_PORT = 8000
EXPECTED_CONTENT = "test c"

def start_http_server(directory):
    """Start Python HTTP server in the given directory."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(HTTP_PORT), "--directory", directory],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return proc

def run_curl_test():
    """Test the HTTP server with curl."""
    import requests
    try:
        resp = requests.get(f"http://localhost:{HTTP_PORT}/index.html", timeout=5)
        if resp.status_code != 200:
            print(f"FAIL: HTTP status code {resp.status_code}")
            sys.exit(1)
        if EXPECTED_CONTENT not in resp.text:
            print(f"FAIL: Response body does not contain '{EXPECTED_CONTENT}'")
            sys.exit(1)
        print("PASS: All checks passed.")
    except Exception as e:
        print(f"FAIL: Request failed - {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Create temporary directory with index.html
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = os.path.join(tmpdir, "index.html")
        with open(index_path, "w") as f:
            f.write(EXPECTED_CONTENT)
        print(f"Created {index_path}")

        # Start HTTP server
        server_proc = start_http_server(tmpdir)
        time.sleep(1)  # Wait for server to start

        try:
            run_curl_test()
        finally:
            # Shutdown server
            server_proc.send_signal(signal.SIGINT)
            server_proc.wait()
