"""Category-only integration checks on the explicitly authorized R3 replica."""
import os
import secrets
import unittest
from uuid import uuid4

import httpx

from backend.auth_core import AuthService
from backend.r3_local_store import DATABASE, TARGET, Store, connect
from backend.tests.test_auth_core import Delivery


@unittest.skipUnless(os.getenv("R3_CATEGORY_TEST_TARGET"), "Explicit synthetic target required")
class CategoryOnboardingTests(unittest.TestCase):
    def test_empty_repeat_custom_and_owner_isolation(self):
        target = os.environ["R3_CATEGORY_TEST_TARGET"]
        self.assertEqual(target, TARGET)
        with connect(target) as client, httpx.Client(
            base_url="http://127.0.0.1:8013", trust_env=False
        ) as http:
            db = client[DATABASE]
            delivery, operator = Delivery(), object()
            auth = AuthService(Store(db), delivery, lambda actor: actor is operator)
            profiles = []
            for _ in range(2):
                email, password = f"category-{uuid4().hex}@example.com", secrets.token_urlsafe(24)
                auth.invite(operator, email)
                auth.accept_invitation(delivery.messages[-1][2], password)
                result = http.post("/api/auth/login", json={"email": email, "password": password})
                self.assertEqual(result.status_code, 200)
                pair = result.json()
                profiles.append(pair)
            try:
                a, b = profiles
                headers = lambda pair: {"Authorization": "Bearer " + pair["access"]}
                for pair in profiles:
                    self.assertEqual(http.get("/api/categories", headers=headers(pair)).json(), [])
                custom = http.post("/api/categories", headers=headers(b), json={
                    "name": "Custom ñ category", "icon": "leaf-outline", "color": "#123456",
                })
                self.assertEqual(custom.status_code, 200)
                custom_id = custom.json()["id"]
                preserved = db.categories.find_one({"id": custom_id, "user_id": b["user_id"]})
                for pair in profiles:
                    response = http.post("/api/categories/init-defaults", headers=headers(pair))
                    self.assertEqual(response.status_code, 200)
                    self.assertGreater(response.json()["created"], 0)
                    snapshot = list(db.categories.find({"user_id": pair["user_id"]}).sort("_id", 1))
                    again = http.post("/api/categories/init-defaults", headers=headers(pair))
                    self.assertEqual(again.status_code, 200)
                    self.assertEqual(again.json()["created"] + again.json()["groups_created"] + again.json()["links"], 0)
                    self.assertEqual(snapshot, list(db.categories.find({"user_id": pair["user_id"]}).sort("_id", 1)))
                    choices = http.get("/api/categories", headers=headers(pair)).json()
                    self.assertTrue(all(row["user_id"] == pair["user_id"] for row in choices))
                    for kind in ("income", "expense"):
                        self.assertTrue(any(row["type"] == kind and not row.get("is_group") for row in choices))
                self.assertEqual(preserved, db.categories.find_one({"id": custom_id, "user_id": b["user_id"]}))
                self.assertEqual(http.get("/api/categories", headers=headers(a)).json().__len__() + 1,
                                 len(http.get("/api/categories", headers=headers(b)).json()))
                self.assertEqual(db.categories.count_documents({"id": custom_id, "user_id": a["user_id"]}), 0)
                self.assertEqual(db.transactions.count_documents({"user_id": {"$in": [a["user_id"], b["user_id"]]}}), 0)
            finally:
                for pair in profiles:
                    http.post("/api/auth/logout", json={"refresh": pair["refresh"]})
