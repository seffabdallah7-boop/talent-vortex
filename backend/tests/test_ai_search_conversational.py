"""Tests for POST /api/users/ai-search (conversational agent)."""
import os
import re
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://candidai.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "seffabdallah7@gmail.com"
ADMIN_PWD = "Admin@2026!"


def _solve_captcha(question: str) -> int:
    # question like "7 + 3 = ?"
    m = re.match(r"\s*(\d+)\s*([\+\-\*x×])\s*(\d+)", question)
    a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
    if op == "+": return a + b
    if op == "-": return a - b
    return a * b


@pytest.fixture(scope="module")
def admin_token():
    c = requests.get(f"{API}/auth/captcha", timeout=15).json()
    ans = _solve_captcha(c["question"])
    r = requests.post(f"{API}/auth/login", json={
        "email": ADMIN_EMAIL, "password": ADMIN_PWD,
        "captcha_id": c["captcha_id"], "captcha_answer": str(ans),
    }, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def test_ai_search_requires_auth():
    r = requests.post(f"{API}/users/ai-search", json={"query": "python"}, timeout=15)
    assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"


def test_ai_search_first_turn(h):
    r = requests.post(f"{API}/users/ai-search",
                      json={"query": "Qui a de l'expérience en développement ou en informatique ?", "history": []},
                      headers=h, timeout=90)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
    data = r.json()
    assert "answer" in data and isinstance(data["answer"], str)
    assert "results" in data and isinstance(data["results"], list)
    # Save for next test
    test_ai_search_first_turn._data = data
    test_ai_search_first_turn._query = "Qui a de l'expérience en développement ou en informatique ?"
    print(f"Turn 1 answer: {data['answer'][:200]}")
    print(f"Turn 1 results count: {len(data['results'])}")
    if data["results"]:
        r0 = data["results"][0]
        assert "user_id" in r0 and "ai_score" in r0 and "ai_reason" in r0
        assert isinstance(r0["ai_reason"], str) and len(r0["ai_reason"]) > 0


def test_ai_search_multi_turn(h):
    d1 = getattr(test_ai_search_first_turn, "_data", None)
    q1 = getattr(test_ai_search_first_turn, "_query", "Qui a de l'expérience ?")
    if d1 is None:
        pytest.skip("first turn did not run")
    history = [
        {"role": "user", "content": q1},
        {"role": "assistant", "content": d1.get("answer", "")},
    ]
    r = requests.post(f"{API}/users/ai-search",
                      json={"query": "Parmi eux, lequel a le plus d'années d'expérience ?", "history": history},
                      headers=h, timeout=90)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
    data = r.json()
    assert isinstance(data.get("answer", ""), str)
    assert isinstance(data.get("results", []), list)
    print(f"Turn 2 answer: {data['answer'][:200]}")
    print(f"Turn 2 results count: {len(data['results'])}")


def test_ai_search_empty_query(h):
    r = requests.post(f"{API}/users/ai-search",
                      json={"query": "  ", "history": []}, headers=h, timeout=30)
    assert r.status_code == 200
    assert r.json().get("results") == []
