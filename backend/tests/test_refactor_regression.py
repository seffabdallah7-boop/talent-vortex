"""Post-refactor regression tests: verify every router still exposes its endpoints."""
import os
import re
import time
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "seffabdallah7@gmail.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")


def _solve_captcha(s: requests.Session):
    r = s.get(f"{API}/auth/captcha", timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    m = re.match(r"\s*(\d+)\s*\+\s*(\d+)", j["question"])
    return j["captcha_id"], str(int(m.group(1)) + int(m.group(2)))


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    cid, ans = _solve_captcha(s)
    r = s.post(f"{API}/auth/login", json={
        "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD,
        "captcha_id": cid, "captcha_answer": ans,
    }, timeout=20)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    token = r.json()["token"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def candidate_session():
    s = requests.Session()
    cid, ans = _solve_captcha(s)
    email = f"TEST_cand_{int(time.time())}@test.com"
    r = s.post(f"{API}/auth/register", json={
        "name": "TEST Cand", "email": email, "password": "Test@2026!",
        "captcha_id": cid, "captcha_answer": ans,
    }, timeout=20)
    assert r.status_code == 200, f"Register failed: {r.status_code} {r.text}"
    data = r.json()
    token = data["token"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s, data["user"]


# --- Auth
class TestAuth:
    def test_captcha(self):
        r = requests.get(f"{API}/auth/captcha", timeout=10)
        assert r.status_code == 200
        j = r.json()
        assert "captcha_id" in j and "question" in j

    def test_admin_login_and_refresh(self, admin_session):
        r = admin_session.post(f"{API}/auth/refresh", timeout=15)
        assert r.status_code == 200
        assert "token" in r.json() and r.json()["user"]["role"] == "admin"


# --- Jobs
class TestJobs:
    def test_list_jobs_public(self):
        r = requests.get(f"{API}/jobs", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_jobs_all_admin(self, admin_session):
        r = admin_session.get(f"{API}/jobs/all", timeout=15)
        assert r.status_code == 200

    def test_job_crud(self, admin_session):
        payload = {"title": "TEST_Job", "description": "desc", "requirements": "req",
                   "location": "Remote", "type": "CDI", "company": "TEST Co"}
        r = admin_session.post(f"{API}/jobs", json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text
        job = r.json()
        jid = job.get("id") or job.get("job_id")
        assert jid
        # Update
        r2 = admin_session.put(f"{API}/jobs/{jid}", json={**payload, "title": "TEST_Job2"}, timeout=15)
        assert r2.status_code == 200
        # Toggle active
        r3 = admin_session.put(f"{API}/jobs/{jid}/active", json={"is_active": False}, timeout=15)
        assert r3.status_code == 200
        # Suggestions
        r4 = admin_session.get(f"{API}/jobs/{jid}/suggestions", timeout=20)
        assert r4.status_code == 200
        # Delete
        r5 = admin_session.delete(f"{API}/jobs/{jid}", timeout=15)
        assert r5.status_code in (200, 204)


# --- Applications
class TestApplications:
    def test_list_applications_admin(self, admin_session):
        r = admin_session.get(f"{API}/applications", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# --- Users / candidates / nationalities
class TestUsers:
    def test_users_list(self, admin_session):
        r = admin_session.get(f"{API}/users", timeout=15)
        assert r.status_code == 200

    def test_candidates_list(self, admin_session):
        r = admin_session.get(f"{API}/candidates", timeout=15)
        assert r.status_code == 200

    def test_nationalities(self, admin_session):
        r = admin_session.get(f"{API}/admin/nationalities", timeout=15)
        assert r.status_code == 200


# --- Chat (regression + NEW delete endpoint)
class TestChat:
    def test_conversations_admin_only(self):
        r = requests.get(f"{API}/chat/conversations", timeout=15)
        assert r.status_code in (401, 403)

    def test_conversations_admin(self, admin_session):
        r = admin_session.get(f"{API}/chat/conversations", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_candidate_unread(self, candidate_session):
        s, _ = candidate_session
        r = s.get(f"{API}/chat/unread", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert "unread" in j and "active" in j

    def test_typing(self, candidate_session):
        s, _ = candidate_session
        r = s.post(f"{API}/chat/typing", json={}, timeout=10)
        assert r.status_code == 200

    def test_full_conv_flow_and_delete(self, admin_session, candidate_session):
        s_cand, cand_user = candidate_session
        cid = cand_user["user_id"]
        # activate
        r = admin_session.put(f"{API}/chat/conversations/{cid}/active", json={"active": True}, timeout=15)
        assert r.status_code == 200
        # candidate sends message
        r = s_cand.post(f"{API}/chat/messages", json={"text": "TEST hello"}, timeout=15)
        assert r.status_code == 200
        # admin lists conversations, must include cid
        convs = admin_session.get(f"{API}/chat/conversations", timeout=15).json()
        assert any(c["candidate_id"] == cid for c in convs), "Conversation not found after send"
        # admin fetches messages
        r = admin_session.get(f"{API}/chat/messages", params={"candidate_id": cid}, timeout=15)
        assert r.status_code == 200
        assert len(r.json()["messages"]) >= 1

        # NEW: unauthorized cannot delete
        r = requests.delete(f"{API}/chat/conversations/{cid}", timeout=15)
        assert r.status_code in (401, 403)
        # candidate also cannot delete
        r = s_cand.delete(f"{API}/chat/conversations/{cid}", timeout=15)
        assert r.status_code in (401, 403)
        # admin CAN delete
        r = admin_session.delete(f"{API}/chat/conversations/{cid}", timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True
        # conversation gone from list
        convs2 = admin_session.get(f"{API}/chat/conversations", timeout=15).json()
        assert not any(c["candidate_id"] == cid for c in convs2), "Conversation still present after delete"


# --- Calls / recordings
class TestCalls:
    def test_recordings_admin(self, admin_session):
        r = admin_session.get(f"{API}/recordings", timeout=15)
        assert r.status_code == 200

    def test_calls_incoming_admin(self, admin_session):
        r = admin_session.get(f"{API}/calls/incoming", timeout=15)
        assert r.status_code == 200


# --- Interviews
class TestInterviews:
    def test_interviews_admin(self, admin_session):
        r = admin_session.get(f"{API}/interviews", timeout=15)
        assert r.status_code == 200

    def test_interviews_me(self, candidate_session):
        s, _ = candidate_session
        r = s.get(f"{API}/interviews/me", timeout=15)
        assert r.status_code == 200


# --- Contracts
class TestContracts:
    def test_contracts_admin(self, admin_session):
        r = admin_session.get(f"{API}/contracts", timeout=15)
        assert r.status_code == 200

    def test_contracts_me(self, candidate_session):
        s, _ = candidate_session
        r = s.get(f"{API}/contracts/me", timeout=15)
        assert r.status_code == 200


# --- Misc (stats, theme, notifications, ai)
class TestMisc:
    def test_admin_stats(self, admin_session):
        r = admin_session.get(f"{API}/admin/stats", timeout=15)
        assert r.status_code == 200

    def test_theme_public(self):
        r = requests.get(f"{API}/settings/theme", timeout=15)
        assert r.status_code == 200

    def test_notifications(self, candidate_session):
        s, _ = candidate_session
        r = s.get(f"{API}/notifications", timeout=15)
        assert r.status_code == 200

    def test_ai_chat(self, candidate_session):
        s, _ = candidate_session
        r = s.post(f"{API}/ai/chat", json={"message": "Bonjour"}, timeout=45)
        # AI may fail if key missing, but endpoint must exist (not 404)
        assert r.status_code != 404, "Endpoint /api/ai/chat missing"
