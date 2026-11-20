"""Offline-testable R3 identity and session service. No routes or database wiring."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from hashlib import sha256
import re
from secrets import token_urlsafe
from threading import BoundedSemaphore
from typing import Protocol
from uuid import uuid4

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError
from email_validator import EmailNotValidError, validate_email


ACCESS_LIFETIME = timedelta(minutes=10)
IDLE_LIFETIME = timedelta(days=7)
ABSOLUTE_LIFETIME = timedelta(days=30)
MAX_FAMILIES = 10


class AuthError(Exception):
    """Safe domain error suitable for translation at a future API boundary."""


class InvalidCredentials(AuthError):
    pass


class InvalidInput(AuthError):
    pass


class Forbidden(AuthError):
    pass


class EnrollmentConflict(AuthError):
    pass


class SessionLimit(AuthError):
    pass


class StorageUnavailable(AuthError):
    """The adapter must translate storage errors without exposing driver details."""


class HashCapacityExceeded(AuthError):
    """Local password hashing capacity is exhausted."""


class DeliveryUnavailable(AuthError):
    """The delivery adapter must translate failures without exposing the message."""


class AccountStatus(Enum):
    INVITED = "invited"
    ACTIVE = "active"
    DISABLED = "disabled"


class Purpose(Enum):
    INVITATION = "invite"
    RECOVERY = "recover"


@dataclass(frozen=True)
class Identity:
    id: str
    email: str = field(repr=False)
    status: AccountStatus
    password_hash: str | None = field(default=None, repr=False)
    credential_version: int = 0


@dataclass(frozen=True)
class Session:
    id: str
    user_id: str
    access_digest: str = field(repr=False)
    access_expires: datetime
    idle_expires: datetime
    absolute_expires: datetime
    generation: int = 0
    revoked: bool = False

    def active(self, now: datetime) -> bool:
        return not self.revoked and now < min(self.idle_expires, self.absolute_expires)


@dataclass(frozen=True)
class Refresh:
    family_id: str
    generation: int
    consumed: bool = False


@dataclass(frozen=True)
class Challenge:
    user_id: str
    purpose: Purpose
    credential_version: int
    expires: datetime
    consumed: bool = False


@dataclass(frozen=True)
class Tokens:
    access: str = field(repr=False)
    refresh: str = field(repr=False)
    access_expires: datetime


@dataclass(frozen=True)
class Principal:
    user_id: str
    family_id: str
    access_digest: str = field(repr=False)


class AuthTransaction(Protocol):
    def erase_account(self, user_id: str) -> None: ...
    def identity(self, user_id: str) -> Identity | None: ...
    def identity_by_email(self, email: str) -> Identity | None: ...
    def save_identity(self, identity: Identity) -> None: ...
    def session(self, family_id: str) -> Session | None: ...
    def session_by_access(self, digest: str) -> Session | None: ...
    def sessions(self, user_id: str) -> list[Session]: ...
    def save_session(self, session: Session) -> None: ...
    def refresh(self, digest: str) -> Refresh | None: ...
    def save_refresh(self, digest: str, refresh: Refresh) -> None: ...
    def challenge(self, digest: str) -> Challenge | None: ...
    def save_challenge(self, digest: str, challenge: Challenge) -> None: ...


class AuthStore(Protocol):
    """Provide atomic, serializable units, including reads used for decisions.

    An adapter must commit on normal exit and roll back on exceptions. MongoDB
    snapshot reads alone are insufficient: coordinate conflicting operations
    on the same identity/family and enforce unique indexes. See R3 delivery notes.
    """

    def transaction(self) -> AbstractContextManager[AuthTransaction]: ...


class ChallengeDelivery(Protocol):
    def deliver(self, email: str, purpose: Purpose, token: str, expires: datetime) -> None: ...


def normalize_email(email: str) -> str:
    if not isinstance(email, str) or len(email) > 512:
        raise InvalidInput("Invalid email")
    try:
        return validate_email(email.strip().lower(), check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        raise InvalidInput("Invalid email") from None


def valid_password(password: str) -> bool:
    if not isinstance(password, str) or not 15 <= len(password) <= 128:
        return False
    try:
        return len(password.encode("utf-8")) <= 1024
    except UnicodeEncodeError:
        return False


def new_token(kind: str) -> str:
    return f"{kind}.{token_urlsafe(32)}"


def token_digest(token: str, kind: str) -> str:
    if not isinstance(token, str) or not re.fullmatch(
        rf"{kind}\.[A-Za-z0-9_-]{{43}}", token
    ):
        raise InvalidCredentials("Invalid credentials")
    return sha256(token.encode("ascii")).hexdigest()


class AuthService:
    """Synchronous service for trusted callers, with no public operator surface."""

    def __init__(
        self,
        store: AuthStore,
        delivery: ChallengeDelivery,
        authorize_operator: Callable[[object], bool],
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.store = store
        self.delivery = delivery
        self.authorize_operator = authorize_operator
        self.clock = clock
        self.passwords = PasswordHasher(
            memory_cost=65536, time_cost=3, parallelism=1, type=Type.ID
        )
        self._hash_slots = BoundedSemaphore(2)
        self._dummy_hash = self._hash_password(token_urlsafe(32))

    def _password_work(self, operation: Callable, *args):
        if not self._hash_slots.acquire(blocking=False):
            raise HashCapacityExceeded("Authentication temporarily unavailable")
        try:
            return operation(*args)
        finally:
            self._hash_slots.release()

    def _hash_password(self, password: str) -> str:
        return self._password_work(self.passwords.hash, password)

    def _verify_password(self, password_hash: str, password: str) -> None:
        try:
            verified = self._password_work(self.passwords.verify, password_hash, password)
        except (VerificationError, InvalidHashError):
            raise InvalidCredentials("Invalid credentials") from None
        if not verified:
            raise InvalidCredentials("Invalid credentials")

    def invite(self, operator: object, email: str) -> None:
        self._issue_challenge(operator, email, Purpose.INVITATION, timedelta(hours=24))

    def recover(self, operator: object, email: str) -> None:
        self._issue_challenge(operator, email, Purpose.RECOVERY, timedelta(minutes=15))

    def _issue_challenge(
        self, operator: object, email: str, purpose: Purpose, lifetime: timedelta
    ) -> None:
        if not self.authorize_operator(operator):
            raise Forbidden("Operator authorization required")
        email = normalize_email(email)
        token = new_token(purpose.value)
        with self.store.transaction() as tx:
            identity = tx.identity_by_email(email)
            expected = AccountStatus.INVITED if purpose is Purpose.INVITATION else AccountStatus.ACTIVE
            if identity is None and purpose is Purpose.INVITATION:
                identity = Identity(str(uuid4()), email, AccountStatus.INVITED)
                tx.save_identity(identity)
            if identity is None or identity.status is not expected:
                raise EnrollmentConflict("Account unavailable for this operation")
            expires = self.clock() + lifetime
            tx.save_challenge(
                token_digest(token, purpose.value),
                Challenge(identity.id, purpose, identity.credential_version, expires),
            )
        self.delivery.deliver(email, purpose, token, expires)

    def accept_invitation(self, token: str, password: str) -> None:
        self._set_password(token, password, Purpose.INVITATION, AccountStatus.INVITED)

    def reset_password(self, token: str, password: str) -> None:
        self._set_password(token, password, Purpose.RECOVERY, AccountStatus.ACTIVE)

    def _challenge_identity(
        self, tx: AuthTransaction, digest: str, purpose: Purpose, expected: AccountStatus
    ) -> tuple[Challenge, Identity]:
        challenge = tx.challenge(digest)
        if (
            challenge is None or challenge.purpose is not purpose
            or challenge.consumed or self.clock() >= challenge.expires
        ):
            raise InvalidCredentials("Invalid credentials")
        identity = tx.identity(challenge.user_id)
        if (
            identity is None or identity.status is not expected
            or identity.credential_version != challenge.credential_version
        ):
            raise InvalidCredentials("Invalid credentials")
        return challenge, identity

    def _set_password(
        self, token: str, password: str, purpose: Purpose, expected: AccountStatus
    ) -> None:
        digest = token_digest(token, purpose.value)
        if not valid_password(password):
            raise InvalidInput("Invalid password")
        with self.store.transaction() as tx:
            self._challenge_identity(tx, digest, purpose, expected)
        password_hash = self._hash_password(password)
        with self.store.transaction() as tx:
            challenge, identity = self._challenge_identity(tx, digest, purpose, expected)
            tx.save_challenge(digest, replace(challenge, consumed=True))
            tx.save_identity(replace(
                identity, status=AccountStatus.ACTIVE, password_hash=password_hash,
                credential_version=identity.credential_version + 1,
            ))
            self._revoke_all(tx, identity.id)

    def _verify_account_password(self, email: str, password: str) -> Identity:
        try:
            email = normalize_email(email)
        except InvalidInput:
            raise InvalidCredentials("Invalid credentials") from None
        if not valid_password(password):
            raise InvalidCredentials("Invalid credentials")
        with self.store.transaction() as tx:
            identity = tx.identity_by_email(email)
        active = identity is not None and identity.status is AccountStatus.ACTIVE
        password_hash = identity.password_hash if active else None
        self._verify_password(password_hash or self._dummy_hash, password)
        if not password_hash or identity is None:
            raise InvalidCredentials("Invalid credentials")
        return identity

    def login(self, email: str, password: str) -> Tokens:
        identity = self._verify_account_password(email, password)
        assert identity.password_hash is not None
        password_hash = identity.password_hash
        updated_hash = (
            self._hash_password(password)
            if self.passwords.check_needs_rehash(password_hash) else password_hash
        )
        with self.store.transaction() as tx:
            if tx.identity(identity.id) != identity:
                raise InvalidCredentials("Invalid credentials")
            now = self.clock()
            if sum(session.active(now) for session in tx.sessions(identity.id)) >= MAX_FAMILIES:
                raise SessionLimit("Active session limit reached")
            if updated_hash != password_hash:
                tx.save_identity(replace(identity, password_hash=updated_hash))
            session = Session(
                str(uuid4()), identity.id, "", now, now + IDLE_LIFETIME, now + ABSOLUTE_LIFETIME
            )
            return self._issue_tokens(tx, session, now)

    def _issue_tokens(self, tx: AuthTransaction, session: Session, now: datetime) -> Tokens:
        access, refresh = new_token("access"), new_token("refresh")
        expires = min(now + ACCESS_LIFETIME, session.idle_expires, session.absolute_expires)
        tx.save_session(replace(
            session, access_digest=token_digest(access, "access"), access_expires=expires,
        ))
        tx.save_refresh(
            token_digest(refresh, "refresh"), Refresh(session.id, session.generation)
        )
        return Tokens(access, refresh, expires)

    def rotate(self, token: str) -> Tokens:
        digest = token_digest(token, "refresh")
        with self.store.transaction() as tx:
            now = self.clock()
            previous = tx.refresh(digest)
            if previous is None:
                raise InvalidCredentials("Invalid credentials")
            session = tx.session(previous.family_id)
            self._require_active(tx, session, now)
            assert session is not None
            if previous.consumed:
                tx.save_session(replace(session, revoked=True))
            else:
                if previous.generation != session.generation:
                    raise InvalidCredentials("Invalid credentials")
                tx.save_refresh(digest, replace(previous, consumed=True))
                return self._issue_tokens(tx, replace(
                    session, generation=session.generation + 1,
                    idle_expires=min(now + IDLE_LIFETIME, session.absolute_expires),
                ), now)
        # Commit replay revocation before returning the authentication failure.
        raise InvalidCredentials("Invalid credentials")

    def authenticate(self, token: str) -> Principal:
        digest = token_digest(token, "access")
        with self.store.transaction() as tx:
            session = self._access_session(tx, digest)
            return Principal(session.user_id, session.id, digest)

    def logout(self, token: str) -> None:
        digest = token_digest(token, "access")
        with self.store.transaction() as tx:
            session = tx.session_by_access(digest)
            if session is not None and not session.revoked:
                session = self._access_session(tx, digest)
                tx.save_session(replace(session, revoked=True))

    def logout_refresh(self, token: str) -> None:
        """Revoke a family even when its short-lived access token has expired."""
        digest = token_digest(token, "refresh")
        with self.store.transaction() as tx:
            refresh = tx.refresh(digest)
            if refresh is None:
                return
            session = tx.session(refresh.family_id)
            if session is not None and not session.revoked:
                tx.save_session(replace(session, revoked=True))

    def logout_all(self, token: str, password: str) -> None:
        digest = token_digest(token, "access")
        with self.store.transaction() as tx:
            session = self._access_session(tx, digest)
            identity = tx.identity(session.user_id)
        if not valid_password(password) or identity is None or identity.password_hash is None:
            raise InvalidCredentials("Invalid credentials")
        self._verify_password(identity.password_hash, password)
        with self.store.transaction() as tx:
            self._access_session(tx, digest)
            if tx.identity(identity.id) != identity:
                raise InvalidCredentials("Invalid credentials")
            self._revoke_all(tx, identity.id)

    def delete_account(self, principal: Principal, password: str) -> None:
        with self.store.transaction() as tx:
            session = self._access_session(tx, principal.access_digest)
            if (session.user_id, session.id) != (principal.user_id, principal.family_id):
                raise InvalidCredentials("Invalid credentials")
            identity = tx.identity(session.user_id)
        if not valid_password(password) or identity is None or not identity.password_hash:
            raise InvalidCredentials("Invalid credentials")
        self._verify_password(identity.password_hash, password)
        with self.store.transaction() as tx:
            current = self._access_session(tx, principal.access_digest)
            if (current.user_id, current.id) != (identity.id, principal.family_id) or tx.identity(identity.id) != identity:
                raise InvalidCredentials("Invalid credentials")
            tx.erase_account(identity.id)

    def delete_account_with_password(self, email: str, password: str) -> None:
        """Verify browser credentials and erase the matching identity without issuing a session."""
        identity = self._verify_account_password(email, password)
        with self.store.transaction() as tx:
            if tx.identity(identity.id) != identity:
                raise InvalidCredentials("Invalid credentials")
            tx.erase_account(identity.id)

    @staticmethod
    def _revoke_all(tx: AuthTransaction, user_id: str) -> None:
        for session in tx.sessions(user_id):
            if not session.revoked:
                tx.save_session(replace(session, revoked=True))

    def _access_session(self, tx: AuthTransaction, digest: str) -> Session:
        now = self.clock()
        session = tx.session_by_access(digest)
        if session is None or now >= session.access_expires:
            raise InvalidCredentials("Invalid credentials")
        self._require_active(tx, session, now)
        return session

    @staticmethod
    def _require_active(tx: AuthTransaction, session: Session | None, now: datetime) -> None:
        if session is None or not session.active(now):
            raise InvalidCredentials("Invalid credentials")
        identity = tx.identity(session.user_id)
        if identity is None or identity.status is not AccountStatus.ACTIVE:
            raise InvalidCredentials("Invalid credentials")
