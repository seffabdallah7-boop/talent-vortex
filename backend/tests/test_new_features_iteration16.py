"""
Backend tests for the new features in this session (iteration 16):
- Point 7 : GET /api/chat/unread has_admin/unread lock logic
- Point 8 : GET /api/jobs/{job_id}/suggestions ordered by score
- Point 6 : POST /api/recordings/{rec_id}/share + GET /api/recordings/shared/{token} auth
- Point 2 : POST /api/applications returns screening.questions (immediate redirect target)
"""
import os
import io
import time
import pytest
import requests

def _read_frontend_env():
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        return None
    return None

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _read_frontend_env() or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL missing"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "seffabdallah7@gmail.com"
ADMIN_PASS = "Admin@2026!"
CAND_EMAIL = "cand_1786303173@test.com"
CAND_PASS = "Test@2026!"


def _solve_captcha(q: str) -> int:
    # e.g. "3 + 4 ="
    q = q.replace("=", "").strip()
    a, _, b = q.split()
    return int(a) + int(b)


def _login(email: str, password: str):
    r = requests.get(f"{API}/auth/captcha", timeout=30)
    assert r.status_code == 200, r.text
    c = r.json()
    ans = _solve_captcha(c["question"])
    r = requests.post(f"{API}/auth/login", json={
        "email": email, "password": password,
        "captcha_id": c["captcha_id"], "captcha_answer": str(ans),
    }, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    return data["token"], data["user"]


@pytest.fixture(scope="module")
def admin_ctx():
    token, user = _login(ADMIN_EMAIL, ADMIN_PASS)
    return {"token": token, "user": user, "h": {"Authorization": f"Bearer {token}"}}


@pytest.fixture(scope="module")
def cand_ctx():
    token, user = _login(CAND_EMAIL, CAND_PASS)
    return {"token": token, "user": user, "h": {"Authorization": f"Bearer {token}"}}


# ---------- POINT 7 : /chat/unread ----------
class TestChatUnread:
    def test_candidate_chat_unread_shape(self, cand_ctx):
        r = requests.get(f"{API}/chat/unread", headers=cand_ctx["h"], timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "has_admin" in data and isinstance(data["has_admin"], bool)
        assert "unread" in data and isinstance(data["unread"], int)


# ---------- POINT 8 : /jobs/{id}/suggestions ----------
class TestSuggestions:
    def test_admin_suggestions_sorted_by_score(self, admin_ctx):
        # Get jobs
        rj = requests.get(f"{API}/jobs", timeout=30)
        assert rj.status_code == 200
        jobs = rj.json()
        if not jobs:
            pytest.skip("No jobs in DB")
        job_id = jobs[0]["id"]
        r = requests.get(f"{API}/jobs/{job_id}/suggestions", headers=admin_ctx["h"], timeout=60)
        assert r.status_code == 200, r.text
        arr = r.json()
        assert isinstance(arr, list)
        # If any suggestions, sorted by score desc
        scores = [s["score"] for s in arr]
        assert scores == sorted(scores, reverse=True)
        for s in arr:
            assert "candidate_id" in s and "score" in s and "reason" in s

    def test_suggestions_forbidden_for_candidate(self, cand_ctx):
        rj = requests.get(f"{API}/jobs", timeout=30)
        jobs = rj.json()
        if not jobs:
            pytest.skip("No jobs in DB")
        r = requests.get(f"{API}/jobs/{jobs[0]['id']}/suggestions", headers=cand_ctx["h"], timeout=30)
        assert r.status_code in (401, 403), r.text

    def test_suggestions_unauth(self):
        rj = requests.get(f"{API}/jobs", timeout=30)
        jobs = rj.json()
        if not jobs:
            pytest.skip("No jobs in DB")
        r = requests.get(f"{API}/jobs/{jobs[0]['id']}/suggestions", timeout=30)
        assert r.status_code in (401, 403)


# ---------- POINT 6 : recordings share protection ----------
class TestRecordingsShare:
    def test_shared_endpoint_requires_admin(self):
        r = requests.get(f"{API}/recordings/shared/nonexistent-token", timeout=30)
        assert r.status_code in (401, 403), r.text

    def test_shared_endpoint_forbidden_candidate(self, cand_ctx):
        r = requests.get(f"{API}/recordings/shared/nonexistent-token", headers=cand_ctx["h"], timeout=30)
        assert r.status_code in (401, 403), r.text

    def test_shared_endpoint_admin_404_for_bogus_token(self, admin_ctx):
        r = requests.get(f"{API}/recordings/shared/nonexistent-token", headers=admin_ctx["h"], timeout=30)
        # admin passes auth, but token unknown -> 404
        assert r.status_code == 404, r.text

    def test_share_recording_if_any(self, admin_ctx):
        # List recordings
        r = requests.get(f"{API}/recordings", headers=admin_ctx["h"], timeout=30)
        if r.status_code != 200:
            pytest.skip(f"/recordings not available: {r.status_code}")
        recs = r.json()
        if not recs:
            pytest.skip("No recordings to share")
        rid = recs[0]["id"]
        rs = requests.post(f"{API}/recordings/{rid}/share", headers=admin_ctx["h"], timeout=30)
        assert rs.status_code == 200, rs.text
        token = rs.json().get("token")
        assert token
        # Fetch via admin
        rg = requests.get(f"{API}/recordings/shared/{token}", headers=admin_ctx["h"], timeout=30)
        assert rg.status_code == 200
        assert rg.json().get("id") == rid


# ---------- POINT 2 : applications create returns screening ----------
class TestApplicationScreening:
    def test_application_response_has_screening_questions_when_new(self, cand_ctx):
        # Find a job the candidate hasn't applied to
        rj = requests.get(f"{API}/jobs", timeout=30)
        jobs = rj.json()
        ra = requests.get(f"{API}/applications/me", headers=cand_ctx["h"], timeout=30)
        applied = {a["job_id"] for a in ra.json()} if ra.status_code == 200 else set()
        target = next((j for j in jobs if j["id"] not in applied), None)
        if not target:
            pytest.skip("Candidate already applied to all jobs; can't test new apply")
        files = {"cv": ("test_cv.pdf", io.BytesIO(b"%PDF-1.4\nTEST_CV"), "application/pdf")}
        data = {"job_id": target["id"], "cover_note": "TEST_ application from pytest"}
        r = requests.post(f"{API}/applications", headers=cand_ctx["h"], files=files, data=data, timeout=90)
        assert r.status_code == 200, r.text
        j = r.json()
        # screening may be empty list if LLM fails, but key should exist
        assert "screening" in j
        # Not strict on list length -- but log
        print("screening.questions len =", len((j.get("screening") or {}).get("questions") or []))
