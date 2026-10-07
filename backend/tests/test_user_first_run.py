"""First-run profile regression; no server import, dotenv or live database."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

from bson import ObjectId
from fastapi import APIRouter, FastAPI
import httpx


class UserFirstRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_creation_and_second_read_return_same_json_user(self):
        stored = {}

        class Users:
            async def find_one(self, query, projection):
                if not stored:
                    return None
                self_projection = {key: value for key, value in stored.items()
                                   if projection.get(key) != 0}
                return self_projection

            async def insert_one(self, document):
                # Match PyMongo's mutation of the caller's dictionary.
                document["_id"] = ObjectId()
                stored.update(document)

        class User:
            def __init__(self, **values):
                self.values = values

            def model_dump(self):
                return dict(self.values)

        source = Path(__file__).resolve().parents[1] / "server.py"
        tree = ast.parse(source.read_text())
        nodes = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                 and node.name in {"ensure_user", "get_user"}]
        router = APIRouter(prefix="/api")
        namespace = {"db": SimpleNamespace(users=Users()), "PROJ": {"_id": 0},
                     "DEFAULT_USER_ID": "synthetic-user", "User": User, "api": router}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), namespace)
        app = FastAPI()
        app.include_router(router)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                                     base_url="http://user-test.invalid") as client:
            first = await client.get("/api/user")
            self.assertEqual(first.status_code, 200)
            second = await client.get("/api/user")
            self.assertEqual(second.status_code, 200)
        self.assertNotIn("_id", first.json())
        self.assertNotIn("_id", second.json())
        self.assertEqual(first.json(), second.json())
        self.assertEqual(first.json()["id"], "synthetic-user")
        self.assertIsInstance(stored["_id"], ObjectId)


if __name__ == "__main__":
    unittest.main()
