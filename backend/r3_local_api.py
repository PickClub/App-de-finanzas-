"""Standalone R3 API for the explicitly authorized synthetic replica."""
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import os
import sys
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.auth_core import (
    AuthService, HashCapacityExceeded, InvalidCredentials, InvalidInput,
    SessionLimit, StorageUnavailable,
)
from backend.authenticated_api import create_authenticated_app, verified_principal_dependency
from backend.r3_local_store import DATABASE, Fence, Store, async_client, connect, retry_auth


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=512)
    password: str = Field(max_length=128)


class DeleteAccountInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    password: str = Field(min_length=1, max_length=128)


class RefreshInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refresh: str = Field(max_length=64)


class InvitationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invitation: str = Field(max_length=64)
    password: str = Field(max_length=128)


class SyntheticDelivery:
    def __init__(self):
        self.invitation = None

    def deliver(self, email, purpose, token, expires):
        self.invitation = token


def initialize(database):
    for name, key in (("auth_users", "email"), ("auth_sessions", "access_digest"), ("users", "id")):
        database[name].create_index(key, unique=True)
    database.moneyflow_metadata.update_one(
        {"_id": "financial-context"},
        {"$setOnInsert": {"version": 1, "environment_id": str(uuid4()),
                          "created_at": datetime.now(timezone.utc).isoformat()}}, upsert=True,
    )
    return database.moneyflow_metadata.find_one({"_id": "financial-context"})["environment_id"]


def create_app():
    target = os.environ["R3_SECURITY_TEST_TARGET"]
    sync = connect(target)
    try:
        database = sync[DATABASE]
        environment = initialize(database)
        motor = async_client(target)
    except BaseException:
        sync.close()
        raise
    auth = AuthService(Store(database), SyntheticDelivery(), lambda _: False)
    app = create_authenticated_app(auth, motor[DATABASE],
                                   expected_environment_id=environment,
                                   write_fence=Fence(motor[DATABASE]),
                                   advertise_payment_context=True)
    current = verified_principal_dependency(auth)
    routes = APIRouter(prefix="/api/auth")

    @asynccontextmanager
    async def lifespan(_):
        try:
            yield
        finally:
            motor.close()
            sync.close()

    app.router.lifespan_context = lifespan

    @app.exception_handler(RequestValidationError)
    async def redact_credentials(request: Request, error: RequestValidationError):
        if request.url.path.startswith("/api/auth/"):
            return JSONResponse({"detail": "Invalid authentication request"}, status_code=422,
                                headers={"Cache-Control": "no-store"})
        return await request_validation_exception_handler(request, error)

    def invoke(operation, *args):
        try:
            return retry_auth(operation, *args)
        except (InvalidCredentials, InvalidInput):
            raise HTTPException(401, "Invalid credentials", headers={"WWW-Authenticate": "Bearer"}) from None
        except SessionLimit:
            raise HTTPException(409, "Active session limit reached") from None
        except (StorageUnavailable, HashCapacityExceeded):
            raise HTTPException(503, "Authentication unavailable") from None

    def session_response(tokens, response):
        response.headers["Cache-Control"] = "no-store"
        principal = invoke(auth.authenticate, tokens.access)
        return {**asdict(tokens), "user_id": principal.user_id, "environment_id": environment}

    @routes.post("/login")
    def login(body: Credentials, response: Response):
        return session_response(invoke(auth.login, body.email, body.password), response)

    @routes.post("/refresh")
    def refresh(body: RefreshInput, response: Response):
        return session_response(invoke(auth.rotate, body.refresh), response)

    @routes.get("/session")
    def session(response: Response, principal=Depends(current)):
        response.headers["Cache-Control"] = "no-store"
        return {"user_id": principal.user_id, "environment_id": environment}

    @routes.post("/account/delete", status_code=204)
    def delete_account(body: DeleteAccountInput, principal=Depends(current)):
        invoke(auth.delete_account, principal, body.password)
        return Response(status_code=204, headers={"Cache-Control": "no-store"})

    @routes.post("/logout", status_code=204)
    def logout(body: RefreshInput):
        invoke(auth.logout_refresh, body.refresh)
        return Response(status_code=204, headers={"Cache-Control": "no-store"})

    @routes.post("/invite/accept", status_code=204)
    def accept_invitation(body: InvitationInput):
        invoke(auth.accept_invitation, body.invitation, body.password)
        return Response(status_code=204, headers={"Cache-Control": "no-store"})

    # Install auth routes before the authenticated API's catch-all.
    existing = app.router.routes[:]
    app.router.routes.clear()
    app.include_router(routes)
    app.router.routes.extend(existing)
    return app


def provision():
    """Read synthetic credentials from stdin; no public operator endpoint."""
    import json
    payload = Credentials.model_validate(json.load(sys.stdin))
    with connect(os.environ["R3_SECURITY_TEST_TARGET"]) as client:
        database = client[DATABASE]
        initialize(database)
        delivery = SyntheticDelivery()
        operator = object()
        auth = AuthService(Store(database), delivery, lambda actor: actor is operator)
        auth.invite(operator, payload.email)
        auth.accept_invitation(delivery.invitation, payload.password)


if __name__ == "__main__":
    if sys.argv[1:] != ["provision"]:
        raise SystemExit("Expected explicit provision command")
    provision()
