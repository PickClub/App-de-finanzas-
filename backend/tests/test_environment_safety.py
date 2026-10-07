"""Pure settings tests: no server import, client, real dotenv or database."""
import ast
from pathlib import Path
import unittest
from unittest.mock import patch

from backend.config import ConfigurationError, load_settings, settings_from_mapping


class EnvironmentSafetyTests(unittest.TestCase):
    def values(self, **changes):
        return {"APP_ENV": "development", "MONGO_URL": "mongodb://127.0.0.1:27017",
                "DB_NAME": "example_development", "CORS_ORIGINS": "http://localhost:8081",
                "LOG_LEVEL": "INFO", **changes}

    def test_invalid_environment(self):
        for env in ["", "prod", "staging", "Production"]:
            with self.subTest(env=env), self.assertRaises(ConfigurationError):
                settings_from_mapping(self.values(APP_ENV=env))

    def test_production_open_cors_rejected(self):
        for cors in ["*", "https://example.invalid,*", "https://*.example.invalid", ""]:
            with self.subTest(cors=cors), self.assertRaises(ConfigurationError):
                settings_from_mapping(self.values(APP_ENV="production", CORS_ORIGINS=cors))

    def test_production_test_database_rejected(self):
        for db in ["test_example", "example_test", "example-testing", "TEST", "testdb", "example_testdb"]:
            with self.subTest(db=db), self.assertRaises(ConfigurationError):
                settings_from_mapping(self.values(APP_ENV="production", DB_NAME=db))

    def test_production_requires_mongo_url(self):
        with self.assertRaises(ConfigurationError):
            settings_from_mapping(self.values(APP_ENV="production", MONGO_URL=""))

    def test_dangerous_test_configuration_rejected(self):
        unsafe = [
            {"MONGO_URL": "mongodb+srv://example.invalid/test_example"},
            {"MONGO_URL": "mongodb://example.invalid/test_example"},
            {"MONGO_URL": "mongodb://localhost:27017,example.invalid:27017"},
            {"MONGO_URL": "mongodb://localhost:27017/example_production"},
            {"MONGO_URL": "mongodb://user:fictional@localhost:27017"},
            {"MONGO_URL": "mongodb://localhost:27017/?authSource=admin"},
            {"MONGO_URL": "mongodb://localhost:wrong"},
            {"DB_NAME": "example_production"},
        ]
        for change in unsafe:
            with self.subTest(change=change), self.assertRaises(ConfigurationError):
                settings_from_mapping(self.values(APP_ENV="test", DB_NAME="test_example") | change)

    def test_development_valid_and_backwards_compatible(self):
        values = self.values()
        del values["APP_ENV"]
        del values["CORS_ORIGINS"]
        settings = settings_from_mapping(values)
        self.assertEqual(settings.app_env, "development")
        self.assertEqual(settings.cors_origins, ("*",))

    def test_explicit_test_valid(self):
        settings = settings_from_mapping(self.values(APP_ENV="test", DB_NAME="test_example",
            MONGO_URL="mongodb://127.0.0.1:27018/test_example?replicaSet=test_rs&directConnection=true"))
        self.assertEqual(settings.app_env, "test")

    def test_test_runner_rejects_other_environments(self):
        for env in ["development", "production"]:
            with self.subTest(env=env), self.assertRaises(ConfigurationError):
                load_settings(self.values(APP_ENV=env), testing=True)
        with self.assertRaises(ConfigurationError):
            load_settings({}, testing=True)

    def test_auto_detects_unittest(self):
        with self.assertRaises(ConfigurationError):
            load_settings(self.values(APP_ENV="production"))

    def test_test_never_reads_dotenv(self):
        with patch("backend.config.dotenv_values", side_effect=AssertionError("dotenv forbidden")):
            settings = load_settings(self.values(APP_ENV="test", DB_NAME="test_example"))
            self.assertEqual(settings.app_env, "test")

    def test_process_environment_overrides_dotenv(self):
        with patch("backend.config.dotenv_values", return_value=self.values(LOG_LEVEL="ERROR")):
            settings = load_settings({"LOG_LEVEL": "DEBUG"}, testing=False)
            self.assertEqual(settings.log_level, "DEBUG")

    def test_invalid_log_level_and_database(self):
        for change in [{"LOG_LEVEL": "invalid"}, {"DB_NAME": ""}, {"DB_NAME": "bad/name"}]:
            with self.subTest(change=change), self.assertRaises(ConfigurationError):
                settings_from_mapping(self.values() | change)

    def test_uri_not_in_errors_or_settings_repr(self):
        uri = "mongodb://user:fictional-password@example.invalid"
        self.assertNotIn("fictional-password", repr(settings_from_mapping(self.values(MONGO_URL=uri))))
        with self.assertRaises(ConfigurationError) as error:
            settings_from_mapping(self.values(APP_ENV="test", DB_NAME="test_example", MONGO_URL=uri))
        self.assertNotIn(uri, str(error.exception))

    def test_valid_production(self):
        settings = settings_from_mapping(self.values(APP_ENV="production", DB_NAME="example_live",
            MONGO_URL="mongodb+srv://example.invalid", CORS_ORIGINS="https://app.example.invalid"))
        self.assertEqual(settings.cors_origins, ("https://app.example.invalid",))

    def test_server_validates_before_constructing_client(self):
        # Execute just the startup statements with a forbidden client, not server.py.
        tree = ast.parse(Path(__file__).resolve().parents[1].joinpath("server.py").read_text())
        statements = [n for n in tree.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id in {"settings", "client", "db"} for t in n.targets)]
        def forbidden_client(*args):
            self.fail("MongoDB client must not be constructed for unsafe settings")
        namespace = {"load_settings": lambda: load_settings(self.values(APP_ENV="production"), testing=True),
                     "AsyncIOMotorClient": forbidden_client}
        with self.assertRaises(ConfigurationError):
            exec(compile(ast.Module(body=statements, type_ignores=[]), "startup", "exec"), namespace)


if __name__ == "__main__":
    unittest.main()
