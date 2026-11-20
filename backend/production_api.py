"""Production factory. Run only behind the explicitly trusted HTTPS proxy."""

from contextlib import asynccontextmanager
from dataclasses import asdict
from ipaddress import ip_address
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, Field
from pymongo import MongoClient
from starlette.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from backend.auth_core import (
    AuthService,
    AuthError,
    InvalidCredentials,
    InvalidInput,
    SessionLimit,
    StorageUnavailable,
    HashCapacityExceeded,
    normalize_email,
)
from backend.auth_mongodb import Store, Fence, retry_auth
from backend.authenticated_api import (
    create_authenticated_app,
    verified_principal_dependency,
)
from backend.production_config import ProductionConfig
from backend.production_services import (
    SMTPDelivery,
    MongoRateLimiter,
    RateLimited,
    verify_database,
)

logger = logging.getLogger("pickwallet.security")


WEB_DIRECTORY = Path(__file__).with_name("privacy_web")
WEB_FILES = {
    "/privacy": "privacy-en.html",
    "/privacy/es": "privacy-es.html",
    "/delete-account": "delete-en.html",
    "/delete-account/es": "delete-es.html",
    "/privacy-assets/delete.js": "delete.js",
    "/privacy-assets/pages.css": "pages.css",
}
DEFAULT_CSP = b"default-src 'none'; frame-ancestors 'none'"
WEB_CSP = (
    DEFAULT_CSP
    + b"; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'"
)


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=512)
    password: str = Field(max_length=128)


class DeleteAccountInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    password: str = Field(min_length=1, max_length=128)


class WebDeletionInput(Credentials):
    model_config = ConfigDict(extra="forbid", strict=True)
    confirmed: bool


class RefreshInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refresh: str = Field(max_length=64)


class ChallengeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(max_length=64)
    password: str = Field(max_length=128)


class InvitationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invitation: str = Field(max_length=64)
    password: str = Field(max_length=128)


class ProductionBoundary:
    """The ASGI peer must remain the socket peer: start Uvicorn --no-proxy-headers."""

    def __init__(self, app, config, limiter):
        self.app, self.config, self.limiter = app, config, limiter

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {}
        duplicate = False
        for key, value in scope["headers"]:
            if key in headers and key in (
                b"host",
                b"x-forwarded-proto",
                b"x-forwarded-for",
                b"origin",
            ):
                duplicate = True
            headers[key] = value
        try:
            peer = ip_address(scope["client"][0])
            trusted = any(peer in network for network in self.config.trusted_proxies)
            forwarded_ip = headers.get(b"x-forwarded-for", b"").decode("ascii")
            address = str(ip_address(forwarded_ip))
            host = self.config.public_origin.removeprefix("https://").encode()
            if (
                duplicate
                or not trusted
                or headers.get(b"x-forwarded-proto") != b"https"
                or headers.get(b"host") != host
                or b"forwarded" in headers
            ):
                raise ValueError()
        except (ValueError, KeyError, TypeError, UnicodeError):
            return await JSONResponse({"detail": "Trusted HTTPS proxy required"}, 400)(
                scope, receive, send
            )
        scope.setdefault("state", {})["verified_client_ip"] = address

        started = False

        async def secure_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                message.setdefault("headers", []).extend(
                    [
                        (b"strict-transport-security", b"max-age=31536000"),
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"no-referrer"),
                        (
                            b"content-security-policy",
                            WEB_CSP if scope["path"] in WEB_FILES else DEFAULT_CSP,
                        ),
                        (b"cache-control", b"no-store"),
                    ]
                )
            await send(message)

        # Throttle before parsing credentials, including malformed and oversized auth requests.
        if scope["path"].startswith("/api/auth/"):
            try:
                length = int(headers.get(b"content-length", b"0"))
                if length > 4096 or length < 0:
                    return await JSONResponse(
                        {"detail": "Authentication request too large"}, 413
                    )(scope, receive, secure_send)
                await run_in_threadpool(self.limiter.check, "auth-ip", address, 120, 60)
            except RateLimited:
                return await JSONResponse({"detail": "Try again later"}, 429)(
                    scope, receive, secure_send
                )
            except (StorageUnavailable, ValueError):
                return await JSONResponse(
                    {"detail": "Authentication unavailable"}, 503
                )(scope, receive, secure_send)
            size = 0

            async def bounded_receive():
                nonlocal size
                message = await receive()
                size += len(message.get("body", b""))
                if size > 4096:
                    raise HTTPException(413, "Authentication request too large")
                return message

            receive_request = bounded_receive
        else:
            receive_request = receive
        try:
            return await self.app(scope, receive_request, secure_send)
        except Exception:
            # Starlette may re-raise after its error response; never leak its traceback to Uvicorn.
            logger.error("request_failed")
            if not started:
                return await JSONResponse({"detail": "Service unavailable"}, 503)(
                    scope, receive, secure_send
                )


def build_app(config, auth, database, limiter, fence):
    """Injectable assembly permits complete offline boundary tests."""
    app = create_authenticated_app(
        auth,
        database,
        expected_environment_id=config.environment_id,
        write_fence=fence,
        advertise_payment_context=True,
    )
    current = verified_principal_dependency(auth)
    routes = APIRouter(prefix="/api/auth")

    def invoke(operation, *args):
        try:
            result = retry_auth(operation, *args)
            logger.info("authentication_operation_succeeded")
            return result
        except (InvalidCredentials, InvalidInput):
            logger.info("authentication_operation_rejected")
            raise HTTPException(401, "Invalid credentials") from None
        except SessionLimit:
            raise HTTPException(409, "Active session limit reached") from None
        except (StorageUnavailable, HashCapacityExceeded):
            logger.warning("authentication_infrastructure_unavailable")
            raise HTTPException(503, "Authentication unavailable") from None
        except AuthError:
            raise HTTPException(400, "Account operation unavailable") from None

    def check(category, subject, limit, seconds):
        try:
            limiter.check(category, subject, limit, seconds)
        except RateLimited:
            raise HTTPException(
                429, "Try again later", headers={"Retry-After": str(seconds)}
            ) from None
        except StorageUnavailable:
            raise HTTPException(503, "Authentication unavailable") from None

    def tokens_response(tokens):
        principal = invoke(auth.authenticate, tokens.access)
        return {
            **asdict(tokens),
            "user_id": principal.user_id,
            "environment_id": config.environment_id,
        }

    @routes.post("/login")
    def login(body: Credentials, request: Request):
        check("login-ip", request.state.verified_client_ip, 30, 900)
        try:
            email = normalize_email(body.email)
        except InvalidInput:
            raise HTTPException(401, "Invalid credentials") from None
        check("login-account", email, 5, 900)
        return tokens_response(invoke(auth.login, email, body.password))

    @routes.post("/account/delete-web", status_code=204)
    def delete_web(body: WebDeletionInput, request: Request):
        if (
            request.headers.get("origin") != config.public_origin
            or request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            != "application/json"
            or not body.confirmed
        ):
            raise HTTPException(403, "Account deletion request rejected")
        check("login-ip", request.state.verified_client_ip, 30, 900)
        try:
            email = normalize_email(body.email)
        except InvalidInput:
            raise HTTPException(401, "Invalid credentials") from None
        check("login-account", email, 5, 900)
        invoke(auth.delete_account_with_password, email, body.password)
        return Response(status_code=204)

    @routes.post("/refresh")
    def refresh(body: RefreshInput):
        # Token is HMACed inside the shared limiter and never persisted as plaintext.
        check("refresh-token", body.refresh, 60, 60)
        return tokens_response(invoke(auth.rotate, body.refresh))

    @routes.get("/session")
    def session(principal=Depends(current)):
        return {"user_id": principal.user_id, "environment_id": config.environment_id}

    @routes.post("/account/delete", status_code=204)
    def delete_account(body: DeleteAccountInput, principal=Depends(current)):
        check("account-deletion", principal.user_id, 5, 900)
        invoke(auth.delete_account, principal, body.password)
        return Response(status_code=204, headers={"Cache-Control": "no-store"})

    @routes.post("/logout", status_code=204)
    def logout(body: RefreshInput):
        invoke(auth.logout_refresh, body.refresh)
        return Response(status_code=204)

    @routes.post("/invite/accept", status_code=204)
    def accept(body: InvitationInput):
        check("invitation-token", body.invitation, 5, 900)
        invoke(auth.accept_invitation, body.invitation, body.password)
        return Response(status_code=204)

    @routes.post("/recovery/confirm", status_code=204)
    def recover(body: ChallengeInput):
        check("recovery-token", body.token, 5, 900)
        invoke(auth.reset_password, body.token, body.password)
        return Response(status_code=204)

    def public_web_file(request: Request):
        return FileResponse(WEB_DIRECTORY / WEB_FILES[request.url.path])

    for path in WEB_FILES:
        app.add_api_route(
            path, public_web_file, methods=["GET"], include_in_schema=False
        )

    existing = app.router.routes[:]
    app.router.routes.clear()
    app.include_router(routes)
    app.router.routes.extend(existing)

    @app.exception_handler(RequestValidationError)
    async def redact_validation(request, error):
        return JSONResponse({"detail": "Invalid request"}, status_code=422)

    @app.exception_handler(Exception)
    async def redact_unhandled(request, error):
        logger.error("request_failed")
        return JSONResponse(
            {"detail": "Service unavailable"},
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "MoneyFlow-Environment-ID",
            "MoneyFlow-User-ID",
        ],
    )
    app.add_middleware(ProductionBoundary, config=config, limiter=limiter)
    return app


def create_app():
    config = ProductionConfig.load(os.environ)
    config.verify_private_network()
    sync = motor = None
    try:
        sync = MongoClient(config.mongo_uri, **config.mongo_options())
        database = verify_database(sync, config)
        motor = AsyncIOMotorClient(config.mongo_uri, **config.mongo_options())
        auth = AuthService(Store(database), SMTPDelivery(config), lambda _: False)
        app = build_app(
            config,
            auth,
            motor[config.database],
            MongoRateLimiter(database, config.rate_secret),
            Fence(motor[config.database]),
        )
    except Exception:
        if sync is not None:
            sync.close()
        if motor is not None:
            motor.close()
        raise RuntimeError("Production startup validation failed") from None

    @asynccontextmanager
    async def lifespan(_):
        try:
            yield
        finally:
            motor.close()
            sync.close()

    app.router.lifespan_context = lifespan
    return app
