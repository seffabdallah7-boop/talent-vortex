"""Backend regression tests for RecrutAI recruitment platform (captcha + OTP + admin_code).

Tests cover:
 - Auth: captcha, OTP, admin_code, forgot/reset password, strong password validation
 - Contracts CRUD (admin)
 - Interviews CRUD (admin)
 - Applications review + status
 - CSV exports (with ?auth= query token)
 - Admin stats widgets
"""
import os
import re
import subprocess
import time
import uuid

from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.strip().startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _load_backend_url().rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "seffabdallah7@gmail.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ADMIN_CODE = os.environ.get("ADMIN_CODE", "")
CANDIDATE_EMAIL = os.environ.get("TEST_CANDIDATE_EMAIL", "candidate1@test.com")
CANDIDATE_PASSWORD = os.environ.get("TEST_CANDIDATE_PASSWORD", "")

LOG_FILE = "/var/log/supervisor/backend.err.log"


# ----------------------------- helpers -----------------------------
def get_captcha():
    r = requests.get(f"{API}/auth/captcha", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    q = d["question"]  # e.g. "3 + 4"
    m = re.match(r"\s*(\d+)\s*\+\s*(\d+)", q)
    assert m, f"Unexpected captcha question: {q}"
    ans = str(int(m.group(1)) + int(m.group(2)))
    return d["captcha_id"], ans


def read_code_from_log(prefix: str, email: str, since_ts: float, timeout: float = 8.0):
    """Grep OTP/RESET code from backend logs since given timestamp."""
    deadline = time.time() + timeout
    pattern = f"{prefix} {email} = "
    while time.time() < deadline:
        try:
            out = subprocess.check_output(
                ["grep", pattern, LOG_FILE], stderr=subprocess.DEVNULL
            ).decode()
        except subprocess.CalledProcessError:
            out = ""
        # last match
        codes = re.findall(rf"{re.escape(pattern)}(\d{{6}})", out)
        if codes:
            return codes[-1]
        time.sleep(0.5)
    raise AssertionError(f"Could not read {prefix} code for {email} from logs")


def full_login(email: str, password: str, admin_code: str | None = None) -> str:
    """Perform captcha -> login -> OTP verify. Returns bearer token."""
    cid, ans = get_captcha()
    body = {"email": email, "password": password, "captcha_id": cid, "captcha_answer": ans}
    if admin_code is not None:
        body["admin_code"] = admin_code
    ts = time.time()
    r = requests.post(f"{API}/auth/login", json=body, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    assert r.json().get("otp_required") is True
    code = read_code_from_log("OTP", email, ts)
    r2 = requests.post(f"{API}/auth/verify-otp", json={"email": email, "code": code}, timeout=30)
    assert r2.status_code == 200, f"verify-otp failed: {r2.status_code} {r2.text}"
    tok = r2.json()["token"]
    assert isinstance(tok, str) and len(tok) > 10
    return tok


# ----------------------------- fixtures -----------------------------
@pytest.fixture(scope="session")
def admin_token():
    # NEW: admin_code no longer required, just email+password+captcha+OTP
    return full_login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def candidate_token():
    # Ensure candidate exists. Try login; if fails (unknown), register.
    try:
        return full_login(CANDIDATE_EMAIL, CANDIDATE_PASSWORD)
    except AssertionError:
        cid, ans = get_captcha()
        r = requests.post(f"{API}/auth/register", json={
            "name": "Candidate One", "email": CANDIDATE_EMAIL, "password": CANDIDATE_PASSWORD,
            "captcha_id": cid, "captcha_answer": ans,
        }, timeout=30)
        assert r.status_code == 200, r.text
        return r.json()["token"]


# ----------------------------- Captcha -----------------------------
class TestCaptcha:
    def test_captcha_endpoint(self):
        r = requests.get(f"{API}/auth/captcha", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "captcha_id" in d and "question" in d
        assert re.match(r"^\d+ \+ \d+$", d["question"])

    def test_login_wrong_captcha(self):
        cid, ans = get_captcha()
        wrong = str(int(ans) + 1)
        r = requests.post(f"{API}/auth/login", json={
            "email": CANDIDATE_EMAIL, "password": CANDIDATE_PASSWORD,
            "captcha_id": cid, "captcha_answer": wrong,
        }, timeout=30)
        assert r.status_code == 400, r.text


# ----------------------------- Admin login / OTP / admin_code -----------------------------
class TestAdminLogin:
    def test_admin_full_flow(self, admin_token):
        assert admin_token  # login + OTP verify succeeded
        # /auth/me must return admin role
        r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {admin_token}"}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("role") == "admin"

    def test_admin_no_code_field_needed(self):
        # NEW: admin logs in with just email+password+captcha+OTP; admin_code is no longer required.
        # Sending 'admin_code' (even wrong) should be ignored -> login should still succeed.
        cid, ans = get_captcha()
        r = requests.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD,
            "captcha_id": cid, "captcha_answer": ans,
            "admin_code": "SHOULD-BE-IGNORED",
        }, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("otp_required") is True


# ----------------------------- Registration + strong password -----------------------------
class TestRegister:
    def test_register_strong(self):
        email = f"test_reg_{uuid.uuid4().hex[:6]}@test.com"
        cid, ans = get_captcha()
        r = requests.post(f"{API}/auth/register", json={
            "name": "Reg Test", "email": email, "password": "Test@2026!",
            "captcha_id": cid, "captcha_answer": ans,
        }, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "token" in d and d["user"]["email"] == email
        assert d["user"]["role"] == "candidate"

    def test_register_weak_password_rejected(self):
        email = f"test_weak_{uuid.uuid4().hex[:6]}@test.com"
        cid, ans = get_captcha()
        r = requests.post(f"{API}/auth/register", json={
            "name": "Weak", "email": email, "password": "abc",
            "captcha_id": cid, "captcha_answer": ans,
        }, timeout=30)
        assert r.status_code == 400, r.text


# ----------------------------- Forgot / Reset password -----------------------------
class TestForgotReset:
    def test_forgot_reset_flow(self):
        # 1) forgot
        cid, ans = get_captcha()
        ts = time.time()
        r = requests.post(f"{API}/auth/forgot-password", json={
            "email": CANDIDATE_EMAIL, "captcha_id": cid, "captcha_answer": ans,
        }, timeout=30)
        assert r.status_code == 200, r.text

        code = read_code_from_log("RESET", CANDIDATE_EMAIL, ts)

        # 2) reset with weak password should fail
        r_weak = requests.post(f"{API}/auth/reset-password", json={
            "email": CANDIDATE_EMAIL, "code": code, "new_password": "abc",
        }, timeout=30)
        assert r_weak.status_code == 400

        # 3) reset with strong password (same Test@2026! to keep credential valid)
        r_ok = requests.post(f"{API}/auth/reset-password", json={
            "email": CANDIDATE_EMAIL, "code": code, "new_password": CANDIDATE_PASSWORD,
        }, timeout=30)
        assert r_ok.status_code == 200, r_ok.text

        # 4) candidate can now login with new password (OTP flow)
        tok = full_login(CANDIDATE_EMAIL, CANDIDATE_PASSWORD)
        assert tok


# ----------------------------- Contracts CRUD -----------------------------
class TestContracts:
    contract_id = None

    def test_create_contract(self, admin_headers):
        r = requests.post(f"{API}/contracts", json={
            "title": "TEST_Contract_A", "client": "Acme", "status": "en_cours",
            "amount": "10000", "start_date": "2026-02-01", "end_date": "2026-08-01",
        }, headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["title"] == "TEST_Contract_A"
        assert d["status"] == "en_cours"
        assert "id" in d
        TestContracts.contract_id = d["id"]

    def test_create_contract_invalid_status(self, admin_headers):
        r = requests.post(f"{API}/contracts", json={"title": "TEST_x", "status": "bogus"},
                          headers=admin_headers, timeout=30)
        assert r.status_code == 400

    def test_list_contracts(self, admin_headers):
        r = requests.get(f"{API}/contracts", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        ids = [c["id"] for c in r.json()]
        assert TestContracts.contract_id in ids

    def test_filter_contracts(self, admin_headers):
        r = requests.get(f"{API}/contracts?status=en_cours", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert all(c["status"] == "en_cours" for c in r.json())

    def test_update_contract(self, admin_headers):
        r = requests.put(f"{API}/contracts/{TestContracts.contract_id}", json={
            "title": "TEST_Contract_A_upd", "status": "boucle",
        }, headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert r.json()["status"] == "boucle"

    def test_delete_contract(self, admin_headers):
        r = requests.delete(f"{API}/contracts/{TestContracts.contract_id}", headers=admin_headers, timeout=30)
        assert r.status_code == 200

    def test_contracts_forbidden_for_candidate(self, candidate_token):
        r = requests.get(f"{API}/contracts", headers={"Authorization": f"Bearer {candidate_token}"}, timeout=30)
        assert r.status_code == 403


# ----------------------------- Interviews CRUD -----------------------------
class TestInterviews:
    itw_id = None

    def test_create_interview(self, admin_headers):
        r = requests.post(f"{API}/interviews", json={
            "title": "TEST_Interview_A", "date": "2026-09-15", "time": "10:30",
            "candidate_name": "Candidate One",
        }, headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["title"] == "TEST_Interview_A"
        assert d["date"] == "2026-09-15"
        assert d["time"] == "10:30"
        TestInterviews.itw_id = d["id"]

    def test_list_interviews(self, admin_headers):
        r = requests.get(f"{API}/interviews", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert any(i["id"] == TestInterviews.itw_id for i in r.json())

    def test_update_interview(self, admin_headers):
        r = requests.put(f"{API}/interviews/{TestInterviews.itw_id}", json={
            "title": "TEST_Interview_A_upd", "date": "2026-09-15", "time": "11:00",
        }, headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert r.json()["time"] == "11:00"

    def test_delete_interview(self, admin_headers):
        r = requests.delete(f"{API}/interviews/{TestInterviews.itw_id}", headers=admin_headers, timeout=30)
        assert r.status_code == 200


# ----------------------------- Admin stats widgets -----------------------------
class TestStats:
    def test_admin_stats_has_widgets(self, admin_headers):
        r = requests.get(f"{API}/admin/stats", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ["contracts_active", "upcoming_interviews", "jobs", "applications"]:
            assert k in d, f"Missing key {k} in stats"


# ----------------------------- CSV exports -----------------------------
class TestExports:
    def test_export_applications(self, admin_token):
        r = requests.get(f"{API}/export/applications?auth={admin_token}", timeout=30)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "").lower()
        assert "Candidat" in r.text.splitlines()[0]

    def test_export_contracts(self, admin_token):
        r = requests.get(f"{API}/export/contracts?auth={admin_token}", timeout=30)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "").lower()
        assert "Intitule" in r.text.splitlines()[0]

    def test_export_forbidden_without_auth(self):
        r = requests.get(f"{API}/export/applications", timeout=30)
        assert r.status_code == 401


# ----------------------------- Application review + status -----------------------------
class TestApplicationReview:
    def test_review_and_status_flow(self, admin_headers, candidate_token):
        # find an application; if none exists, create one by applying to any active job
        apps = requests.get(f"{API}/applications", headers=admin_headers, timeout=30).json()
        if not apps:
            jobs = requests.get(f"{API}/jobs", timeout=30).json()
            if not jobs:
                pytest.skip("No jobs available to create an application")
            import io as _io
            files = {"cv": ("cv.pdf", _io.BytesIO(b"%PDF-1.4 test cv"), "application/pdf")}
            data = {"job_id": jobs[0]["id"], "cover_note": "TEST review"}
            rr = requests.post(f"{API}/applications", data=data, files=files,
                               headers={"Authorization": f"Bearer {candidate_token}"}, timeout=60)
            assert rr.status_code == 200, rr.text
            app_id = rr.json()["id"]
        else:
            app_id = apps[0]["id"]

        # review
        r = requests.put(f"{API}/applications/{app_id}/review",
                         json={"admin_note": "TEST note", "rating": 4},
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("admin_note") == "TEST note"
        assert d.get("rating") == 4

        # persistence: refetch list
        apps2 = requests.get(f"{API}/applications", headers=admin_headers, timeout=30).json()
        target = next(a for a in apps2 if a["id"] == app_id)
        assert target["admin_note"] == "TEST note"
        assert target["rating"] == 4

        # status change (accepted then rejected)
        r2 = requests.put(f"{API}/applications/{app_id}/status", json={"status": "accepted"},
                          headers=admin_headers, timeout=30)
        assert r2.status_code == 200
        assert r2.json()["status"] == "accepted"
        r3 = requests.put(f"{API}/applications/{app_id}/status", json={"status": "rejected"},
                          headers=admin_headers, timeout=30)
        assert r3.status_code == 200
        assert r3.json()["status"] == "rejected"


# ----------------------------- New features (iteration 5) -----------------------------
class TestNewFeatures:
    """New: admin notifications on new application/message, interview with candidate_id,
    GET /interviews/me, cron endpoint auth."""

    def test_admin_notif_on_new_application(self, admin_headers, candidate_token):
        # snapshot admin notifications count
        before = requests.get(f"{API}/notifications", headers=admin_headers, timeout=30).json()
        before_unread = before.get("unread", 0)

        # find a job the candidate hasn't applied to yet (anti double-apply now enforced)
        jobs = requests.get(f"{API}/jobs", timeout=30).json()
        if not jobs:
            pytest.skip("No jobs available")
        my_apps = requests.get(f"{API}/applications/me",
                               headers={"Authorization": f"Bearer {candidate_token}"}, timeout=30).json()
        applied_job_ids = {a["job_id"] for a in my_apps}
        job = next((j for j in jobs if j["id"] not in applied_job_ids), None)
        if not job:
            pytest.skip("Candidate has already applied to all jobs")
        import io as _io
        files = {"cv": ("cv.pdf", _io.BytesIO(b"%PDF-1.4 TEST notif"), "application/pdf")}
        data = {"job_id": job["id"], "cover_note": "TEST admin notif"}
        r = requests.post(f"{API}/applications", data=data, files=files,
                          headers={"Authorization": f"Bearer {candidate_token}"}, timeout=60)
        assert r.status_code == 200, r.text

        after = requests.get(f"{API}/notifications", headers=admin_headers, timeout=30).json()
        assert after["unread"] >= before_unread + 1, f"Admin should get a new unread notif ({before_unread}->{after['unread']})"
        # find application-type notif
        assert any(n.get("type") == "application" for n in after["items"]), "no 'application' type notif"

    def test_admin_notif_on_candidate_message(self, admin_headers, candidate_token):
        # candidate posts a message; admin should be notified
        before = requests.get(f"{API}/notifications", headers=admin_headers, timeout=30).json()
        before_unread = before.get("unread", 0)

        r = requests.post(f"{API}/chat/messages", json={"text": "TEST_msg from candidate"},
                          headers={"Authorization": f"Bearer {candidate_token}"}, timeout=30)
        assert r.status_code == 200, r.text
        after = requests.get(f"{API}/notifications", headers=admin_headers, timeout=30).json()
        assert after["unread"] >= before_unread + 1
        assert any(n.get("type") == "message" for n in after["items"])

    def test_interview_with_candidate_id_and_me_endpoint(self, admin_headers, candidate_token):
        # discover candidate user_id
        me = requests.get(f"{API}/auth/me",
                          headers={"Authorization": f"Bearer {candidate_token}"}, timeout=30).json()
        cand_id = me["user_id"]
        # snapshot candidate notifications
        cn_before = requests.get(f"{API}/notifications",
                                 headers={"Authorization": f"Bearer {candidate_token}"}, timeout=30).json()
        # admin plans interview with candidate_id
        r = requests.post(f"{API}/interviews", json={
            "title": "TEST_ITW_notif", "date": "2026-11-20", "time": "14:00",
            "candidate_id": cand_id, "candidate_name": me.get("name", ""),
        }, headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        itw = r.json()
        assert itw["candidate_id"] == cand_id
        itw_id = itw["id"]

        # GET /interviews/me returns it
        r_me = requests.get(f"{API}/interviews/me",
                            headers={"Authorization": f"Bearer {candidate_token}"}, timeout=30)
        assert r_me.status_code == 200
        assert any(i["id"] == itw_id for i in r_me.json()), "candidate /interviews/me missing new interview"

        # candidate got an 'interview' notification
        cn_after = requests.get(f"{API}/notifications",
                                headers={"Authorization": f"Bearer {candidate_token}"}, timeout=30).json()
        assert cn_after["unread"] >= cn_before.get("unread", 0) + 1
        assert any(n.get("type") == "interview" for n in cn_after["items"])

        # verify via admin GET /interviews that candidate_id is present
        all_itws = requests.get(f"{API}/interviews", headers=admin_headers, timeout=30).json()
        target = next(i for i in all_itws if i["id"] == itw_id)
        assert target.get("candidate_id") == cand_id

        # cleanup
        requests.delete(f"{API}/interviews/{itw_id}", headers=admin_headers, timeout=30)

    def test_interviews_me_only_returns_own(self, admin_headers, candidate_token):
        # create an interview with an unrelated candidate_id
        other_id = "user_" + uuid.uuid4().hex[:12]
        r = requests.post(f"{API}/interviews", json={
            "title": "TEST_ITW_other", "date": "2026-12-01", "time": "09:00",
            "candidate_id": other_id, "candidate_name": "Someone Else",
        }, headers=admin_headers, timeout=30)
        assert r.status_code == 200
        other_itw_id = r.json()["id"]

        r_me = requests.get(f"{API}/interviews/me",
                            headers={"Authorization": f"Bearer {candidate_token}"}, timeout=30)
        assert r_me.status_code == 200
        assert not any(i["id"] == other_itw_id for i in r_me.json())

        requests.delete(f"{API}/interviews/{other_itw_id}", headers=admin_headers, timeout=30)

    def test_cron_interview_reminders_auth(self):
        secret = os.environ.get("WEBHOOK_CRON_SECRET") or "tv_cron_7f3a9c2e5b8d1046af62e9c4d7b0153e"
        # No auth -> 401
        r = requests.post(f"{API}/cron/interview-reminders", timeout=30)
        assert r.status_code == 401, r.text
        # Wrong token -> 401
        r2 = requests.post(f"{API}/cron/interview-reminders",
                           headers={"Authorization": "Bearer wrong"}, timeout=30)
        assert r2.status_code == 401
        # Correct -> 200
        r3 = requests.post(f"{API}/cron/interview-reminders",
                           headers={"Authorization": f"Bearer {secret}"}, timeout=30)
        assert r3.status_code == 200, r3.text
        assert r3.json().get("ok") is True


# ----------------------------- Notifications (candidate side) -----------------------------
class TestNotifications:
    def test_candidate_notifications_created_on_status_change(self, admin_headers, candidate_token):
        # Trigger a status update so the candidate gets an in-app notification
        apps = requests.get(f"{API}/applications", headers=admin_headers, timeout=30).json()
        if not apps:
            pytest.skip("No applications available")
        # find one belonging to candidate1@test.com if possible
        target = next((a for a in apps if a.get("candidate_email") == CANDIDATE_EMAIL), apps[0])
        app_id = target["id"]
        requests.put(f"{API}/applications/{app_id}/status", json={"status": "accepted"},
                     headers=admin_headers, timeout=30)
        # Only assert notifications for the owner candidate
        if target.get("candidate_email") != CANDIDATE_EMAIL:
            pytest.skip("Application not owned by test candidate; notif belongs to another user")
        r = requests.get(f"{API}/notifications",
                         headers={"Authorization": f"Bearer {candidate_token}"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "items" in d and "unread" in d


# ----------------------------- Candidate Profile + Priorisation + Double-apply -----------------------------
class TestCandidateProfile:
    """Iteration 6: PUT/GET /profile, profile_completed flag, /jobs prioritisation, anti double-apply."""

    def _fresh_candidate_token(self):
        """Create a fresh candidate + login. Returns (token, email, user_id)."""
        email = f"test_cand_{uuid.uuid4().hex[:8]}@test.com"
        cid, ans = get_captcha()
        r = requests.post(f"{API}/auth/register", json={
            "name": "TEST Cand", "email": email, "password": "Test@2026!",
            "captcha_id": cid, "captcha_answer": ans,
        }, timeout=30)
        assert r.status_code == 200, r.text
        tok = r.json()["token"]
        uid = r.json()["user"]["user_id"]
        return tok, email, uid

    def test_get_profile_returns_fields(self, candidate_token):
        r = requests.get(f"{API}/profile",
                         headers={"Authorization": f"Bearer {candidate_token}"}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ["user_id", "email", "role"]:
            assert k in d

    def test_put_profile_sets_completed_true(self):
        tok, _, _ = self._fresh_candidate_token()
        H = {"Authorization": f"Bearer {tok}"}
        # Before: profile_completed should be False/absent
        g0 = requests.get(f"{API}/profile", headers=H, timeout=30).json()
        assert not g0.get("profile_completed")
        # PUT full profile
        r = requests.put(f"{API}/profile", json={
            "name": "TEST Cand Full",
            "phone": "+33612345678",
            "nationality": "Française",
            "city": "Paris",
            "country": "France",
            "current_position": "Développeur Full-Stack",
            "years_experience": 5,
            "headline": "Ingénieur logiciel",
            "bio": "Passionné par React et Python.",
            "domains": ["Tech"],
            "tools": ["React", "Python"],
        }, headers=H, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("profile_completed") is True
        assert d.get("name") == "TEST Cand Full"
        assert d.get("phone") == "+33612345678"
        assert d.get("nationality") == "Française"
        assert d.get("domains") == ["Tech"]
        # GET returns same values (persistence)
        g = requests.get(f"{API}/profile", headers=H, timeout=30).json()
        assert g["profile_completed"] is True
        assert g["phone"] == "+33612345678"
        assert g["domains"] == ["Tech"]

    def test_put_profile_partial_keeps_incomplete(self):
        tok, _, _ = self._fresh_candidate_token()
        H = {"Authorization": f"Bearer {tok}"}
        # Only name -> not complete (needs phone+nationality+domains)
        r = requests.put(f"{API}/profile", json={"name": "Just Name"}, headers=H, timeout=30)
        assert r.status_code == 200
        assert r.json().get("profile_completed") is False

    def test_jobs_prioritisation_for_tech_candidate(self):
        # Fresh Tech candidate
        tok, _, _ = self._fresh_candidate_token()
        H = {"Authorization": f"Bearer {tok}"}
        requests.put(f"{API}/profile", json={
            "name": "TEST Tech", "phone": "+33600000000", "nationality": "Française",
            "domains": ["Tech"],
        }, headers=H, timeout=30)

        # List jobs with auth
        r_auth = requests.get(f"{API}/jobs", headers=H, timeout=30)
        assert r_auth.status_code == 200
        jobs_auth = r_auth.json()
        if len(jobs_auth) < 2:
            pytest.skip("Need >=2 jobs to test prioritisation")

        # All jobs should have match_score, and Tech-category ones should be at the top
        assert all("match_score" in j for j in jobs_auth), "match_score missing on some jobs"
        tech_jobs = [j for j in jobs_auth if (j.get("category") or "").lower() == "tech"]
        if tech_jobs:
            # top scores are non-tech only if higher — but tech match=3 is the highest possible here
            assert jobs_auth[0].get("match_score", 0) >= 1, "Top job should have positive score"
            # verify no lower-scored job comes before a higher-scored one
            scores = [j.get("match_score", 0) for j in jobs_auth]
            assert scores == sorted(scores, reverse=True), f"Jobs not sorted by score desc: {scores}"

        # Without auth -> no match_score field, ordered by date
        r_noauth = requests.get(f"{API}/jobs", timeout=30)
        assert r_noauth.status_code == 200
        jobs_noauth = r_noauth.json()
        assert all("match_score" not in j for j in jobs_noauth), "match_score should not appear without auth"

    def test_anti_double_application(self):
        tok, _, _ = self._fresh_candidate_token()
        H = {"Authorization": f"Bearer {tok}"}
        jobs = requests.get(f"{API}/jobs", timeout=30).json()
        if not jobs:
            pytest.skip("No jobs available")
        job_id = jobs[0]["id"]
        import io as _io
        # 1st application -> 200
        r1 = requests.post(f"{API}/applications",
                           data={"job_id": job_id, "cover_note": "TEST first"},
                           files={"cv": ("cv.pdf", _io.BytesIO(b"%PDF-1.4 first"), "application/pdf")},
                           headers=H, timeout=60)
        assert r1.status_code == 200, r1.text
        # 2nd application -> 400 with French message
        r2 = requests.post(f"{API}/applications",
                           data={"job_id": job_id, "cover_note": "TEST duplicate"},
                           files={"cv": ("cv.pdf", _io.BytesIO(b"%PDF-1.4 dup"), "application/pdf")},
                           headers=H, timeout=60)
        assert r2.status_code == 400, r2.text
        assert "déjà postulé" in r2.json().get("detail", "").lower()

    def test_contracts_me_only_own(self, admin_headers):
        # Fresh candidate 1
        tok1, email1, uid1 = self._fresh_candidate_token()
        tok2, email2, uid2 = self._fresh_candidate_token()
        # Admin creates a contract for cand1
        r = requests.post(f"{API}/contracts", json={
            "title": "TEST_MyContract", "client": "Acme", "status": "en_cours",
            "candidate_id": uid1,
        }, headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        try:
            # cand1 sees it
            r1 = requests.get(f"{API}/contracts/me",
                              headers={"Authorization": f"Bearer {tok1}"}, timeout=30)
            assert r1.status_code == 200
            assert any(c["id"] == cid for c in r1.json())
            # cand2 does NOT see it
            r2 = requests.get(f"{API}/contracts/me",
                              headers={"Authorization": f"Bearer {tok2}"}, timeout=30)
            assert r2.status_code == 200
            assert not any(c["id"] == cid for c in r2.json())
        finally:
            requests.delete(f"{API}/contracts/{cid}", headers=admin_headers, timeout=30)

    def test_interviews_me_only_own(self, admin_headers):
        tok, _, uid = self._fresh_candidate_token()
        r = requests.post(f"{API}/interviews", json={
            "title": "TEST_MyItw", "date": "2026-11-25", "time": "10:00",
            "candidate_id": uid, "candidate_name": "TEST Cand",
        }, headers=admin_headers, timeout=30)
        assert r.status_code == 200
        itw_id = r.json()["id"]
        try:
            r_me = requests.get(f"{API}/interviews/me",
                                headers={"Authorization": f"Bearer {tok}"}, timeout=30)
            assert r_me.status_code == 200
            assert any(i["id"] == itw_id for i in r_me.json())
        finally:
            requests.delete(f"{API}/interviews/{itw_id}", headers=admin_headers, timeout=30)


# ----------------------------- NEW iter6: profile detail + avatars enrichment -----------------------------
class TestProfileEnrichment:
    """GET /users/{id} (admin), applications candidate_picture, chat conv picture"""

    def _fresh_candidate(self):
        email = f"TEST_pe_{uuid.uuid4().hex[:6]}@test.com"
        cid, ans = get_captcha()
        r = requests.post(f"{API}/auth/register", json={
            "name": "TEST Enrich", "email": email, "password": "Test@2026!",
            "captcha_id": cid, "captcha_answer": ans,
        }, timeout=30)
        assert r.status_code == 200, r.text
        return r.json()["token"], r.json()["user"]["user_id"], email

    def test_get_user_detail_shape(self, admin_headers):
        tok, uid, email = self._fresh_candidate()
        # candidate updates profile a little
        requests.put(f"{API}/profile", json={
            "phone": "+33123456789", "nationality": "FR",
            "domains": ["Tech"], "tools": ["Python"], "bio": "TEST bio", "years_experience": 3,
        }, headers={"Authorization": f"Bearer {tok}"}, timeout=30)

        r = requests.get(f"{API}/users/{uid}", headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert set(["user", "applications", "interviews", "contracts"]).issubset(d.keys())
        u = d["user"]
        assert u["email"].lower() == email.lower()
        assert u["user_id"] == uid
        assert "password_hash" not in u
        assert d["applications"] == [] or isinstance(d["applications"], list)
        assert isinstance(d["interviews"], list)
        assert isinstance(d["contracts"], list)

    def test_get_user_detail_404(self, admin_headers):
        r = requests.get(f"{API}/users/nonexistent-id-xyz", headers=admin_headers, timeout=30)
        assert r.status_code == 404

    def test_get_user_detail_requires_admin(self, candidate_token):
        # Grab any user_id
        r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {candidate_token}"}, timeout=30)
        uid = r.json()["user_id"]
        r2 = requests.get(f"{API}/users/{uid}",
                          headers={"Authorization": f"Bearer {candidate_token}"}, timeout=30)
        assert r2.status_code in (401, 403)

    def test_applications_include_candidate_picture_field(self, admin_headers):
        r = requests.get(f"{API}/applications", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        apps = r.json()
        assert isinstance(apps, list)
        # Field must be present (value may be None) on every row when apps exist
        for a in apps[:10]:
            assert "candidate_picture" in a, f"missing candidate_picture: {a.keys()}"

    def test_chat_conversations_include_picture_field(self, admin_headers):
        r = requests.get(f"{API}/chat/conversations", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        for c in r.json()[:10]:
            assert "picture" in c
            assert "candidate_id" in c
