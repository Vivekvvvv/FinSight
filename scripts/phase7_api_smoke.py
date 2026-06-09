#!/usr/bin/env python3
"""Phase 7 API Smoke Test"""
import sys
import io
import time
import json
import urllib.request
import urllib.error

# Windows GBK terminal fix
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8000"
SESSION = "public:anonymous:phase7-smoke"
USER = "phase7_smoke_user"

results = []

def check(name: str, path: str, *, required_keys: list[str] = None, expect_status: int = 200):
    url = f"{BASE}{path}"
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            elapsed = round((time.time() - t0) * 1000)
            status = resp.status
            body = json.loads(resp.read())
            ok = status == expect_status
            missing = [k for k in (required_keys or []) if k not in body]
            result = {
                "name": name,
                "url": url,
                "status": status,
                "elapsed_ms": elapsed,
                "pass": ok and not missing,
                "missing_keys": missing,
                "error": None,
            }
            results.append(result)
            sym = "✓" if result["pass"] else "✗"
            print(f"  {sym} {name:45s} {status} {elapsed:4d}ms", end="")
            if missing:
                print(f"  MISSING: {missing}", end="")
            print()
            return body
    except urllib.error.HTTPError as e:
        elapsed = round((time.time() - t0) * 1000)
        results.append({"name": name, "url": url, "status": e.code, "elapsed_ms": elapsed,
                         "pass": e.code == expect_status, "missing_keys": [], "error": str(e)})
        sym = "✓" if e.code == expect_status else "✗"
        print(f"  {sym} {name:45s} {e.code} {elapsed:4d}ms  HTTP error")
    except Exception as e:
        elapsed = round((time.time() - t0) * 1000)
        results.append({"name": name, "url": url, "status": 0, "elapsed_ms": elapsed,
                         "pass": False, "missing_keys": [], "error": str(e)})
        print(f"  ✗ {name:45s} ERR  {elapsed:4d}ms  {e}")


print("=" * 60)
print("Phase 7 API Smoke Test")
print(f"Base: {BASE}")
print(f"Session: {SESSION}")
print("=" * 60)

print("\n[1] Health & Auth")
check("/health", "/health", required_keys=["status", "version"])
check("/api/me", f"/api/me?session_id={SESSION}&user_id={USER}",
      required_keys=["success", "user_id"])

print("\n[2] Today Workspace")
body = check("/api/today", f"/api/today?session_id={SESSION}&user_id={USER}",
      required_keys=["success", "portfolio_snapshot", "next_actions"])

print("\n[3] Research APIs")
check("/api/research-quality", f"/api/research-quality?session_id={SESSION}&user_id={USER}",
      required_keys=["success", "summary"])
check("/api/what-changed", f"/api/what-changed?session_id={SESSION}&user_id={USER}",
      required_keys=["success", "items"])
check("/api/research-notes", f"/api/research-notes?session_id={SESSION}&user_id={USER}",
      required_keys=["success"])

print("\n[4] Portfolio & Watchlist")
check("/api/portfolio/summary", f"/api/portfolio/summary?session_id={SESSION}&user_id={USER}",
      required_keys=["success", "positions"])
check("/api/portfolio/risk-lens", f"/api/portfolio/risk-lens?session_id={SESSION}&user_id={USER}",
      required_keys=["success"])
check("/api/user/watchlist", f"/api/user/watchlist?session_id={SESSION}&user_id={USER}",
      required_keys=["success", "items"])

print("\n[5] Reports & Timeline")
check("/api/reports/index", f"/api/reports/index?session_id={SESSION}&user_id={USER}",
      required_keys=["success", "items"])
check("/api/timeline/AAPL", f"/api/timeline/AAPL?session_id={SESSION}&user_id={USER}",
      required_keys=["success", "events"])

print("\n[6] Alerts")
check("/api/alerts/feed", f"/api/alerts/feed?email=smoke@example.invalid",
      required_keys=["success"])

print("\n[7] Market Data (no real API keys — graceful fallback expected)")
check("/api/quote/AAPL", f"/api/quote/AAPL?session_id={SESSION}&user_id={USER}")

# Summary
passed = sum(1 for r in results if r["pass"])
total = len(results)
print("\n" + "=" * 60)
print(f"Result: {passed}/{total} passed")

# Write JSON results
out_path = "PHASE7_API_SMOKE_RESULTS.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "base": BASE, "passed": passed, "total": total, "results": results}, f, indent=2)
print(f"Results saved to {out_path}")

if passed < total:
    sys.exit(1)
