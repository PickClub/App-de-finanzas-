"""Seed regression tests with an in-process API and no MongoDB client or .env.

Run directly: python -B backend/tests/test_seed_safety.py
Only the seed route is loaded from the AST, so importing server.py cannot open
a database connection. Any attempt to access data fails the test immediately.
"""

import ast
import asyncio
from pathlib import Path
import unittest
from unittest.mock import AsyncMock

import httpx
from fastapi import APIRouter, FastAPI, HTTPException


class ForbiddenDatabase:
    def __getattr__(self, name):
        raise AssertionError(f"Seed must not access MongoDB: {name}")


class SeedSafetyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / "server.py"
        tree = ast.parse(source.read_text())
        seed = next(
            node for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "seed"
        )
        router = APIRouter(prefix="/api")
        self.ensure_user = AsyncMock(
            side_effect=AssertionError("Seed must not create or read a user")
        )
        namespace = {
            "api": router,
            "HTTPException": HTTPException,
            "db": ForbiddenDatabase(),
            "ensure_user": self.ensure_user,
        }
        exec(compile(ast.Module(body=[seed], type_ignores=[]), str(source), "exec"), namespace)
        self.app = FastAPI()
        self.app.include_router(router)

    def client(self):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://seed-test.invalid",
        )

    async def test_seed_is_forbidden_without_accessing_data(self):
        async with self.client() as client:
            response = await client.post("/api/seed")
        self.assertEqual(response.status_code, 403)
        self.assertIn("detail", response.json())
        self.ensure_user.assert_not_awaited()

    async def test_client_options_cannot_enable_seed(self):
        async with self.client() as client:
            for payload in ({}, {"force": True}, {"demo": True, "confirm": True}):
                with self.subTest(payload=payload):
                    response = await client.post("/api/seed?force=true", json=payload)
                    self.assertEqual(response.status_code, 403)
        self.ensure_user.assert_not_awaited()

    async def test_repeated_concurrent_requests_never_access_data(self):
        async with self.client() as client:
            responses = await asyncio.gather(*[
                client.post("/api/seed") for _ in range(10)
            ])
        self.assertEqual([r.status_code for r in responses], [403] * 10)
        self.ensure_user.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
