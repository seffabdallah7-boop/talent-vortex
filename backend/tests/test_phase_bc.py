"""Phase B (admin appreciation) & Phase C (schedule interview on accept) tests.

Reuses helpers from backend_test.py.
"""
import io as _io
import time
import uuid

import pytest
import requests

from backend_test import (
    API,
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    CANDIDATE_EMAIL,
    CANDIDATE_PASSWORD,
    full_login,
    get_captcha,
)


# ---- fixtures reused via module scope (own to avoid session collision) ----
@pytest.fixture(scope="module")
def admin_headers():
    tok = full_login(ADMIN_EMAIL, ADMIN_PASSWORD)
    return {"Authorization": f"Bearer {tok}"}


def _new_candidate():
    email = f"test_bc_{uuid.uuid4().hex[:8]}@test.com"
    cid, ans = get_captcha()
    r = requests.post(f"{API}/auth/register", json={
        "name": "TEST BC Cand", "email": email, "password": "Test@2026!",
        "captcha_id": cid, "captcha_answer": ans,
    }, timeout=30)
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    uid = r.json()["user"]["user_id"]
    return tok, uid, email


# ============================ Phase B: appreciation ============================
class TestPhaseB_Appreciation:
    def test_users_list_returns_rating_fields(self, admin_headers):
        r = requests.get(f"{API}/users", headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        users = r.json()
        assert isinstance(users, list) and len(users) > 0
        for u in users[:20]:
            assert "rating" in u, f"rating missing: {u.keys()}"
            assert "rating_count" in u

    def test_min_rating_filter(self, admin_headers):
        # Get baseline
        r_all = requests.get(f"{API}/users", headers=admin_headers, timeout=30).json()
        r4 = requests.get(f"{API}/users?min_rating=4", headers=admin_headers, timeout=30)
        assert r4.status_code == 200
        filtered = r4.json()
        assert isinstance(filtered, list)
        # every user returned must have rating >= 4
        for u in filtered:
            assert (u.get("rating") or 0) >= 4, f"user {u.get('email')} rating={u.get('rating')} leaked past min_rating=4"
        # count filtered <= all
        assert len(filtered) <= len(r_all)

    def test_min_rating_5_subset_of_4(self, admin_headers):
        r5 = requests.get(f"{API}/users?min_rating=5", headers=admin_headers, timeout=30).json()
        r4 = requests.get(f"{API}/users?min_rating=4", headers=admin_headers, timeout=30).json()
        ids5 = {u["user_id"] for u in r5}
        ids4 = {u["user_id"] for u in r4}
        assert ids5.issubset(ids4)

    def test_candidates_list_also_returns_rating(self, admin_headers):
        r = requests.get(f"{API}/candidates", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        for c in r.json()[:10]:
            assert "rating" in c and "rating_count" in c

    def test_rating_average_matches_review(self, admin_headers):
        """Create fresh candidate → apply → admin rates 4 & 5 → user rating should be 4.5."""
        # need at least 2 different jobs
        jobs = requests.get(f"{API}/jobs", timeout=30).json()
        if len(jobs) < 2:
            pytest.skip("Need >=2 jobs")
        tok, uid, email = _new_candidate()
        H = {"Authorization": f"Bearer {tok}"}
        app_ids = []
        for j, rating in zip(jobs[:2], [4, 5]):
            files = {"cv": ("cv.pdf", _io.BytesIO(b"%PDF-1.4"), "application/pdf")}
            data = {"job_id": j["id"], "cover_note": "TEST"}
            r = requests.post(f"{API}/applications", data=data, files=files, headers=H, timeout=60)
            assert r.status_code == 200, r.text
            aid = r.json()["id"]
            app_ids.append(aid)
            rr = requests.put(f"{API}/applications/{aid}/review",
                              json={"admin_note": "t", "rating": rating}, headers=admin_headers, timeout=30)
            assert rr.status_code == 200
        # now check the user rating
        r = requests.get(f"{API}/users?q={email}", headers=admin_headers, timeout=30).json()
        target = next((u for u in r if u["user_id"] == uid), None)
        assert target is not None, "candidate not in users listing"
        assert target["rating"] == 4.5, f"expected 4.5 got {target['rating']}"
        assert target["rating_count"] == 2


# ============================ Phase C: schedule on accept ============================
class TestPhaseC_ScheduleOnAccept:
    def test_end_to_end_accept_schedule_notify(self, admin_headers):
        # 1) create candidate + application
        tok, uid, email = _new_candidate()
        H = {"Authorization": f"Bearer {tok}"}
        jobs = requests.get(f"{API}/jobs", timeout=30).json()
        if not jobs:
            pytest.skip("No jobs")
        job = jobs[0]
        files = {"cv": ("cv.pdf", _io.BytesIO(b"%PDF-1.4"), "application/pdf")}
        r = requests.post(f"{API}/applications",
                          data={"job_id": job["id"], "cover_note": "TEST phase C"},
                          files=files, headers=H, timeout=60)
        assert r.status_code == 200, r.text
        app = r.json()

        # 2) admin accepts
        r2 = requests.put(f"{API}/applications/{app['id']}/status",
                          json={"status": "accepted"}, headers=admin_headers, timeout=30)
        assert r2.status_code == 200
        assert r2.json()["status"] == "accepted"

        # 3) admin schedules interview
        r3 = requests.post(f"{API}/interviews", json={
            "title": f"Entretien — {job['title']}",
            "candidate_id": uid, "candidate_name": "TEST BC Cand",
            "application_id": app["id"],
            "date": "2026-12-15", "time": "10:00",
            "location": "Visio", "notes": "TEST notes", "status": "scheduled",
        }, headers=admin_headers, timeout=30)
        assert r3.status_code == 200, r3.text
        itw = r3.json()
        assert itw["candidate_id"] == uid
        assert itw["date"] == "2026-12-15"

        # 4) candidate sees it via /interviews/me
        r_me = requests.get(f"{API}/interviews/me", headers=H, timeout=30)
        assert r_me.status_code == 200
        my_itws = r_me.json()
        assert any(i["id"] == itw["id"] for i in my_itws), "scheduled interview not in candidate's /interviews/me"

        # 5) candidate has interview notification
        r_n = requests.get(f"{API}/notifications", headers=H, timeout=30)
        assert r_n.status_code == 200
        d = r_n.json()
        assert any(n.get("type") == "interview" for n in d["items"]), "candidate should have interview notification"

        # 6) admin agenda: GET /interviews includes it
        r_all = requests.get(f"{API}/interviews", headers=admin_headers, timeout=30).json()
        assert any(i["id"] == itw["id"] for i in r_all)

        # cleanup
        requests.delete(f"{API}/interviews/{itw['id']}", headers=admin_headers, timeout=30)
