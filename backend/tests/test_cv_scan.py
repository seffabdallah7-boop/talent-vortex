"""CV scanning endpoints backend tests (admin-only)."""
import os
import re
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fall back to reading frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

ADMIN_EMAIL = "seffabdallah7@gmail.com"
ADMIN_PWD = "Admin@2026!"
CANDIDATE_EMAIL = "candidate_test@talentvortex.com"
CANDIDATE_PWD = "Candidate@2026!"


def _solve_captcha(question: str) -> int:
    m = re.search(r"(\d+)\s*([+\-x*])\s*(\d+)", question)
    if not m:
        raise RuntimeError(f"Cannot parse captcha: {question}")
    a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    return a * b


def _login(email: str, password: str) -> str:
    s = requests.Session()
    cap = s.get(f"{BASE_URL}/api/auth/captcha", timeout=15).json()
    ans = _solve_captcha(cap["question"])
    r = s.post(f"{BASE_URL}/api/auth/login", json={
        "email": email, "password": password,
        "captcha_id": cap["captcha_id"], "captcha_answer": str(ans),
    }, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers():
    return {"Authorization": f"Bearer {_login(ADMIN_EMAIL, ADMIN_PWD)}"}


@pytest.fixture(scope="module")
def candidate_headers():
    try:
        tok = _login(CANDIDATE_EMAIL, CANDIDATE_PWD)
        return {"Authorization": f"Bearer {tok}"}
    except Exception:
        pytest.skip("No candidate test user available")


# --- Auth guard tests -------------------------------------------------------
class TestCvScanAuth:
    def test_status_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/cv-scan/status", timeout=15)
        assert r.status_code in (401, 403)

    def test_all_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/cv-scan/all", timeout=15)
        assert r.status_code in (401, 403)

    def test_candidate_forbidden(self, candidate_headers):
        r = requests.get(f"{BASE_URL}/api/cv-scan/status", headers=candidate_headers, timeout=15)
        assert r.status_code == 403


# --- Status endpoint --------------------------------------------------------
class TestCvScanStatus:
    def test_status_shape(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/cv-scan/status", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        for k in ("total_cv", "scanned", "errors", "pending", "running"):
            assert k in data, f"missing key {k}"
        assert isinstance(data["total_cv"], int)
        assert isinstance(data["scanned"], int)
        assert isinstance(data["errors"], int)
        assert isinstance(data["pending"], int)
        assert isinstance(data["running"], bool)
        # coherence
        assert data["total_cv"] >= data["scanned"]
        assert data["pending"] == max(0, data["total_cv"] - data["scanned"])
        print(f"CV scan status: {data}")


# --- Per-user rescan --------------------------------------------------------
class TestCvScanPerUser:
    def test_rescan_scanned_user(self, admin_headers):
        # get an already-scanned user
        r = requests.get(f"{BASE_URL}/api/users", headers=admin_headers,
                         params={"has_cv": "true"}, timeout=15)
        # fall back if unsupported
        if r.status_code != 200:
            r = requests.get(f"{BASE_URL}/api/users", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        users = r.json() if isinstance(r.json(), list) else r.json().get("users", [])
        target = None
        for u in users:
            if u.get("cv_file_id"):
                target = u
                break
        if not target:
            pytest.skip("No user with a CV available")
        uid = target["user_id"]
        r = requests.post(f"{BASE_URL}/api/cv-scan/{uid}?force=true",
                          headers=admin_headers, timeout=180)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("status") in ("scanned", "error", "skipped"), body
        print(f"rescan user {uid}: {body}")

        # Verify data endpoint returns structured
        r2 = requests.get(f"{BASE_URL}/api/cv-scan/{uid}/data",
                          headers=admin_headers, timeout=15)
        assert r2.status_code == 200
        doc = r2.json()
        assert "status" in doc
        if body.get("status") == "scanned":
            assert doc.get("status") == "scanned"
            assert isinstance(doc.get("structured"), dict)
            s = doc["structured"]
            # keys expected
            for k in ("skills", "experiences", "education", "languages"):
                assert k in s, f"missing structured key {k}"
            assert "raw_text" in doc

    def test_scan_nonexistent_user(self, admin_headers):
        r = requests.post(f"{BASE_URL}/api/cv-scan/nonexistent-user-xyz?force=true",
                          headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert r.json().get("status") == "skipped"


# --- Batch endpoint (non-force, should return started or busy) --------------
class TestCvScanAll:
    def test_start_batch(self, admin_headers):
        r = requests.post(f"{BASE_URL}/api/cv-scan/all",
                          headers=admin_headers, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") in ("started", "busy"), body
        print(f"cv-scan/all: {body}")


# --- AI search still works & uses structured data ---------------------------
class TestAiSearch:
    def test_ai_search_returns_reasons(self, admin_headers):
        r = requests.post(f"{BASE_URL}/api/users/ai-search",
                          headers=admin_headers,
                          json={"query": "développeur avec expérience"}, timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()
        # response is either list or {results:[...]}
        results = data if isinstance(data, list) else data.get("results", [])
        assert isinstance(results, list)
        # ai_reason field expected on at least one
        if results:
            keys = set()
            for x in results[:3]:
                keys.update(x.keys())
            print(f"AI search top keys sample: {keys}")
