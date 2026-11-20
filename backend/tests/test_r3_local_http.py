"""Opt-in smoke test for the detached, loopback-only R3 backend."""
import json
import os
import secrets
import subprocess
import sys
import unittest

import httpx

from backend.r3_local_store import TARGET, connect


@unittest.skipUnless(os.getenv("R3_LOCAL_HTTP_TEST") == "1", "Explicit local HTTP test required")
class LocalHTTPTests(unittest.TestCase):
    def test_authentication_and_financial_routes(self):
        self.assertEqual(os.getenv("R3_SECURITY_TEST_TARGET"), TARGET)
        with connect(TARGET):
            pass
        with httpx.Client(base_url="http://127.0.0.1:8013", trust_env=False) as client:
            self.assertEqual(client.get("/api/accounts").status_code, 401)
            self.assertEqual(client.post("/api/auth/login", json={
                "email": "missing@example.com", "password": "invalid password",
            }).status_code, 401)
            sentinel = "synthetic-private-value"
            malformed = client.post("/api/auth/login", json={"email": [], "password": [sentinel]})
            self.assertEqual(malformed.status_code, 422)
            self.assertNotIn(sentinel, malformed.text)
            pairs = []
            for _ in range(2):
                body = {"email": f"standalone-{secrets.token_hex(8)}@example.com",
                        "password": secrets.token_urlsafe(24)}
                subprocess.run([sys.executable, "-B", "-m", "backend.r3_local_api", "provision"],
                               input=json.dumps(body), text=True, check=True)
                response = client.post("/api/auth/login", json=body)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["cache-control"], "no-store")
                pairs.append(response.json())
            a, b = pairs

            def headers(pair):
                return {"Authorization": "Bearer " + pair["access"]}

            def request(method, path, pair=a, **kwargs):
                return client.request(method, "/api" + path, headers=headers(pair), **kwargs)

            self.assertEqual(request("GET", "/auth/session").json()["user_id"], a["user_id"])
            self.assertEqual(request("GET", "/financial-context").json()["mode"], "authenticated_user")
            for path in ("/accounts", "/transactions/page", "/categories", "/debts", "/bills",
                         "/recurring", "/recurring-payments", "/budgets", "/goals",
                         "/calendar/summary", "/user", "/notes", "/summary"):
                self.assertEqual(request("GET", path).status_code, 200, path)
            account_ids = []
            for name, amount in (("Source", 100), ("Target", 0)):
                account = request("POST", "/accounts", json={"name": name, "initial_balance": amount})
                self.assertEqual(account.status_code, 200)
                account_ids.append(account.json()["id"])
            transfer = request("POST", "/transactions", json={
                "name": "Synthetic transfer", "type": "transfer", "amount": 15,
                "account_id": account_ids[0], "to_account_id": account_ids[1],
            })
            self.assertEqual(transfer.status_code, 200)
            self.assertEqual(request("GET", "/transactions/page").json()["total"], 1)
            self.assertEqual(request("GET", "/accounts", b).json(), [])
            self.assertEqual(request("PUT", f"/accounts/{account_ids[0]}", b,
                                     json={"name": "Foreign"}).status_code, 404)
            note = request("POST", "/notes", json={
                "title": "Synthetic note", "content": "Synthetic", "color": "#126046",
            })
            self.assertEqual(note.status_code, 201)
            self.assertEqual(request("GET", "/notes", b).json(), [])
            self.assertEqual(request("POST", "/seed").status_code, 404)
            response = client.post("/api/auth/refresh", json={"refresh": a["refresh"]})
            self.assertEqual(response.status_code, 200)
            renewed = response.json()
            self.assertEqual(request("GET", "/accounts").status_code, 401)
            self.assertEqual(client.post("/api/auth/logout",
                                         json={"refresh": renewed["refresh"]}).status_code, 204)
            self.assertEqual(request("GET", "/accounts", renewed).status_code, 401)
            self.assertEqual(client.post("/api/auth/refresh",
                                         json={"refresh": renewed["refresh"]}).status_code, 401)
            self.assertEqual(client.post("/api/auth/logout", json={"refresh": b["refresh"]}).status_code, 204)
