"""Iteration 32: security hardening + inline application edit endpoints.

Covers:
- PUT /api/applications/{id}/status, /review, /interview-note (admin only)
- Public/private file download headers (nosniff, inline for safe types, attachment for others)
- File access control (401/403/200)
- Admin authorization matrix (401/403)
- RGPD purge DELETE /api/account works
"""
import io
import os
import re
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://candidai.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "seffabdallah7@gmail.com"
ADMIN_PWD = "Admin@2026!"


def _solve_captcha():
    r = requests.get(f"{API}/auth/captcha", timeout=15)
    r.raise_for_status()
    j = r.json()
    q = j["question"] if "question" in j else j.get("challenge") or j.get("prompt")
    # q like "3 + 4"
    m = re.search(r"(\d+)\s*([+\-*])\s*(\d+)", q)
    a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
    ans = {"+": a + b, "-": a - b, "*": a * b}[op]
    return j.get("captcha_id") or j.get("id"), str(ans)


@pytest.fixture(scope="module")
def admin_token():
    cid, ans = _solve_captcha()
    r = requests.post(f"{API}/auth/login", json={
        "email": ADMIN_EMAIL, "password": ADMIN_PWD,
        "captcha_id": cid, "captcha_answer": ans,
    }, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def candidate_creds():
    # Register a fresh candidate to guarantee predictable ownership matrix
    cid, ans = _solve_captcha()
    email = f"TEST_iter32_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "CandTest@2026!"
    r = requests.post(f"{API}/auth/register", json={
        "name": "Iter32 Candidate", "email": email, "password": pwd,
        "captcha_id": cid, "captcha_answer": ans,
    }, timeout=15)
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    return {"email": email, "password": pwd, "token": r.json()["token"], "user_id": r.json()["user"]["user_id"]}


@pytest.fixture(scope="module")
def candidate_headers(candidate_creds):
    return {"Authorization": f"Bearer {candidate_creds['token']}"}


@pytest.fixture(scope="module")
def second_candidate():
    cid, ans = _solve_captcha()
    email = f"TEST_iter32b_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "CandTest@2026!"
    r = requests.post(f"{API}/auth/register", json={
        "name": "Iter32 Other", "email": email, "password": pwd,
        "captcha_id": cid, "captcha_answer": ans,
    }, timeout=15)
    assert r.status_code == 200
    return {"token": r.json()["token"], "user_id": r.json()["user"]["user_id"]}


# ---------------------------------------------------------------------------
# 1. Admin authorization matrix
# ---------------------------------------------------------------------------

def test_users_list_requires_admin(candidate_headers):
    r1 = requests.get(f"{API}/users", timeout=15)
    assert r1.status_code == 401
    r2 = requests.get(f"{API}/users", headers=candidate_headers, timeout=15)
    assert r2.status_code == 403


def test_users_get_requires_admin(candidate_headers, candidate_creds):
    uid = candidate_creds["user_id"]
    assert requests.get(f"{API}/users/{uid}", timeout=15).status_code == 401
    assert requests.get(f"{API}/users/{uid}", headers=candidate_headers, timeout=15).status_code == 403


def test_delete_user_requires_admin(candidate_headers, candidate_creds):
    uid = candidate_creds["user_id"]
    assert requests.delete(f"{API}/users/{uid}", timeout=15).status_code == 401
    assert requests.delete(f"{API}/users/{uid}", headers=candidate_headers, timeout=15).status_code == 403


def test_put_status_requires_admin(candidate_headers):
    fake = "does-not-exist"
    r1 = requests.put(f"{API}/applications/{fake}/status", json={"status": "pending"}, timeout=15)
    assert r1.status_code == 401
    r2 = requests.put(f"{API}/applications/{fake}/status", json={"status": "pending"}, headers=candidate_headers, timeout=15)
    assert r2.status_code == 403


def test_put_review_requires_admin(candidate_headers):
    fake = "does-not-exist"
    assert requests.put(f"{API}/applications/{fake}/review", json={"admin_note": "x"}, timeout=15).status_code == 401
    assert requests.put(f"{API}/applications/{fake}/review", json={"admin_note": "x"}, headers=candidate_headers, timeout=15).status_code == 403


# ---------------------------------------------------------------------------
# 2. Inline application edit flow (status / review / interview-note)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def created_application(admin_headers, candidate_creds):
    # Pick a job
    jobs = requests.get(f"{API}/jobs/all", headers=admin_headers, timeout=15).json()
    assert isinstance(jobs, list) and len(jobs) > 0
    job_id = jobs[0]["id"]
    r = requests.post(f"{API}/applications/admin-create", headers=admin_headers, json={
        "candidate_id": candidate_creds["user_id"], "job_id": job_id, "status": "pending",
    }, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def test_put_status_valid_transitions(admin_headers, created_application):
    app_id = created_application["id"]
    for s in ["accepted", "rejected", "pending", "interview_scheduled", "interview_done"]:
        r = requests.put(f"{API}/applications/{app_id}/status",
                         headers=admin_headers, json={"status": s}, timeout=15)
        assert r.status_code == 200, f"{s}: {r.status_code} {r.text}"
        assert r.json()["status"] == s


def test_put_status_invalid(admin_headers, created_application):
    r = requests.put(f"{API}/applications/{created_application['id']}/status",
                     headers=admin_headers, json={"status": "bogus"}, timeout=15)
    assert r.status_code == 400


def test_put_review_persists(admin_headers, created_application):
    app_id = created_application["id"]
    r = requests.put(f"{API}/applications/{app_id}/review", headers=admin_headers,
                     json={"admin_note": "great candidate", "rating": 4}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["admin_note"] == "great candidate"
    assert body["rating"] == 4


def test_put_interview_note_requires_done_status(admin_headers, created_application):
    app_id = created_application["id"]
    # force pending
    requests.put(f"{API}/applications/{app_id}/status", headers=admin_headers, json={"status": "pending"}, timeout=15)
    r = requests.put(f"{API}/applications/{app_id}/interview-note",
                     headers=admin_headers, json={"note": "should fail"}, timeout=15)
    assert r.status_code == 400
    # now move to interview_done
    requests.put(f"{API}/applications/{app_id}/status", headers=admin_headers, json={"status": "interview_done"}, timeout=15)
    r2 = requests.put(f"{API}/applications/{app_id}/interview-note",
                      headers=admin_headers, json={"note": "went well"}, timeout=15)
    assert r2.status_code == 200
    assert r2.json().get("interview_note") == "went well"


# ---------------------------------------------------------------------------
# 3. File download hardening
# ---------------------------------------------------------------------------

def _upload_profile_photo(headers):
    # tiny valid PNG (1x1)
    png = bytes.fromhex(
        "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
        "0000000A49444154789C6300010000000500010D0A2DB40000000049454E44AE426082"
    )
    files = {"photo": ("pixel.png", png, "image/png")}
    r = requests.post(f"{API}/profile/photo", headers=headers, files=files, timeout=20)
    return r


def test_public_photo_inline_and_nosniff(candidate_headers, candidate_creds):
    r = _upload_profile_photo(candidate_headers)
    if r.status_code != 200:
        pytest.skip(f"upload-photo not available: {r.status_code} {r.text[:200]}")
    # Grab picture URL from /auth/me
    me = requests.get(f"{API}/auth/me", headers=candidate_headers, timeout=15).json()
    pic = me.get("picture") or ""
    m = re.search(r"/files/public/([^/?#]+)", pic)
    assert m, f"no public file id in picture url: {pic}"
    file_id = m.group(1)
    resp = requests.get(f"{API}/files/public/{file_id}", timeout=15)
    assert resp.status_code == 200
    assert resp.headers.get("x-content-type-options", "").lower() == "nosniff"
    assert resp.headers.get("content-type", "").startswith("image/")
    disp = resp.headers.get("content-disposition", "").lower()
    assert "inline" in disp


def _upload_cv(headers):
    # minimal-ish PDF
    pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
    files = {"cv": ("cv.pdf", pdf, "application/pdf")}
    r = requests.post(f"{API}/profile/cv", headers=headers, files=files, timeout=20)
    return r


def test_private_cv_headers_and_acl(candidate_headers, candidate_creds, admin_headers, second_candidate):
    r = _upload_cv(candidate_headers)
    if r.status_code != 200:
        pytest.skip(f"upload-cv not available: {r.status_code} {r.text[:200]}")
    me = requests.get(f"{API}/auth/me", headers=candidate_headers, timeout=15).json()
    file_id = me.get("cv_file_id")
    assert file_id, "cv_file_id should be set after upload"

    # 401 no token
    r0 = requests.get(f"{API}/files/{file_id}", timeout=15)
    assert r0.status_code == 401

    # 403 for a different non-admin
    r1 = requests.get(f"{API}/files/{file_id}",
                      headers={"Authorization": f"Bearer {second_candidate['token']}"}, timeout=15)
    assert r1.status_code == 403

    # 200 owner
    r2 = requests.get(f"{API}/files/{file_id}", headers=candidate_headers, timeout=15)
    assert r2.status_code == 200
    assert r2.headers.get("x-content-type-options", "").lower() == "nosniff"
    assert r2.headers.get("content-type", "").startswith("application/pdf")
    assert "inline" in r2.headers.get("content-disposition", "").lower()

    # 200 admin
    r3 = requests.get(f"{API}/files/{file_id}", headers=admin_headers, timeout=15)
    assert r3.status_code == 200


# ---------------------------------------------------------------------------
# 4. RGPD purge — DELETE /api/account
# ---------------------------------------------------------------------------

def test_delete_my_account_purges(admin_headers):
    # Register a fresh candidate to nuke
    cid, ans = _solve_captcha()
    email = f"TEST_iter32_purge_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "CandTest@2026!"
    r = requests.post(f"{API}/auth/register", json={
        "name": "Purge Me", "email": email, "password": pwd,
        "captcha_id": cid, "captcha_answer": ans,
    }, timeout=15)
    assert r.status_code == 200
    tok = r.json()["token"]
    uid = r.json()["user"]["user_id"]

    d = requests.delete(f"{API}/account", headers={"Authorization": f"Bearer {tok}"}, timeout=20)
    assert d.status_code in (200, 204), f"delete_my_account failed: {d.status_code} {d.text}"

    # Verify user is gone (admin GET /users/{id} -> 404)
    g = requests.get(f"{API}/users/{uid}", headers=admin_headers, timeout=15)
    assert g.status_code == 404


# ---------------------------------------------------------------------------
# 5. CV upload type allowlist (anti-stored-XSS via wrong file)
# ---------------------------------------------------------------------------

def test_cv_upload_rejects_non_pdf(candidate_headers):
    files = {"cv": ("nasty.txt", b"hello world", "text/plain")}
    r = requests.post(f"{API}/profile/cv", headers=candidate_headers, files=files, timeout=15)
    assert r.status_code == 400, r.text
    assert "Format" in r.text or "non autoris" in r.text.lower()


def test_cv_upload_rejects_html(candidate_headers):
    files = {"cv": ("evil.html", b"<script>alert(1)</script>", "text/html")}
    r = requests.post(f"{API}/profile/cv", headers=candidate_headers, files=files, timeout=15)
    assert r.status_code == 400


def test_cv_upload_accepts_pdf(candidate_headers):
    pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
    files = {"cv": ("ok.pdf", pdf, "application/pdf")}
    r = requests.post(f"{API}/profile/cv", headers=candidate_headers, files=files, timeout=20)
    assert r.status_code == 200, r.text
    assert r.json().get("cv_file_id")


# ---------------------------------------------------------------------------
# 6. Admin DELETE /users/{id} purges related data (RGPD)
# ---------------------------------------------------------------------------

def test_admin_delete_user_purges_applications(admin_headers):
    # Register throwaway candidate
    cid, ans = _solve_captcha()
    email = f"TEST_iter32_purge_admin_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={
        "name": "Purge By Admin", "email": email, "password": "CandTest@2026!",
        "captcha_id": cid, "captcha_answer": ans,
    }, timeout=15)
    assert r.status_code == 200
    uid = r.json()["user"]["user_id"]

    # Create an application for them
    jobs = requests.get(f"{API}/jobs/all", headers=admin_headers, timeout=15).json()
    job_id = jobs[0]["id"]
    ca = requests.post(f"{API}/applications/admin-create", headers=admin_headers,
                       json={"candidate_id": uid, "job_id": job_id, "status": "pending"}, timeout=15)
    assert ca.status_code == 200
    app_id = ca.json()["id"]

    # Delete user via admin
    d = requests.delete(f"{API}/users/{uid}", headers=admin_headers, timeout=20)
    assert d.status_code == 200, d.text

    # User gone
    g = requests.get(f"{API}/users/{uid}", headers=admin_headers, timeout=15)
    assert g.status_code == 404

    # Application no longer visible in list
    apps = requests.get(f"{API}/applications", headers=admin_headers, timeout=15).json()
    assert not any(a.get("id") == app_id for a in apps), "application should be purged with the user"
    assert not any(a.get("candidate_id") == uid for a in apps), "no leftover apps for purged user"


def test_admin_cannot_delete_super_admin(admin_headers):
    # Admin should not be able to delete themselves
    me = requests.get(f"{API}/auth/me", headers=admin_headers, timeout=15).json()
    r = requests.delete(f"{API}/users/{me['user_id']}", headers=admin_headers, timeout=15)
    assert r.status_code in (400, 404)
