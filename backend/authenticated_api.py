"""Explicitly composed R3 API. Never mount the legacy router here."""
from contextlib import AbstractAsyncContextManager
from datetime import datetime, timezone
from typing import Annotated, Literal, Protocol
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Header, Query, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import PyMongoError

from backend.account_operations import AccountCreate, delete_owned_account, recompute_balance
from backend.transaction_history import read_page
from backend.movement_operations import TransactionCreate, edit_payload, validate_movement, versioned_movement_update
from backend.movement_receipts import apply_movement_once
from backend.reference_integrity import check_movement_references, coordinate
from backend.auth_core import AuthService, InvalidCredentials, Principal, StorageUnavailable
from backend.financial_context import get_financial_context, verify_payment_context
from backend import catalog_operations, debt_operations
from backend.obligation_operations import (
    BillIn, BillPayIn, ObligationOperations, RecurringPayRecordCreate, RecurringPaymentCreate,
)
from backend.shared_obligations import reconcile_payment_intent, shared_read_route
from backend.financial_summary import summarize
from backend.planning_operations import (
    BudgetCreate, GoalContributionCreate, PlanningOperations, SavingGoalCreate,
)
from backend.shared_obligations import public_financial_document


class WriteFence(Protocol):
    def __call__(self, principal: Principal) -> AbstractAsyncContextManager:
        """Recheck access and serialize with revocation; yield the DB session."""
        ...


class OwnedAccountInput(AccountCreate):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class OwnedMovementInput(TransactionCreate):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class OwnedLinkedPaymentEdit(OwnedMovementInput):
    settlement_source: Literal["account", "external"] | None = None


class OwnedMovementEdit(OwnedLinkedPaymentEdit):
    expected_revision: Annotated[int, Field(strict=True, ge=0)] | None = None


MovementKey = Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=128)]


class OwnedDebtInput(debt_operations.DebtCreate):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    direction: Literal["i_owe", "they_owe"]
    payment_frequency: Literal["weekly", "biweekly", "monthly", "none"] = "monthly"


class OwnedPaymentInput(debt_operations.DebtPaymentCreate):
    model_config = ConfigDict(extra="forbid")


ExpectedEnvironment = Annotated[str | None, Header(alias="MoneyFlow-Environment-ID", min_length=1, max_length=36)]
ExpectedUser = Annotated[str | None, Header(alias="MoneyFlow-User-ID", min_length=1, max_length=128)]


class OwnedBillInput(BillIn):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class OwnedBillPayment(BillPayIn):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class OwnedRecurringInput(RecurringPaymentCreate):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class OwnedRecurringPayment(RecurringPayRecordCreate):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class OwnedBudgetInput(BudgetCreate):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class OwnedGoalInput(SavingGoalCreate):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class OwnedContributionInput(GoalContributionCreate):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class OwnedProfileInput(catalog_operations.UserUpdate):
    model_config = ConfigDict(extra="forbid")


class OwnedCategoryInput(catalog_operations.CategoryCreate):
    model_config = ConfigDict(extra="forbid")
    type: Literal["income", "expense"] = "expense"


class OwnedTemplateInput(catalog_operations.RecurringCreate):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    frequency: Literal["weekly", "biweekly", "monthly", "custom"] = "monthly"


class NoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str = Field(max_length=80)
    content: str = Field(max_length=5000)
    pinned: bool = False
    color: str = Field(max_length=64)
    icon: str | None = Field(default=None, max_length=100)
    categories: list[Annotated[str, Field(max_length=200)]] | None = Field(
        default=None, max_length=50
    )
    listMode: Literal["plain", "check", "ordered"] | None = None
    palette: Literal["green", "cream", "yellow", "blue", "lavender", "coral"] | None = None


def unauthorized() -> HTTPException:
    return HTTPException(401, "Invalid credentials", headers={"WWW-Authenticate": "Bearer"})


def verified_principal_dependency(auth: AuthService):
    bearer = HTTPBearer(auto_error=False)

    def verified_principal(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> Principal:
        if credentials is None:
            raise unauthorized()
        try:
            principal = auth.authenticate(credentials.credentials)
        except InvalidCredentials:
            raise unauthorized() from None
        except StorageUnavailable:
            raise HTTPException(503, "Authentication unavailable") from None
        try:
            owner = UUID(principal.user_id)
            if owner.version != 4 or str(owner) != principal.user_id:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(403, "Identity is not eligible") from None
        return principal

    return verified_principal


def create_authenticated_app(
    auth: AuthService, database, *, expected_environment_id: str,
    write_fence: WriteFence | None = None,
    advertise_payment_context: bool = False,
) -> FastAPI:
    """Compose a detached API using explicitly provided storage and auth."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    current = verified_principal_dependency(auth)
    user = Annotated[Principal, Depends(current)]
    api = APIRouter(prefix="/api", dependencies=[Depends(current)])

    async def find_owned(collection, principal: Principal, resource_id: str, session=None):
        try:
            record = await collection.find_one(
                {"id": resource_id, "user_id": principal.user_id}, {"_id": 0}, session=session
            )
        except PyMongoError:
            raise HTTPException(503, "Resource storage unavailable") from None
        if record is None:
            raise HTTPException(404, "Not found")
        return record

    async def list_owned(collection, principal: Principal, limit: int, sort=None):
        try:
            cursor = collection.find({"user_id": principal.user_id}, {"_id": 0})
            if sort:
                cursor = cursor.sort(sort)
            return await cursor.to_list(limit)
        except PyMongoError:
            raise HTTPException(503, "Resource storage unavailable") from None

    @api.get("/financial-context")
    async def financial_context(principal: user):
        context = await get_financial_context(database, expected_environment_id, principal.user_id)
        return {**context, "mode": "authenticated_user", "capabilities": {
            key: value if advertise_payment_context else False
            for key, value in context["capabilities"].items()
        }}

    @api.get("/accounts")
    async def accounts(principal: user):
        return public_financial_document(await list_owned(database.accounts, principal, 500))

    @api.get("/categories")
    async def categories(principal: user):
        return public_financial_document(await list_owned(database.categories, principal, 500))

    @api.get("/transactions")
    async def transactions(principal: user, limit: Annotated[int, Query(ge=1, le=500)] = 500):
        return public_financial_document(await list_owned(
            database.transactions, principal, limit, [("date", -1)]
        ))

    @api.get("/transactions/page")
    async def transaction_page(
        principal: user,
        account_id: Annotated[str | None, Query(min_length=1, max_length=256)] = None,
        category_id: Annotated[str | None, Query(min_length=1, max_length=256)] = None,
        types: Annotated[list[str] | None, Query(alias="type")] = None,
        start: str | None = None, end: str | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        order: Literal["recent", "oldest", "high", "low"] = "recent",
        cursor: Annotated[str | None, Query(min_length=1, max_length=2048)] = None,
    ):
        if account_id is not None:
            await find_owned(database.accounts, principal, account_id)
        if category_id is not None:
            await find_owned(database.categories, principal, category_id)
        return await read_page(
            database, principal.user_id, {"_id": 0}, public_financial_document,
            context=["authenticated_user", expected_environment_id],
            account_id=account_id, category_id=category_id, types=types,
            start=start, end=end, limit=limit, order=order, cursor=cursor,
        )

    @api.get("/transactions/{tid}")
    async def transaction(tid: str, principal: user):
        record = await find_owned(database.transactions, principal, tid)
        return public_financial_document({"revision": 0, **record})

    @api.get("/debts")
    async def debts(principal: user):
        return public_financial_document(await list_owned(database.debts, principal, 500))

    @api.get("/debts/{did}")
    async def debt(did: str, principal: user):
        return public_financial_document(await find_owned(database.debts, principal, did))

    def note_public(record):
        return {key: value for key, value in record.items()
                if key in NoteInput.model_fields or key in {"id", "createdAt", "updatedAt"}}

    @api.get("/notes")
    async def notes(principal: user):
        records = await list_owned(
            database.notes, principal, 100, [("pinned", -1), ("updatedAt", -1), ("id", 1)]
        )
        return [note_public(record) for record in records]

    @api.get("/notes/{note_id}")
    async def note(note_id: UUID, principal: user):
        return note_public(await find_owned(database.notes, principal, str(note_id)))

    async def fenced_write(principal: Principal, operation):
        if write_fence is None:
            raise HTTPException(503, "Resource writes unavailable")
        try:
            async with write_fence(principal) as session:
                if session is None:
                    raise StorageUnavailable("Transaction session unavailable")
                result = await operation(session)
            return result
        except InvalidCredentials:
            raise unauthorized() from None
        except (PyMongoError, StorageUnavailable):
            raise HTTPException(503, "Resource storage unavailable") from None

    @api.post("/accounts")
    async def create_account(data: OwnedAccountInput, principal: user):
        record = {
            **data.model_dump(), "id": str(uuid4()), "user_id": principal.user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "current_balance": data.initial_balance,
        }

        async def operation(session):
            await database.accounts.insert_one(record, session=session)
            return public_financial_document(record)

        return await fenced_write(principal, operation)

    @api.put("/accounts/{account_id}")
    async def update_account(account_id: str, data: OwnedAccountInput, principal: user):
        async def operation(session):
            await find_owned(database.accounts, principal, account_id, session)
            await database.accounts.update_one(
                {"id": account_id, "user_id": principal.user_id},
                {"$set": data.model_dump()}, session=session,
            )
            await recompute_balance(database, principal.user_id, account_id, {"_id": 0}, session)
            return public_financial_document(
                await find_owned(database.accounts, principal, account_id, session)
            )

        return await fenced_write(principal, operation)

    @api.delete("/accounts/{account_id}")
    async def delete_account(account_id: str, principal: user):
        async def operation(session):
            await find_owned(database.accounts, principal, account_id, session)
            return await delete_owned_account(
                database, principal.user_id, account_id, {"_id": 0}, session
            )

        return await fenced_write(principal, operation)

    async def owned_movement_references(payload, principal, session=None):
        references = {}
        for field, collection in (
            ("account_id", database.accounts), ("to_account_id", database.accounts),
            ("category_id", database.categories),
        ):
            if payload.get(field) is not None:
                references[field] = await find_owned(collection, principal, payload[field], session)
        return references

    @api.get("/transactions/{tid}/references")
    async def movement_references(tid: str, principal: user):
        movement = await find_owned(database.transactions, principal, tid)
        return public_financial_document(await owned_movement_references(movement, principal))

    async def movement_write(principal, key, operation, payload, execute):
        async def transaction(session):
            if getattr(session, "in_transaction", False) is not True:
                raise StorageUnavailable("Movement transaction unavailable")
            return await apply_movement_once(
                database, principal.user_id, key, operation, payload, session, execute
            )

        return await fenced_write(principal, transaction)

    async def ordinary_movement(tid, principal, session):
        record = await find_owned(database.transactions, principal, tid, session)
        if record.get("type") not in {"income", "expense", "transfer"} or any(
            record.get(field) for field in (
                "debt_id", "debt_payment_id", "goal_id", "goal_contribution_id",
                "bill_id", "bill_payment_id", "recurring_payment_id", "recurring_record_id",
            )
        ):
            raise HTTPException(409, "Use the corresponding linked financial operation")
        await owned_movement_references(record, principal, session)
        await check_movement_references(database, principal.user_id, record, session)
        return record

    async def refresh_movement_balances(principal, session, *records):
        accounts = {record.get(field) for record in records
                    for field in ("account_id", "to_account_id")}
        for account_id in sorted(accounts - {None}):
            await recompute_balance(database, principal.user_id, account_id, {"_id": 0}, session)

    @api.post("/transactions")
    async def create_movement(data: OwnedMovementInput, principal: user, key: MovementKey = None):
        if data.debt_id or data.type in ("debt_payment", "loan_given", "loan_received"):
            raise HTTPException(409, "Use the corresponding debt operation")
        payload = data.model_dump()
        now = datetime.now(timezone.utc).isoformat()
        payload["date"] = payload["date"] or now
        movement_id = str(uuid4())
        record = {
            **payload, "id": movement_id, "user_id": principal.user_id,
            "created_at": now, "debt_payment_id": None, "revision": 0,
        }

        async def operation(session):
            await owned_movement_references(payload, principal, session)
            await validate_movement(
                database, principal.user_id, {"_id": 0}, payload, session=session
            )
            await database.transactions.insert_one(dict(record, _id=movement_id), session=session)
            await refresh_movement_balances(principal, session, record)
            return record

        return await movement_write(principal, key, "create", data.model_dump(), operation)

    @api.put("/transactions/{tid}")
    async def update_movement(tid: str, data: OwnedMovementEdit, principal: user,
                              key: MovementKey = None):
        async def operation(session):
            record = await find_owned(database.transactions, principal, tid, session)
            if record.get("debt_payment_id"):
                await owned_movement_references(record, principal, session)
                return public_financial_document(await debt_operations.edit_payment(
                    database, principal.user_id, tid,
                    OwnedLinkedPaymentEdit(**data.model_dump(exclude_unset=True, exclude={"expected_revision"})),
                    session,
                ))
            if data.debt_id or data.type in {"debt_payment", "loan_given", "loan_received"}:
                raise HTTPException(409, "Use the corresponding debt operation")
            expected = data.expected_revision
            if expected is None:
                raise HTTPException(422, "Movement revision required")
            if record.get("revision", 0) != expected:
                raise HTTPException(409, "Movement revision conflict")
            old = await ordinary_movement(tid, principal, session)
            payload = edit_payload(
                data, old, datetime.now(timezone.utc).isoformat(), preserve_missing_date=True
            )
            payload.pop("expected_revision")
            await owned_movement_references(payload, principal, session)
            await validate_movement(
                database, principal.user_id, {"_id": 0}, payload, old, session=session
            )
            payload.pop("settlement_source", None)
            selector = {"id": tid, "user_id": principal.user_id, "revision": expected}
            if "revision" not in old:
                selector["revision"] = {"$exists": False}
            result = await database.transactions.update_one(
                selector, versioned_movement_update({"$set": payload}), session=session,
            )
            if result.matched_count != 1:
                raise HTTPException(409, "Movement revision conflict")
            await refresh_movement_balances(principal, session, old, payload)
            return public_financial_document({**old, **payload, "revision": expected + 1})

        return await movement_write(
            principal, key, "update", [tid, data.model_dump(exclude_unset=True)], operation
        )

    @api.delete("/transactions/{tid}")
    async def delete_movement(tid: str, principal: user, key: MovementKey = None):
        async def operation(session):
            record = await find_owned(database.transactions, principal, tid, session)
            if record.get("debt_payment_id"):
                payment = await find_owned(database.debt_payments, principal, record["debt_payment_id"], session)
                if payment.get("transaction_id") != tid or payment.get("deleted"):
                    raise HTTPException(409, "Payment requires reconciliation")
                return await cancel_owned_payment(payment, principal, session)
            old = await ordinary_movement(tid, principal, session)
            scope = {"user_id": principal.user_id}
            if await database.recurring_templates.find_one(
                {**scope, "source_transaction_id": tid}, {"_id": 0}, session=session
            ):
                raise HTTPException(409, "Movement is the source of a recurring template")
            await database.transactions.delete_one({**scope, "id": tid}, session=session)
            await refresh_movement_balances(principal, session, old)
            return {"ok": True}

        return await movement_write(principal, key, "delete", tid, operation)

    @api.post("/debts")
    async def create_debt(data: OwnedDebtInput, principal: user):
        async def operation(session):
            await owned_movement_references(data.model_dump(), principal, session)
            return await debt_operations.create_debt(database, principal.user_id, data, session)

        return await movement_write(principal, None, "debt-create", None, operation)

    @api.put("/debts/{did}")
    async def update_debt(did: str, data: OwnedDebtInput, principal: user):
        async def operation(session):
            old = await find_owned(database.debts, principal, did, session)
            payload = data.model_dump()
            for field in ("account_id", "category_id"):
                if field not in data.model_fields_set:
                    payload[field] = old.get(field)
            await owned_movement_references(payload, principal, session)
            return public_financial_document(await debt_operations.update_debt(
                database, principal.user_id, did, data, session
            ))

        return await movement_write(principal, None, "debt-update", None, operation)

    @api.delete("/debts/{did}")
    async def delete_debt(did: str, principal: user):
        async def operation(session):
            await find_owned(database.debts, principal, did, session)
            return await debt_operations.delete_debt(database, principal.user_id, did, session)

        return await movement_write(principal, None, "debt-delete", None, operation)

    @api.get("/debts/{did}/payments")
    async def debt_payments(did: str, principal: user):
        await find_owned(database.debts, principal, did)
        try:
            rows = await database.debt_payments.find({
                "debt_id": did, "user_id": principal.user_id, "deleted": {"$ne": True},
            }, {"_id": 0}).sort([("date", -1)]).to_list(500)
        except PyMongoError:
            raise HTTPException(503, "Resource storage unavailable") from None
        return [debt_operations.DebtPayment(**row).model_dump() for row in rows]

    async def check_payment_context(principal, environment, owner, session):
        if (environment is None) != (owner is None):
            raise HTTPException(422, "Send both context headers or neither")
        if environment is not None:
            await verify_payment_context(
                database, expected_environment_id, principal.user_id, environment, owner, session
            )

    @api.post("/debt-payments")
    async def create_debt_payment(data: OwnedPaymentInput, principal: user, key: MovementKey = None,
                                  environment: ExpectedEnvironment = None, owner: ExpectedUser = None):
        async def operation(session):
            await check_payment_context(principal, environment, owner, session)
            return await debt_operations.create_payment(database, principal.user_id, data, key, session)

        # The payment itself is the receipt; cancellation retains its tombstone.
        return await movement_write(principal, None, "payment-create", None, operation)

    @api.post("/debt-payments/reconcile")
    async def reconcile_debt_payment(data: OwnedPaymentInput, principal: user, key: MovementKey,
                                     environment: ExpectedEnvironment = None, owner: ExpectedUser = None):
        if key is None:
            raise HTTPException(422, "Idempotency-Key is required")

        async def operation(session):
            await check_payment_context(principal, environment, owner, session)
            return await debt_operations.reconcile_payment(database, principal.user_id, data, key, session)

        return await movement_write(principal, None, "payment-reconcile", None, operation)

    async def cancel_owned_payment(payment, principal, session):
        if not payment.get("deleted"):
            movement = await debt_operations.payment_movement(database, principal.user_id, payment, session)
            await owned_movement_references(movement, principal, session)
            await check_movement_references(
                database, principal.user_id, movement, session, debt_payment_id=payment["id"]
            )
        return await debt_operations.remove_payment(database, principal.user_id, payment["id"], session)

    @api.delete("/debt-payments/{pid}")
    async def delete_debt_payment(pid: str, principal: user, key: MovementKey = None):
        async def operation(session):
            payment = await find_owned(database.debt_payments, principal, pid, session)
            return await cancel_owned_payment(payment, principal, session)

        return await movement_write(principal, key, "payment-delete", pid, operation)

    @api.get("/summary")
    async def summary(principal: user):
        return await movement_write(
            principal, None, "summary", None,
            lambda session: summarize(database, principal.user_id, session),
        )

    def obligations(principal):
        return ObligationOperations(database, principal.user_id)

    async def read_obligation(principal, method, *args):
        read = shared_read_route(
            lambda: database, lambda: database.client,
            lambda: expected_environment_id, lambda: principal.user_id,
        )(getattr(obligations(principal), method))
        return await read(*args)

    async def write_obligation(principal, method, *args, target=None, data=None,
                               environment=None, owner=None):
        async def operation(session):
            await check_payment_context(principal, environment, owner, session)
            old = None
            if target:
                old = await find_owned(getattr(database, target[0]), principal, target[1], session)
            if data is not None:
                for field, name in (
                    ("account_id", "accounts"), ("category_id", "categories"),
                    ("recurring_payment_id", "recurring_payments"), ("transaction_id", "transactions"),
                ):
                    value = getattr(data, field, None)
                    if old and field not in data.model_fields_set and hasattr(data, field):
                        value = old.get(field)
                    if value:
                        await find_owned(getattr(database, name), principal, value, session)
            result = await getattr(obligations(principal), method)(*args, session=session)
            return public_financial_document(result)

        return await movement_write(principal, None, method, None, operation)

    @api.get("/bills")
    async def list_bills(principal: user, status: str = "all", tz_offset: int = 0):
        return await read_obligation(principal, "list_bills", status, tz_offset)

    @api.get("/bills/summary")
    async def bills_summary(principal: user, tz_offset: int = 0, year: int | None = None, month: int | None = None):
        return await read_obligation(principal, "bills_summary", tz_offset, year, month)

    @api.get("/bills/{bid}")
    async def get_bill(principal: user, bid: str, tz_offset: int = 0):
        return await read_obligation(principal, "get_bill", bid, tz_offset)

    @api.get("/recurring-payments")
    async def list_recurring_payments(principal: user, tz_offset: int = 0):
        return await read_obligation(principal, "list_recurring_payments", tz_offset)

    @api.get("/recurring-payments/overview")
    async def recurring_overview(principal: user, year: int | None = None, month: int | None = None, tz_offset: int = 0):
        return await read_obligation(principal, "recurring_overview", year, month, tz_offset)

    @api.get("/recurring-payments/{rid}")
    async def get_recurring_payment(principal: user, rid: str, tz_offset: int = 0):
        return await read_obligation(principal, "get_recurring_payment", rid, tz_offset)

    @api.get("/recurring-payments/{rid}/occurrences")
    async def recurring_occurrences(principal: user, rid: str, offset: int = 0, limit: int = 20, tz_offset: int = 0):
        return await read_obligation(principal, "recurring_occurrences", rid, offset, limit, tz_offset)

    @api.get("/recurring-payments/{rid}/link-candidates")
    async def recurring_link_candidates(principal: user, rid: str, due_date: str):
        return await read_obligation(principal, "recurring_link_candidates", rid, due_date)

    @api.post("/bills")
    async def create_bill(principal: user, data: OwnedBillInput, key: MovementKey = None):
        return await write_obligation(
            principal, "create_bill", data, key, data=data,
        )

    @api.put("/bills/{bid}")
    async def update_bill(principal: user, bid: str, data: OwnedBillInput):
        return await write_obligation(
            principal, "update_bill", bid, data, target=("bills", bid), data=data,
        )

    @api.delete("/bills/{bid}")
    async def delete_bill(principal: user, bid: str):
        return await write_obligation(
            principal, "delete_bill", bid, target=("bills", bid),
        )

    @api.post("/bills/{bid}/payments")
    async def pay_bill(principal: user, bid: str, data: OwnedBillPayment, key: MovementKey = None, environment: ExpectedEnvironment = None, owner: ExpectedUser = None):
        return await write_obligation(
            principal, "pay_bill", bid, data, key, target=("bills", bid), data=data, environment=environment, owner=owner,
        )

    @api.delete("/bills/payments/{pid}")
    async def delete_bill_payment(principal: user, pid: str, environment: ExpectedEnvironment = None, owner: ExpectedUser = None):
        return await write_obligation(
            principal, "delete_bill_payment", pid, target=("bill_payments", pid), environment=environment, owner=owner,
        )

    @api.post("/recurring-payments")
    async def create_recurring_payment(principal: user, data: OwnedRecurringInput, key: MovementKey = None):
        return await write_obligation(
            principal, "create_recurring_payment", data, key, data=data,
        )

    @api.put("/recurring-payments/{rid}")
    async def update_recurring_payment(principal: user, rid: str, data: OwnedRecurringInput):
        return await write_obligation(
            principal, "update_recurring_payment", rid, data, target=("recurring_payments", rid), data=data,
        )

    @api.delete("/recurring-payments/{rid}")
    async def delete_recurring_payment(principal: user, rid: str):
        return await write_obligation(
            principal, "delete_recurring_payment", rid, target=("recurring_payments", rid),
        )

    @api.post("/recurring-payments/{rid}/payments")
    async def create_recurring_record(principal: user, rid: str, data: OwnedRecurringPayment, key: MovementKey = None, environment: ExpectedEnvironment = None, owner: ExpectedUser = None):
        return await write_obligation(
            principal, "create_recurring_record", rid, data, key, target=("recurring_payments", rid), data=data, environment=environment, owner=owner,
        )

    @api.delete("/recurring-payments/payments/{pid}")
    async def delete_recurring_record(principal: user, pid: str, environment: ExpectedEnvironment = None, owner: ExpectedUser = None):
        return await write_obligation(
            principal, "delete_recurring_record", pid, target=("recurring_payment_records", pid), environment=environment, owner=owner,
        )

    @api.post("/recurring-payments/{rid}/pause")
    async def pause_recurring_payment(principal: user, rid: str):
        return await write_obligation(
            principal, "_rp_set_state", rid, "pause", target=("recurring_payments", rid),
        )

    @api.post("/recurring-payments/{rid}/resume")
    async def resume_recurring_payment(principal: user, rid: str):
        return await write_obligation(
            principal, "_rp_set_state", rid, "resume", target=("recurring_payments", rid),
        )

    @api.post("/recurring-payments/{rid}/end")
    async def end_recurring_payment(principal: user, rid: str):
        return await write_obligation(
            principal, "_rp_set_state", rid, "end", target=("recurring_payments", rid),
        )

    async def reconcile_obligation(principal, origin, parent_id, data, key, environment, owner):
        if key is None or environment is None or owner is None:
            raise HTTPException(422, "Idempotency-Key and financial context are required")

        async def operation(session):
            await check_payment_context(principal, environment, owner, session)
            # The owner-scoped receipt can outlive its parent after deletion.
            return await reconcile_payment_intent(
                database, origin=origin, parent_id=parent_id, key=key,
                payload=data.model_dump(), expected_environment_id=expected_environment_id,
                effective_user=principal.user_id, session=session,
            )

        return await movement_write(principal, None, "obligation-reconcile", None, operation)

    @api.post("/bills/{bid}/payments/reconcile")
    async def reconcile_bill(principal: user, bid: str, data: OwnedBillPayment, key: MovementKey,
                             environment: ExpectedEnvironment = None, owner: ExpectedUser = None):
        return await reconcile_obligation(principal, "bill", bid, data, key, environment, owner)

    @api.post("/recurring-payments/{rid}/payments/reconcile")
    async def reconcile_recurring(principal: user, rid: str, data: OwnedRecurringPayment,
                                  key: MovementKey, environment: ExpectedEnvironment = None,
                                  owner: ExpectedUser = None):
        return await reconcile_obligation(principal, "recurring", rid, data, key, environment, owner)

    async def read_planning(principal, method, *args, calendar_read=False):
        read = getattr(PlanningOperations(database, principal.user_id), method)
        if calendar_read:
            read = shared_read_route(
                lambda: database, lambda: database.client,
                lambda: expected_environment_id, lambda: principal.user_id,
            )(read)
        try:
            return public_financial_document(await read(*args))
        except PyMongoError:
            raise HTTPException(503, "Resource storage unavailable") from None

    async def write_planning(principal, method, *args, target=None, data=None):
        async def operation(session):
            old = None
            if target:
                old = await find_owned(getattr(database, target[0]), principal, target[1], session)
            if data is not None:
                for field, collection in (("account_id", database.accounts),
                                          ("category_id", database.categories)):
                    value = getattr(data, field, None)
                    if old and field not in data.model_fields_set and hasattr(data, field):
                        value = old.get(field)
                    if value:
                        await find_owned(collection, principal, value, session)
            if method == "create_goal_contribution" and data.real_movement and old.get("account_id"):
                await find_owned(database.accounts, principal, old["account_id"], session)
            service = PlanningOperations(database, principal.user_id)
            return public_financial_document(await getattr(service, method)(*args, session=session))

        return await movement_write(principal, None, method, None, operation)

    @api.get("/budgets")
    async def list_budgets(principal: user):
        return await read_planning(principal, "list_budgets")

    @api.get("/budgets/overview")
    async def budgets_overview(principal: user, year: int | None = None, month: int | None = None, tz_offset: int = 0):
        return await read_planning(principal, "budgets_overview", year, month, tz_offset)

    @api.get("/budgets/{bid}/detail")
    async def budget_detail(principal: user, bid: str, year: int | None = None, month: int | None = None, tz_offset: int = 0):
        return await read_planning(principal, "budget_detail", bid, year, month, tz_offset)

    @api.get("/goals")
    async def list_goals(principal: user):
        return await read_planning(principal, "list_goals")

    @api.get("/goals/overview")
    async def goals_overview(principal: user):
        return await read_planning(principal, "goals_overview")

    @api.get("/goals/{gid}")
    async def get_goal(principal: user, gid: str, limit: int = 20):
        return await read_planning(principal, "get_goal", gid, limit)

    @api.get("/goals/{gid}/contributions")
    async def list_goal_contributions(principal: user, gid: str, limit: int = 20, offset: int = 0):
        return await read_planning(principal, "list_goal_contributions", gid, limit, offset)

    @api.get("/calendar/events")
    async def calendar_events(principal: user, start: str, end: str, tz_offset: int = 0, types: str | None = None):
        return await read_planning(principal, "calendar_events", start, end, tz_offset, types, calendar_read=True)

    @api.get("/calendar/summary")
    async def calendar_summary(principal: user, year: int | None = None, month: int | None = None, tz_offset: int = 0, types: str | None = None):
        return await read_planning(principal, "calendar_summary", year, month, tz_offset, types, calendar_read=True)

    @api.get("/calendar/upcoming")
    async def calendar_upcoming(principal: user, tz_offset: int = 0, limit: int = 5, offset: int = 0, days: int = 120, types: str | None = None):
        return await read_planning(principal, "calendar_upcoming", tz_offset, limit, offset, days, types, calendar_read=True)

    @api.post("/budgets")
    async def create_budget(principal: user, data: OwnedBudgetInput, key: MovementKey = None):
        return await write_planning(principal, "create_budget", data, key, data=data)

    @api.put("/budgets/{bid}")
    async def update_budget(principal: user, bid: str, data: OwnedBudgetInput):
        return await write_planning(principal, "update_budget", bid, data, target=("budgets", bid), data=data)

    @api.delete("/budgets/{bid}")
    async def delete_budget(principal: user, bid: str):
        return await write_planning(principal, "delete_budget", bid, target=("budgets", bid))

    @api.post("/goals")
    async def create_goal(principal: user, data: OwnedGoalInput, key: MovementKey = None):
        return await write_planning(principal, "create_goal", data, key, data=data)

    @api.put("/goals/{gid}")
    async def update_goal(principal: user, gid: str, data: OwnedGoalInput):
        return await write_planning(principal, "update_goal", gid, data, target=("saving_goals", gid), data=data)

    @api.delete("/goals/{gid}")
    async def delete_goal(principal: user, gid: str):
        return await write_planning(principal, "delete_goal", gid, target=("saving_goals", gid))

    @api.post("/goals/{gid}/contributions")
    async def create_goal_contribution(principal: user, gid: str, data: OwnedContributionInput, key: MovementKey = None):
        return await write_planning(principal, "create_goal_contribution", gid, data, key, target=("saving_goals", gid), data=data)

    profile_fields = {"id", "name", "email", "profile_photo", "currency"}

    async def owned_profile(principal, session=None):
        try:
            record = await database.users.find_one(
                {"id": principal.user_id}, {"_id": 0, **dict.fromkeys(profile_fields, 1)},
                session=session,
            )
        except PyMongoError:
            raise HTTPException(503, "Resource storage unavailable") from None
        if record is None:
            raise HTTPException(404, "Not found")
        return {field: value for field, value in record.items() if field in profile_fields}

    @api.get("/user")
    async def get_profile(principal: user):
        return await owned_profile(principal)

    @api.put("/user")
    async def update_profile(data: OwnedProfileInput, principal: user):
        async def operation(session):
            record = await owned_profile(principal, session)
            changes = data.model_dump(exclude_none=True)
            if changes:
                await database.users.update_one(
                    {"id": principal.user_id}, {"$set": changes}, session=session
                )
            return {**record, **changes}

        return await movement_write(principal, None, "profile-update", None, operation)

    @api.post("/categories")
    async def create_category(data: OwnedCategoryInput, principal: user):
        async def operation(session):
            record = catalog_operations.Category(
                user_id=principal.user_id, **data.model_dump()
            ).model_dump()
            await catalog_operations.validate_category_parent(
                database, principal.user_id, record["id"], record.get("parent_id"), session
            )
            await coordinate(database, principal.user_id, record, session)
            await database.categories.insert_one(dict(record, _id=record["id"]), session=session)
            return public_financial_document(record)

        return await movement_write(principal, None, "category-create", None, operation)

    @api.put("/categories/{cid}")
    async def update_category(cid: str, data: OwnedCategoryInput, principal: user):
        async def operation(session):
            old = await find_owned(database.categories, principal, cid, session)
            payload = data.model_dump(exclude_unset=True)
            record = {**old, **payload}
            await catalog_operations.validate_category_parent(
                database, principal.user_id, cid, record.get("parent_id"), session
            )
            await coordinate(database, principal.user_id, record, session, old)
            await database.categories.update_one(
                {"id": cid, "user_id": principal.user_id}, {"$set": payload}, session=session
            )
            return public_financial_document(record)

        return await movement_write(principal, None, "category-update", None, operation)

    @api.delete("/categories/{cid}")
    async def delete_category(cid: str, principal: user):
        async def operation(session):
            await find_owned(database.categories, principal, cid, session)
            return await catalog_operations.delete_owned_category(
                database, principal.user_id, cid, session
            )

        return await movement_write(principal, None, "category-delete", None, operation)

    @api.post("/categories/init-defaults")
    async def init_default_categories(principal: user):
        return await movement_write(
            principal, None, "category-initialize", None,
            lambda session: catalog_operations.initialize_categories(database, principal.user_id, session),
        )

    @api.get("/recurring")
    async def list_templates(principal: user):
        return public_financial_document(await list_owned(
            database.recurring_templates, principal, 500, [("created_at", -1)]
        ))

    @api.post("/recurring")
    async def create_template(data: OwnedTemplateInput, principal: user, key: MovementKey = None):
        async def operation(session):
            await owned_movement_references(data.model_dump(), principal, session)
            if data.source_transaction_id:
                await find_owned(database.transactions, principal, data.source_transaction_id, session)
            return await catalog_operations.create_template(database, principal.user_id, data, session)

        return await movement_write(principal, key, "template-create", data.model_dump(), operation)

    @api.delete("/recurring/{rid}")
    async def delete_template(rid: str, principal: user):
        async def operation(session):
            await find_owned(database.recurring_templates, principal, rid, session)
            await database.recurring_templates.delete_one(
                {"id": rid, "user_id": principal.user_id}, session=session
            )
            return {"ok": True}

        return await movement_write(principal, None, "template-delete", None, operation)

    @api.post("/notes", status_code=201)
    async def create_note(data: NoteInput, principal: user):
        now = datetime.now(timezone.utc).isoformat()
        record = {
            **data.model_dump(), "id": str(uuid4()), "user_id": principal.user_id,
            "createdAt": now, "updatedAt": now,
        }

        async def insert(session):
            await database.notes.insert_one(record, session=session)
            return note_public(record)

        return await fenced_write(principal, insert)

    @api.put("/notes/{note_id}")
    async def update_note(note_id: UUID, data: NoteInput, principal: user):
        from pymongo import ReturnDocument

        async def update(session):
            record = await database.notes.find_one_and_update(
                {"id": str(note_id), "user_id": principal.user_id},
                {"$set": {**data.model_dump(), "updatedAt": datetime.now(timezone.utc).isoformat()}},
                return_document=ReturnDocument.AFTER, session=session,
            )
            if record is None:
                raise HTTPException(404, "Not found")
            return note_public(record)

        return await fenced_write(principal, update)

    @api.delete("/notes/{note_id}", status_code=204)
    async def delete_note(note_id: UUID, principal: user):
        async def delete(session):
            result = await database.notes.delete_one(
                {"id": str(note_id), "user_id": principal.user_id}, session=session
            )
            if result.deleted_count != 1:
                raise HTTPException(404, "Not found")
            return Response(status_code=204)

        return await fenced_write(principal, delete)

    @api.api_route("/{unavailable:path}", methods=[
        "GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS",
    ], include_in_schema=False)
    async def unavailable():
        raise HTTPException(404, "Not found")

    app.include_router(api)
    return app
