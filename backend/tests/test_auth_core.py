"""Synthetic tests; the transaction double serializes threads and rolls back."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import threading
import unittest
from uuid import UUID

from backend.auth_core import (
    AccountStatus, AuthService, Forbidden, InvalidCredentials, InvalidInput,
    Purpose, SessionLimit, StorageUnavailable,
)


PASSWORD = "synthetic password A"
NEW_PASSWORD = "synthetic replacement A"


class MemoryStore:
    def __init__(self):
        self.lock = threading.Lock()
        self.data = ({}, {}, {}, {})
        self.fail_commit = False

    @contextmanager
    def transaction(self):
        with self.lock:
            working = deepcopy(self.data)
            yield Transaction(*working)
            if self.fail_commit:
                raise StorageUnavailable("Authentication storage unavailable")
            self.data = working


class Transaction:
    def __init__(self, identities, families, refreshes, challenges):
        self.identities = identities
        self.families = families
        self.refreshes = refreshes
        self.challenges = challenges

    def identity(self, user_id):
        return self.identities.get(user_id)

    def identity_by_email(self, email):
        return next((user for user in self.identities.values() if user.email == email), None)

    def save_identity(self, identity):
        self.identities[identity.id] = identity

    def session(self, family_id):
        return self.families.get(family_id)

    def session_by_access(self, digest):
        return next((item for item in self.families.values() if item.access_digest == digest), None)

    def sessions(self, user_id):
        return [item for item in self.families.values() if item.user_id == user_id]

    def save_session(self, session):
        self.families[session.id] = session

    def refresh(self, digest):
        return self.refreshes.get(digest)

    def save_refresh(self, digest, refresh):
        self.refreshes[digest] = refresh

    def challenge(self, digest):
        return self.challenges.get(digest)

    def save_challenge(self, digest, challenge):
        self.challenges[digest] = challenge


class Delivery:
    def __init__(self):
        self.messages = []

    def deliver(self, email, purpose, token, expires):
        self.messages.append((email, purpose, token, expires))


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.delivery = Delivery()
        self.operator = object()
        self.now = datetime(2026, 11, 4, tzinfo=timezone.utc)
        self.service = AuthService(
            self.store, self.delivery, lambda actor: actor is self.operator, lambda: self.now
        )

    def enroll(self, email="a@example.com"):
        self.service.invite(self.operator, email)
        self.service.accept_invitation(self.delivery.messages[-1][2], PASSWORD)
        return self.service.login(email, PASSWORD)

    def test_identity_password_and_secret_handling(self):
        with self.assertNoLogs():
            tokens = self.enroll(" A@Example.COM ")
            principal = self.service.authenticate(tokens.access)
            other = self.service.authenticate(self.enroll("b@example.com").access)
        self.assertEqual(UUID(principal.user_id).version, 4)
        self.assertNotEqual(principal.user_id, other.user_id)
        self.assertNotEqual(principal.user_id, "default-user")
        first, second = self.store.data[0].values()
        self.assertEqual(first.email, "a@example.com")
        self.assertTrue(first.password_hash.startswith("$argon2id$"))
        self.assertNotEqual(first.password_hash, second.password_hash)
        for secret in (PASSWORD, tokens.access, tokens.refresh, self.delivery.messages[0][2]):
            self.assertNotIn(secret, repr((self.store.data, tokens)))
        for email in ("a@example.com", "missing@example.com"):
            with self.assertRaises(InvalidCredentials):
                self.service.login(email, NEW_PASSWORD)

    def test_manipulated_inputs_and_operator(self):
        with self.assertRaises(Forbidden):
            self.service.invite("operator", "a@example.com")
        with self.assertRaises(Forbidden):
            self.service.recover("operator", "a@example.com")
        with self.assertRaises(InvalidInput):
            self.service.invite(self.operator, "default-user")
        self.assertFalse(self.store.data[0])
        self.service.invite(self.operator, "a@example.com")
        token = self.delivery.messages[-1][2]
        with self.assertRaises(InvalidInput):
            self.service.accept_invitation(token, "short")
        with self.assertRaises(InvalidCredentials):
            self.service.reset_password(token, PASSWORD)
        self.service.accept_invitation(token, PASSWORD)
        with self.assertRaises(InvalidCredentials):
            self.service.authenticate("default-user")

    def test_invitation_expiry_and_consumption(self):
        self.service.invite(self.operator, "a@example.com")
        token = self.delivery.messages[-1][2]
        self.now += timedelta(hours=24)
        with self.assertRaises(InvalidCredentials):
            self.service.accept_invitation(token, PASSWORD)
        self.service.invite(self.operator, "a@example.com")
        token = self.delivery.messages[-1][2]
        self.service.accept_invitation(token, PASSWORD)
        with self.assertRaises(InvalidCredentials):
            self.service.accept_invitation(token, PASSWORD)

    def test_access_idle_and_absolute_expiry(self):
        tokens = self.enroll()
        self.now += timedelta(minutes=10)
        with self.assertRaises(InvalidCredentials):
            self.service.authenticate(tokens.access)
        tokens = self.service.rotate(tokens.refresh)
        self.now += timedelta(days=7)
        with self.assertRaises(InvalidCredentials):
            self.service.rotate(tokens.refresh)
        tokens = self.service.login("a@example.com", PASSWORD)
        for _ in range(4):
            self.now += timedelta(days=6)
            tokens = self.service.rotate(tokens.refresh)
        self.now += timedelta(days=6)
        with self.assertRaises(InvalidCredentials):
            self.service.rotate(tokens.refresh)

    def test_rotation_replay_and_logout(self):
        tokens = self.enroll()
        separate = self.service.login("a@example.com", PASSWORD)
        renewed = self.service.rotate(tokens.refresh)
        with self.assertRaises(InvalidCredentials):
            self.service.authenticate(tokens.access)
        self.service.authenticate(renewed.access)
        with self.assertRaises(InvalidCredentials):
            self.service.rotate(tokens.refresh)
        with self.assertRaises(InvalidCredentials):
            self.service.authenticate(renewed.access)
        with self.assertRaises(InvalidCredentials):
            self.service.rotate(renewed.refresh)
        self.service.authenticate(separate.access)
        self.service.logout(separate.access)
        self.service.logout(separate.access)
        with self.assertRaises(InvalidCredentials):
            self.service.rotate(separate.refresh)

    def test_limit_logout_all_and_disabled_account(self):
        tokens = self.enroll()
        for _ in range(9):
            self.service.login("a@example.com", PASSWORD)
        with self.assertRaises(SessionLimit):
            self.service.login("a@example.com", PASSWORD)
        with self.assertRaises(InvalidCredentials):
            self.service.logout_all(tokens.access, NEW_PASSWORD)
        self.service.logout_all(tokens.access, PASSWORD)
        self.assertTrue(all(family.revoked for family in self.store.data[1].values()))
        fresh = self.service.login("a@example.com", PASSWORD)
        user_id = self.service.authenticate(fresh.access).user_id
        with self.store.transaction() as tx:
            tx.save_identity(replace(tx.identity(user_id), status=AccountStatus.DISABLED))
        for operation, token in (
            (self.service.authenticate, fresh.access), (self.service.rotate, fresh.refresh)
        ):
            with self.assertRaises(InvalidCredentials):
                operation(token)

    def test_recovery_revokes_only_target_and_checks_expiry(self):
        first = self.enroll()
        second = self.enroll("b@example.com")
        self.service.recover(self.operator, "a@example.com")
        _, purpose, expired, _ = self.delivery.messages[-1]
        self.assertIs(purpose, Purpose.RECOVERY)
        self.now += timedelta(minutes=15)
        with self.assertRaises(InvalidCredentials):
            self.service.reset_password(expired, NEW_PASSWORD)
        self.service.recover(self.operator, "a@example.com")
        token = self.delivery.messages[-1][2]
        self.service.reset_password(token, NEW_PASSWORD)
        with self.assertRaises(InvalidCredentials):
            self.service.reset_password(token, PASSWORD)
        with self.assertRaises(InvalidCredentials):
            self.service.rotate(first.refresh)
        self.service.rotate(second.refresh)
        with self.assertRaises(InvalidCredentials):
            self.service.login("a@example.com", PASSWORD)
        self.service.login("a@example.com", NEW_PASSWORD)

    def test_failed_commit_does_not_release_tokens_or_consume_refresh(self):
        tokens = self.enroll()
        before = deepcopy(self.store.data)
        self.store.fail_commit = True
        with self.assertRaises(StorageUnavailable):
            self.service.rotate(tokens.refresh)
        self.assertEqual(self.store.data, before)
        with self.assertRaises(StorageUnavailable):
            self.service.authenticate(tokens.access)
        self.store.fail_commit = False
        self.service.rotate(tokens.refresh)

    def test_concurrent_rotation_simulation(self):
        tokens = self.enroll()
        barrier = threading.Barrier(2)

        def attempt():
            barrier.wait()
            try:
                return self.service.rotate(tokens.refresh)
            except InvalidCredentials:
                return None

        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda _: attempt(), range(2)))
        issued = [result for result in results if result is not None]
        self.assertEqual(len(issued), 1)
        with self.assertRaises(InvalidCredentials):
            self.service.authenticate(issued[0].access)
