"""R4 internal identity, verified readers and transactional payment kernel.

No client, startup hook, environment loading, route or automatic migration.
Public adapters require explicit activation; administrative indexes are never installed by them.
Pass the application's existing _rp_occurrences function; do not duplicate its
calendar rules or import server.py (which would open the production client).
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, DecimalException, InvalidOperation, localcontext
import json
import hashlib
from uuid import NAMESPACE_URL, uuid5

from bson.decimal128 import Decimal128
from fastapi import HTTPException
from pymongo.errors import PyMongoError

if __package__:
    from .history_keys import strip_history_metadata
    from .financial_context import get_financial_context, validate_environment_id
    from .reference_integrity import coordinate, _same_optional_reference, check_bill_payment, check_record
else:
    from history_keys import strip_history_metadata
    from financial_context import get_financial_context, validate_environment_id
    from reference_integrity import coordinate, _same_optional_reference, check_bill_payment, check_record


VERSION = 1
LIFECYCLES = {"bound", "tracking_detached", "archived"}
FREQUENCIES = {"weekly": "weekly", "monthly": "monthly", "quarterly": "quarterly", "yearly": "annual"}
INDEXES = (
    ("shared_period_unique", (("user_id", 1), ("recurring_id", 1), ("original_due_date", 1))),
    ("shared_bill_unique", (("user_id", 1), ("bill_id", 1))),
)


def conflict(message):
    raise HTTPException(409, message)


def identifier(value):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        conflict("Identificador financiero no verificable.")
    return value


def day(value):
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError()
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        conflict("El vencimiento original no es verificable.")


def money(value, *, positive=True):
    try:
        if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal, Decimal128)):
            raise ValueError()
        result = value.to_decimal() if isinstance(value, Decimal128) else Decimal(str(value))
        if not result.is_finite() or (result <= 0 if positive else result < 0):
            raise ValueError()
        return result
    except (ValueError, InvalidOperation, TypeError):
        conflict("Importe financiero no verificable; no se normalizará el histórico.")


def _stored_money(value):
    try:
        return Decimal128(money(value))
    except DecimalException:
        conflict("El importe no puede conservarse exactamente en Decimal128.")


@dataclass(frozen=True)
class Scope:
    environment_id: str
    user_id: str
    mode: str = "single_user"

    def __post_init__(self):
        validate_environment_id(self.environment_id)
        identifier(self.user_id)
        if self.mode != "single_user":
            conflict("Modo de usuario no soportado por esta etapa.")


def identity(scope, recurring_id, due_date):
    identifier(recurring_id)
    day(due_date)
    key = json.dumps(["moneyflow:shared-obligation:v1", scope.environment_id,
                      scope.user_id, recurring_id, due_date], separators=(",", ":"))
    return str(uuid5(NAMESPACE_URL, key))


def _calendar(occurrences, recurring, first, last):
    try:
        return occurrences(recurring, first, last)
    except (KeyError, ValueError, TypeError, IndexError, OverflowError):
        conflict("La programación heredada no puede verificarse.")


def validate_document(document, scope):
    if not document:
        conflict("No existe una identidad compartida verificable.")
    try:
        if (type(document["version"]) is not int or document["version"] != VERSION
                or type(document["revision"]) is not int or document["revision"] < 0
                or document["lifecycle"] not in LIFECYCLES
                or document["environment_id"] != scope.environment_id
                or document["user_id"] != scope.user_id or document["mode"] != scope.mode):
            raise ValueError()
        identifier(document["bill_id"])
        expected = identity(scope, document["recurring_id"], document["original_due_date"])
        if document["_id"] != expected:
            raise ValueError()
        money(document["actual_amount"])
        money(document["estimated_amount"])
        created = datetime.fromisoformat(document["created_at"])
        if created.tzinfo is None or not isinstance(document["schedule_snapshot"], dict):
            raise ValueError()
        snapshot = document["schedule_snapshot"]
        day(snapshot["valid_from"])
        day(snapshot["start_date"])
        if snapshot["frequency"] not in {"daily", "weekly", "biweekly", "monthly", "bimonthly", "quarterly", "semiannual", "annual"}:
            raise ValueError()
        if snapshot.get("due_day") is not None and (type(snapshot["due_day"]) is not int or not 1 <= snapshot["due_day"] <= 31):
            raise ValueError()
        if money(snapshot["amount"]) != money(document["estimated_amount"]):
            raise ValueError()
        if type(document["variable_snapshot"]) is not bool:
            raise ValueError()
    except (KeyError, TypeError, ValueError, AttributeError):
        conflict("La identidad compartida contiene metadatos incoherentes.")
    if "bill_schedule_snapshot" in document:
        bill_schedule(document)
    return deepcopy(document)


def bill_schedule(document):
    """Original bill calendar, never inferred from the recurring estimate."""
    snapshot = document.get("bill_schedule_snapshot")
    if (not isinstance(snapshot, dict) or snapshot.get("frequency") not in {"once", *FREQUENCIES}
            or type(snapshot.get("anchor_day")) is not int or not 1 <= snapshot["anchor_day"] <= 31
            or snapshot.get("original_due_date") != document["original_due_date"]):
        conflict("Falta la programación original verificable de la factura; no se completará automáticamente.")
    day(snapshot["original_due_date"])
    identifier(snapshot.get("series_id"))  # grouping key, not a document FK
    return deepcopy(snapshot)


def resolve_documents(bill, recurring, scope, *, occurrences, existing=None, candidates=()):
    """Pure resolver. New links require an exact, unambiguous due date.

    Once persisted, the original schedule is verified instead of remapping the
    period through a mutable current schedule. Never adopts payments by amount.
    """
    if not bill or not recurring:
        conflict("La factura o recurrencia no existe.")
    bid, rid = identifier(bill.get("id")), identifier(recurring.get("id"))
    if (bill.get("user_id") != scope.user_id or recurring.get("user_id") != scope.user_id
            or bill.get("recurring_payment_id") != rid or bill.get("deleted") or recurring.get("deleted")):
        conflict("Los padres no corresponden al mismo vínculo financiero activo.")
    if existing:
        doc = validate_document(existing, scope)
        if doc["bill_id"] != bid or doc["recurring_id"] != rid or doc["lifecycle"] != "bound":
            conflict("La identidad no puede reasignarse a otros documentos.")
        original = day(doc["original_due_date"])
        frozen = {"versions": [doc["schedule_snapshot"]], "pauses": [], "end_date": None}
        if original.isoformat() not in _calendar(occurrences, frozen, original, original):
            conflict("La programación histórica del período no es verificable.")
        if money(bill.get("amount")) != money(doc["actual_amount"]):
            conflict("El importe real cambió; necesita una actualización compartida explícita.")
        return doc
    due = day(bill.get("due_date"))
    available = _calendar(occurrences, recurring, due, due)
    if due.isoformat() not in available:
        conflict("No hay un vencimiento exacto verificable; no se elegirá el más cercano.")
    versions = recurring.get("versions") or []
    selected = [v for v in versions if day(v.get("valid_from")) <= due]
    if not selected:
        conflict("No existe una versión de programación aplicable.")
    # Reject malformed ordering rather than guessing which historical version won.
    dates = [day(v.get("valid_from")) for v in versions]
    if dates != sorted(set(dates)):
        conflict("Las versiones de programación son ambiguas.")
    version = selected[-1]
    frequency = bill.get("frequency", "once")
    if frequency != "once" and FREQUENCIES.get(frequency) != version.get("frequency"):
        conflict("Las frecuencias no representan el mismo período.")
    actual, estimated = money(bill.get("amount")), money(available[due.isoformat()])
    variable = recurring.get("variable", False)
    if type(variable) is not bool or (not variable and actual != estimated):
        conflict("Los importes fijos son incompatibles; no se inventará una obligación común.")
    for candidate in candidates:
        if (candidate.get("user_id") == scope.user_id and candidate.get("id") != bid
                and candidate.get("recurring_payment_id") == rid
                and candidate.get("due_date") == due.isoformat() and not candidate.get("deleted")):
            conflict("Más de una factura reclama el mismo vencimiento.")
    snapshot = {k: deepcopy(version.get(k)) for k in ("frequency", "start_date", "due_day", "valid_from", "amount")}
    doc = dict(_id=identity(scope, rid, due.isoformat()), version=VERSION, revision=0,
               environment_id=scope.environment_id, user_id=scope.user_id, mode=scope.mode,
               bill_id=bid, recurring_id=rid, original_due_date=due.isoformat(),
               actual_amount=_stored_money(actual), estimated_amount=_stored_money(estimated),
               variable_snapshot=variable, schedule_snapshot=snapshot, lifecycle="bound",
               bill_schedule_snapshot={"frequency": frequency,
                   "anchor_day": bill.get("anchor_day") if bill.get("anchor_day") is not None else due.day,
                   "original_due_date": due.isoformat(), "series_id": bill.get("series_id") or bid},
               created_at=datetime.now(timezone.utc).isoformat())
    return validate_document(doc, scope)


def without_shared_metadata(value):
    """Future serializer utility, not installed in today's public API."""
    if isinstance(value, dict):
        return {k: without_shared_metadata(v) for k, v in value.items() if not k.startswith("_shared_")}
    if isinstance(value, list):
        return [without_shared_metadata(v) for v in value]
    return deepcopy(value)


def public_financial_document(value):
    """Copy public documents recursively; never change stored provenance.

    Only internal storage fields are removed. Public IDs and links survive.
    Safe on both legacy responses and future shared receipt recoveries.
    """
    return strip_history_metadata(_public_financial_document(value))


def _public_financial_document(value):
    if isinstance(value, dict):
        return {key: _public_financial_document(item) for key, item in value.items()
                if key not in {"_id", "request_fingerprint", "idempotency_key",
                               "_reference_revision", "_payment_revision", "_bill_generation_origin"}
                and not key.startswith("_shared_")}
    if isinstance(value, (list, tuple)):
        return [_public_financial_document(item) for item in value]
    return deepcopy(value)


def _unique(documents, scope):
    result = {}
    for doc in documents:
        key = identifier(doc.get("id"))
        if doc.get("user_id") != scope.user_id or key in result:
            conflict("Identidad de recibo o movimiento duplicada/no verificable.")
        if doc.get("deleted") is not None and type(doc["deleted"]) is not bool:
            conflict("Estado histórico no verificable.")
        result[key] = doc
    return result


@dataclass(frozen=True)
class PaymentSummary:
    paid: Decimal
    remaining: Decimal
    financial_status: str
    transaction_ids: tuple
    annulled_transaction_ids: tuple
    retained_transaction_ids: tuple
    tracking_only_records: tuple

    @property
    def requires_reconciliation(self):
        return bool(self.tracking_only_records)


def _retired_alias(documents, receipt, obligation, reverse_field):
    matches = [doc for doc in documents.values()
               if doc.get("deleted") is True and doc.get("_shared_financial_state") == "active"
               and doc.get("_shared_obligation_id") == obligation["_id"]
               and doc.get("transaction_id") == receipt["transaction_id"]
               and doc.get("_shared_origin_receipt_id") == receipt.get("_shared_origin_receipt_id")
               and doc.get(reverse_field) in (None, "", receipt["id"])]
    if len(matches) != 1:
        conflict("El seguimiento retirado no tiene un recibo financiero complementario inequívoco.")
    return matches[0]


def _present_links(obligation, payments, records, movements):
    """Retirement permits cleared links, never contradictory surviving links."""
    def reference(document, field, targets, transaction_id, inverse=None):
        value = document.get(field)
        if value in (None, ""):
            return
        target = targets.get(identifier(value))
        if (not target or target.get("transaction_id") != transaction_id
                or (inverse and target.get(inverse) not in (None, "", document["id"]))):
            conflict("Un vínculo financiero conservado apunta a otro recibo o movimiento.")

    for tx in movements.values():
        for field, expected in (("bill_id", obligation["bill_id"]),
                                ("recurring_payment_id", obligation["recurring_id"])):
            if tx.get(field) not in (None, "", expected):
                conflict("El movimiento conserva un vínculo con otra obligación.")
        reference(tx, "bill_payment_id", payments, tx["id"])
        reference(tx, "recurring_record_id", records, tx["id"])
    for payment in payments.values():
        reference(payment, "recurring_record_id", records, payment.get("transaction_id"), "bill_payment_id")
    for record in records.values():
        reference(record, "bill_payment_id", payments, record.get("transaction_id"), "recurring_record_id")


def verify_payments(document, scope, *, payments=(), records=(), movements=()):
    """Count verified financial events once, never receipts or matching amounts.

    A full old bidirectional graph is read-verifiable. A retired legacy receipt
    without explicit financial provenance is ambiguous, not an automatic refund.
    Stage 1 only understands future internal provenance; it never writes it.
    """
    ob = validate_document(document, scope)
    ps, rs, ts = (_unique(docs, scope) for docs in (payments, records, movements))
    _present_links(ob, ps, rs, ts)
    for tx in ts.values():
        if tx.get("_shared_obligation_id") not in (None, ob["_id"]):
            conflict("El movimiento pertenece a otra obligación financiera.")
        if any(tx.get(field) for field in ("debt_id", "debt_payment_id", "goal_id", "goal_contribution_id")):
            conflict("El gasto conserva vínculos financieros incompatibles con esta obligación.")
    paid_ids, annulled, retained, tracking = set(), set(), set(), set()
    for collection, docs in (("bill", ps), ("recurring", rs)):
        for rec in docs.values():
            if collection == "bill" and rec.get("bill_id") != ob["bill_id"]:
                conflict("El recibo pertenece a otra factura.")
            if collection == "recurring" and (rec.get("recurring_id") != ob["recurring_id"] or rec.get("due_date") != ob["original_due_date"]):
                conflict("El registro pertenece a otro vencimiento.")
            if rec.get("_shared_obligation_id") not in (None, ob["_id"]):
                conflict("El recibo fue asignado a otra obligación.")
            money(rec.get("amount"))
            tid = rec.get("transaction_id")
            if collection == "recurring" and rec.get("mode") == "mark" and not tid:
                if rec.get("bill_payment_id") or rec.get("_shared_financial_state"):
                    conflict("Una marca de seguimiento no demuestra un pago financiero.")
                if not _verified_mark(ob, rec):
                    if not rec.get("deleted"):
                        tracking.add(rec["id"])
                continue
            tid = identifier(tid)
            tx = ts.get(tid)
            state = rec.get("_shared_financial_state")
            if state not in (None, "active", "annulled"):
                conflict("El estado financiero del recibo es inválido.")
            if collection == "recurring" and (rec.get("mode") not in ("expense", "link") or (
                    rec.get("mode") == "expense" and rec.get("bill_payment_id") and
                    (state is None or rec.get("_shared_origin_receipt_id") != rec["id"]))):
                conflict("El modo recurrente no corresponde a un recibo compartido verificable.")
            identifier(rec.get("account_id"))
            if state is not None:
                origin = rec.get("_shared_origin_receipt_id")
                sources = [docs[origin] for docs in (ps, rs) if origin in docs] if isinstance(origin, str) else []
                if (rec.get("_shared_obligation_id") != ob["_id"] or len(sources) != 1
                        or sources[0].get("transaction_id") != tid
                        or sources[0].get("_shared_obligation_id") != ob["_id"]
                        or sources[0].get("_shared_origin_receipt_id") != origin
                        or sources[0].get("_shared_financial_state") != state
                        or money(sources[0].get("amount")) != money(rec.get("amount"))
                        or sources[0].get("account_id") != rec.get("account_id")):
                    conflict("La procedencia financiera no identifica un recibo original verificable.")
                if tx and (tx.get("_shared_obligation_id") != ob["_id"] or tx.get("_shared_origin_receipt_id") != origin):
                    conflict("La procedencia del movimiento no coincide con su recibo original.")
            if state == "annulled":
                if not rec.get("deleted") or rec.get("_shared_obligation_id") != ob["_id"] or tx or any(
                        t.get("bill_payment_id" if collection == "bill" else "recurring_record_id") == rec["id"] for t in ts.values()):
                    conflict("La anulación financiera no puede demostrarse.")
                annulled.add(tid)
                continue
            if not tx or tx.get("type") != "expense" or tx.get("deleted"):
                conflict("El recibo no tiene su gasto financiero verificable.")
            if money(tx.get("amount")) != money(rec.get("amount")) or tx.get("account_id") != rec.get("account_id") or not tx.get("account_id"):
                conflict("El importe o cuenta del gasto no coincide con el recibo.")
            if collection == "recurring" and not _same_optional_reference(tx.get("category_id"), rec.get("category_id")):
                conflict("La categoría histórica del registro no corresponde al movimiento.")
            if rec.get("deleted"):
                # Link retirement cannot zero the paid amount. Both documents
                # need immutable explicit provenance when public links are gone.
                if (state != "active" or rec.get("_shared_obligation_id") != ob["_id"]
                        or tx.get("_shared_obligation_id") != ob["_id"]
                        or rec.get("_shared_origin_receipt_id") != tx.get("_shared_origin_receipt_id")
                        or not rec.get("_shared_origin_receipt_id")):
                    conflict("Seguimiento retirado sin procedencia financiera verificable.")
                retained.add(tid)
            else:
                if collection == "bill":
                    if tx.get("bill_id") != ob["bill_id"] or tx.get("bill_payment_id") != rec["id"]:
                        conflict("El vínculo de factura con su movimiento es incoherente.")
                    counterpart = rs.get(rec.get("recurring_record_id"))
                    if state == "active" and rec.get("recurring_record_id") in (None, ""):
                        _retired_alias(rs, rec, ob, "bill_payment_id")
                    elif not counterpart or counterpart.get("bill_payment_id") != rec["id"] or counterpart.get("transaction_id") != tid:
                        conflict("El recibo no tiene su registro compartido verificable.")
                else:
                    if rec.get("mode") not in ("expense", "link") or tx.get("recurring_payment_id") != ob["recurring_id"] or tx.get("recurring_record_id") != rec["id"]:
                        conflict("El vínculo recurrente con su movimiento es incoherente.")
                    counterpart = ps.get(rec.get("bill_payment_id"))
                    if state == "active" and rec.get("bill_payment_id") in (None, ""):
                        _retired_alias(ps, rec, ob, "recurring_record_id")
                    elif not counterpart or counterpart.get("recurring_record_id") != rec["id"] or counterpart.get("transaction_id") != tid:
                        conflict("El registro no demuestra pertenecer a la misma factura.")
            paid_ids.add(tid)
    if paid_ids & annulled:
        conflict("Los recibos discrepan sobre la anulación del mismo movimiento.")
    if set(ts) != paid_ids:
        conflict("Hay movimientos adicionales sin recibos verificables.")
    amounts = [money(ts[tid]["amount"]) for tid in paid_ids]
    actual = money(ob["actual_amount"])
    # Keep exact Decimal values even for legacy values wider than the default
    # 28-digit context. This is local: no application's money context is changed.
    values = amounts + [actual]
    integer_digits = max(max(1, value.adjusted()+1) for value in values)
    fraction_digits = max(max(0, -value.as_tuple().exponent) for value in values)
    with localcontext() as ctx:
        ctx.prec = max(28, integer_digits+fraction_digits+len(str(len(values)))+2)
        paid = sum(amounts, Decimal(0))
        remaining = actual-paid
    if paid > actual:
        conflict("El histórico ya supera el importe real; requiere conciliación explícita.")
    return PaymentSummary(paid, remaining, "paid" if paid == actual else "partial" if paid else "unpaid",
                          tuple(sorted(paid_ids)), tuple(sorted(annulled)), tuple(sorted(retained)), tuple(sorted(tracking)))


def _transaction(session):
    if session is None or getattr(session, "in_transaction", False) is not True:
        raise RuntimeError("Shared identity operations require an existing transaction")


async def install_indexes(database):
    """Explicit administrative call only; no startup/import side effects."""
    for name, keys in INDEXES:
        await database.shared_obligations.create_index(list(keys), name=name, unique=True)


async def require_indexes(database):
    indexes = await database.shared_obligations.index_information()
    for name, keys in INDEXES:
        spec = indexes.get(name, {})
        if (tuple(spec.get("key", ())) != keys or spec.get("unique") is not True
                or spec.get("partialFilterExpression") or spec.get("sparse") or spec.get("collation")):
            raise HTTPException(503, "Faltan índices íntegros de identidad compartida; no se escribirá.")


async def _scope(database, expected_environment_id, effective_user, session):
    _transaction(session)
    context = await get_financial_context(database, expected_environment_id, effective_user, session)
    return Scope(context["environment_id"], context["user_id"], context["mode"])


async def _hello(database):
    return await database.client.admin.command("hello")


async def require_activation(database, settings, *, effective_user, session):
    """Explicit read-only readiness check, never a startup hook or flow switch.

    Future payment integration must call this in its existing transaction.
    A configured flag alone is not permission to write financial documents.
    """
    if settings.shared_obligations_enabled is not True:
        conflict("La coordinación R4 está desactivada.")
    _transaction(session)
    identifier(effective_user)
    try:
        hello = await _hello(database)
        router = hello.get("msg") == "isdbgrid"
        replica = bool(hello.get("setName"))
        wire = hello.get("maxWireVersion")
        if (hello.get("logicalSessionTimeoutMinutes") is None
                or not (replica or router) or hello.get("isWritablePrimary") is not True
                or type(wire) is not int or wire < (8 if router else 7)):
            raise HTTPException(503, "MongoDB no demuestra soporte de transacciones para R4.")
        # R6 remains the sole authority for the expected financial environment.
        # This actual read runs within the supplied transaction, not just hello.
        scope = await _scope(database, settings.expected_financial_environment_id, effective_user, session)
        await require_indexes(database)
        return scope
    except PyMongoError:
        raise HTTPException(503, "No se pueden verificar los requisitos de activación R4.") from None


async def has_managed_obligation(database, *, effective_user, session,
                                 bill_id=None, recurring_id=None, original_due_date=None,
                                 transaction_id=None, whole_recurring=False):
    """Detect prior R4 ownership even with the switch/pin absent; never adopt it.

    Unknown/corrupt metadata counts as managed, and read errors never mean empty.
    The effective user is server supplied, not an authentication claim.
    """
    _transaction(session)
    identifier(effective_user)
    if type(whole_recurring) is not bool or (whole_recurring and (recurring_id is None or original_due_date is not None)):
        conflict("El alcance del detector de recurrencias no es verificable.")
    if not whole_recurring and (recurring_id is None) != (original_due_date is None):
        conflict("El detector necesita la recurrencia y el vencimiento originales juntos.")
    if bill_id is None and recurring_id is None and transaction_id is None:
        conflict("No se indicó una obligación para comprobar.")
    lookups = []
    if bill_id is not None:
        identifier(bill_id)
        lookups.extend((("shared_obligations", {"bill_id": bill_id}),
                        ("bills", {"id": bill_id}), ("bill_payments", {"bill_id": bill_id}),
                        ("transactions", {"bill_id": bill_id})))
    if recurring_id is not None:
        identifier(recurring_id)
        if whole_recurring:
            lookups.extend((("shared_obligations", {"recurring_id": recurring_id}),
                ("recurring_payments", {"id": recurring_id}),
                ("recurring_payment_records", {"recurring_id": recurring_id}),
                ("bills", {"recurring_payment_id": recurring_id}),
                ("transactions", {"recurring_payment_id": recurring_id})))
        else:
            day(original_due_date)
            lookups.extend((("shared_obligations", {"recurring_id": recurring_id, "original_due_date": original_due_date}),
                            ("recurring_payment_records", {"recurring_id": recurring_id, "due_date": original_due_date})))
    if transaction_id is not None:
        identifier(transaction_id)
        lookups.extend((("transactions", {"id": transaction_id}),
                        ("bill_payments", {"transaction_id": transaction_id}),
                        ("recurring_payment_records", {"transaction_id": transaction_id})))
    try:
        for collection, query in lookups:
            async for doc in getattr(database, collection).find(dict(query, user_id=effective_user), session=session):
                if collection == "shared_obligations" or any(key.startswith("_shared_") for key in doc):
                    return True
                # Missing markers on a movement must not hide an inverse
                # receipt whose bill/period already has a reserved identity.
                if doc.get("bill_id") and await database.shared_obligations.find_one(
                        {"user_id": effective_user, "bill_id": doc["bill_id"]}, session=session):
                    return True
                if doc.get("recurring_id") and doc.get("due_date") and await database.shared_obligations.find_one(
                        {"user_id": effective_user, "recurring_id": doc["recurring_id"],
                         "original_due_date": doc["due_date"]}, session=session):
                    return True
        if recurring_id is not None and not whole_recurring:
            # A missing reservation/receipt must not hide a retained R4 expense.
            # Exclude another period only with the existing strict graph proof.
            async for tx in database.transactions.find(
                    {"user_id": effective_user, "recurring_payment_id": recurring_id}, session=session):
                if not any(key.startswith("_shared_") for key in tx):
                    continue
                source = await database.shared_obligations.find_one(
                    {"_id": tx.get("_shared_obligation_id"), "user_id": effective_user}, session=session)
                if not source:
                    return True
                try:
                    context = await get_financial_context(database, source.get("environment_id"), effective_user, session)
                    scope = Scope(context["environment_id"], context["user_id"], context["mode"])
                    target = {"_id": identity(scope, recurring_id, original_due_date), "bill_id": bill_id,
                              "recurring_id": recurring_id, "original_due_date": original_due_date}
                    await _other_period(database, tx, target, scope, session)
                except HTTPException as error:
                    if error.status_code == 503:
                        raise
                    return True
        return False
    except PyMongoError:
        raise HTTPException(503, "No se puede descartar una obligación previamente gestionada por R4.") from None


async def require_legacy_allowed(database, **lookup):
    """Block old financial writes for reserved/managed R4 obligations."""
    if await has_managed_obligation(database, **lookup):
        conflict("La obligación conserva gestión R4; no puede volver al flujo anterior.")


async def resolve_shared_obligation(database, bill_id, *, expected_environment_id, effective_user, session, occurrences):
    """Snapshot lookup/draft, read-only even for missing metadata or legacy data."""
    scope = await _scope(database, expected_environment_id, effective_user, session)
    bill = await database.bills.find_one({"id": identifier(bill_id), "user_id": scope.user_id}, session=session)
    rid = bill.get("recurring_payment_id") if bill else None
    recurring = await database.recurring_payments.find_one({"id": rid, "user_id": scope.user_id}, session=session) if rid else None
    stored = await database.shared_obligations.find({"user_id": scope.user_id, "bill_id": bill_id}, session=session).to_list(None)
    if len(stored) > 1:
        conflict("La factura tiene más de una identidad compartida.")
    candidates = await database.bills.find({"user_id": scope.user_id, "recurring_payment_id": rid}, session=session).to_list(None) if rid else []
    doc = resolve_documents(bill, recurring, scope, occurrences=occurrences, existing=stored[0] if stored else None, candidates=candidates)
    if bill.get("_shared_obligation_id") is not None and (not stored or bill["_shared_obligation_id"] != doc["_id"]):
        conflict("El vínculo declarado perdió su identidad persistente o apunta a otra obligación.")
    claimed = await database.shared_obligations.find_one({"user_id": scope.user_id, "recurring_id": doc["recurring_id"], "original_due_date": doc["original_due_date"]}, session=session)
    if claimed:
        validate_document(claimed, scope)
        if claimed["bill_id"] != bill_id:
            conflict("El vencimiento ya pertenece a otra factura; no se liberan identidades históricas.")
    return doc, bool(stored)


async def create_shared_obligation(database, bill_id, *, expected_environment_id, effective_user, session, occurrences):
    """Explicit metadata-only creation, dormant in all current routes.

    Never adopts existing receipts. Existing identity replay is read-only.
    Unique conflicts escape to the existing transaction runner: no partial retry.
    """
    _transaction(session)
    await require_indexes(database)
    doc, persisted = await resolve_shared_obligation(database, bill_id, expected_environment_id=expected_environment_id,
                                                    effective_user=effective_user, session=session, occurrences=occurrences)
    if persisted:
        return doc
    for collection, query in (
        (database.bill_payments, {"user_id": effective_user, "bill_id": bill_id}),
        (database.recurring_payment_records, {"user_id": effective_user, "recurring_id": doc["recurring_id"], "due_date": doc["original_due_date"]}),
        (database.transactions, {"user_id": effective_user, "bill_id": bill_id}),
        (database.transactions, {"user_id": effective_user, "_shared_obligation_id": doc["_id"]}),
    ):
        if await collection.find_one(query, session=session):
            conflict("Hay historial previo: esta etapa no migra ni asigna pagos automáticamente.")
    async for tx in database.transactions.find({"user_id": effective_user, "recurring_payment_id": doc["recurring_id"]}, session=session):
        rec = await database.recurring_payment_records.find_one(
            {"id": tx.get("recurring_record_id"), "user_id": effective_user}, session=session)
        if not rec or rec.get("recurring_id") != doc["recurring_id"] or rec.get("transaction_id") != tx.get("id"):
            conflict("La recurrencia tiene movimientos huérfanos; no se adoptarán al crear identidad.")
    await coordinate(database, effective_user, {"bill_id": bill_id, "recurring_payment_id": doc["recurring_id"]}, session)
    await database.shared_obligations.insert_one(deepcopy(doc), session=session)
    return doc


async def _other_period(database, tx, obligation, scope, session):
    """Prove a foreign period from receipt IDs, never transaction dates/amounts."""
    tid = identifier(tx.get("id"))
    receipts = await database.recurring_payment_records.find(
        {"user_id": scope.user_id, "transaction_id": tid}, session=session).to_list(None)
    if len(receipts) != 1:
        conflict("Hay un gasto recurrente sin un período inequívoco; requiere conciliación.")
    record = receipts[0]
    _unique([record], scope)
    _unique([tx], scope)
    due = day(record.get("due_date")).isoformat()
    if (record.get("recurring_id") != obligation["recurring_id"]
            or tx.get("recurring_record_id") != record["id"]
            or due == obligation["original_due_date"]):
        conflict("El gasto recurrente no demuestra pertenecer a otro período.")
    account = await database.accounts.find_one(
        {"id": tx.get("account_id"), "user_id": scope.user_id}, session=session)
    if not account or account.get("deleted"):
        conflict("El gasto recurrente tiene una cuenta no verificable.")
    shared_id = tx.get("_shared_obligation_id") or record.get("_shared_obligation_id")
    payments = await database.bill_payments.find(
        {"user_id": scope.user_id, "transaction_id": tid}, session=session).to_list(None)
    if shared_id:
        other = await database.shared_obligations.find_one({"_id": identifier(shared_id)}, session=session)
        other = validate_document(other, scope)
        if other["recurring_id"] != obligation["recurring_id"] or other["original_due_date"] != due or other["_id"] == obligation["_id"]:
            conflict("La identidad del otro período es incompatible.")
        verify_payments(other, scope, payments=payments, records=[record], movements=[tx])
        return
    if payments or tx.get("bill_id") or tx.get("bill_payment_id") or record.get("bill_payment_id"):
        # A complete legacy bill graph proves a foreign period without adopting
        # it into shared_obligations. The record's stored due is the historical
        # period; today's bill date/calendar must not remap that payment.
        if len(payments) != 1:
            conflict("El pago histórico de otro período es inexistente o ambiguo.")
        payment = payments[0]
        _unique([payment], scope)
        bid = identifier(payment.get("bill_id"))
        bills = await database.bills.find({"id": bid, "user_id": scope.user_id}, session=session).to_list(None)
        if len(bills) != 1:
            conflict("La factura histórica del otro período no es verificable.")
        bill = bills[0]
        _unique([bill], scope)
        if (bid == obligation["bill_id"] or bill.get("deleted")
                or bill.get("recurring_payment_id") != obligation["recurring_id"]
                or payment.get("deleted") or record.get("deleted") or tx.get("deleted")
                or tx.get("type") != "expense" or record.get("mode") != "link"
                or tx.get("bill_id") != bid or tx.get("bill_payment_id") != payment["id"]
                or payment.get("recurring_record_id") != record["id"]
                or record.get("bill_payment_id") != payment["id"]
                or not payment.get("account_id") or payment.get("account_id") != tx.get("account_id")
                or record.get("account_id") != tx.get("account_id")
                or money(payment.get("amount")) != money(tx.get("amount"))
                or money(record.get("amount")) != money(tx.get("amount"))
                or not _same_optional_reference(record.get("category_id"), tx.get("category_id"))
                or any(value.get(field) not in (None, "") for value in (payment, record, tx)
                       for field in ("_shared_obligation_id", "_shared_origin_receipt_id", "_shared_financial_state"))
                or any(tx.get(field) for field in ("debt_id", "debt_payment_id", "goal_id", "goal_contribution_id"))):
            conflict("El grafo histórico de factura de otro período contiene vínculos incompatibles.")
        return
    # Legacy standalone recurring expenses are verifiable through the full
    # inverse receipt, even when their original date no longer occurs today.
    if (payments or record.get("deleted") or tx.get("deleted")
            or record.get("mode") not in ("expense", "link") or tx.get("type") != "expense"
            or not record.get("account_id") or record.get("account_id") != tx.get("account_id")
            or money(record.get("amount")) != money(tx.get("amount"))
            or not _same_optional_reference(record.get("category_id"), tx.get("category_id"))
            or any(tx.get(field) for field in ("bill_id", "bill_payment_id", "debt_id", "debt_payment_id", "goal_id", "goal_contribution_id", "_shared_origin_receipt_id"))
            or record.get("bill_payment_id") or record.get("_shared_financial_state") or record.get("_shared_origin_receipt_id")):
        conflict("El movimiento recurrente de otro período no tiene vínculos verificables.")


async def inspect_payments(database, document, *, expected_environment_id, effective_user, session, draft=False):
    """Read-only, consistent inspection. No reconciliation or financial write."""
    scope = await _scope(database, expected_environment_id, effective_user, session)
    ob = validate_document(document, scope)
    if type(draft) is not bool:
        conflict("El modo de inspección no es verificable.")
    # A caller's draft/stale copy is never authoritative over persisted state.
    stored = await database.shared_obligations.find_one({"_id": ob["_id"]}, session=session)
    by_bill = await database.shared_obligations.find(
        {"user_id": effective_user, "bill_id": ob["bill_id"]}, session=session).to_list(None)
    by_period = await database.shared_obligations.find(
        {"user_id": effective_user, "recurring_id": ob["recurring_id"],
         "original_due_date": ob["original_due_date"]}, session=session).to_list(None)
    if stored:
        canonical = validate_document(stored, scope)
        fields = ("_id", "version", "revision", "bill_id", "recurring_id", "original_due_date")
        if draft or any(ob[field] != canonical[field] for field in fields):
            conflict("La identidad proporcionada es obsoleta o pretende sustituir una identidad persistida.")
        if len(by_bill) != 1 or len(by_period) != 1 or by_bill[0]["_id"] != canonical["_id"] or by_period[0]["_id"] != canonical["_id"]:
            conflict("La asociación persistida no es única.")
        ob = canonical
    elif not draft or by_bill or by_period:
        conflict("No hay una identidad persistida verificable; un borrador exige inspección explícita y no puede reasignar vínculos.")
    payments = await database.bill_payments.find({"user_id": effective_user, "bill_id": ob["bill_id"]}, session=session).to_list(None)
    records = await database.recurring_payment_records.find({"user_id": effective_user, "recurring_id": ob["recurring_id"], "due_date": ob["original_due_date"]}, session=session).to_list(None)
    referenced = [r.get("transaction_id") for r in payments + records if r.get("transaction_id")]
    queries = ({"id": {"$in": referenced}}, {"bill_id": ob["bill_id"]},
               {"_shared_obligation_id": ob["_id"]},
               {"bill_payment_id": {"$in": [p["id"] for p in payments]}},
               {"recurring_record_id": {"$in": [r["id"] for r in records]}})
    found = {}
    for query in queries:
        async for tx in database.transactions.find(dict(query, user_id=effective_user), session=session):
            # Same physical Mongo document can appear in several lookup paths.
            key = tx.get("_id", tx.get("id"))
            found[key] = tx
    async for tx in database.transactions.find(
            {"user_id": effective_user, "recurring_payment_id": ob["recurring_id"]}, session=session):
        if tx.get("_id", tx.get("id")) not in found:
            await _other_period(database, tx, ob, scope, session)
    for tx in found.values():
        account = await database.accounts.find_one({"id": tx.get("account_id"), "user_id": effective_user}, session=session)
        if not account or account.get("deleted"):
            conflict("El movimiento real tiene una cuenta inexistente o no disponible.")
    # Also inspect the reverse lookup, including receipts from another owner
    # of a period: a valid local graph must not hide additional corrupt aliases.
    transaction_ids = [tx["id"] for tx in found.values()]
    for collection, receipts in ((database.bill_payments, payments), (database.recurring_payment_records, records)):
        seen = {rec.get("_id", rec.get("id")) for rec in receipts}
        async for rec in collection.find({"user_id": effective_user, "transaction_id": {"$in": transaction_ids}}, session=session):
            key = rec.get("_id", rec.get("id"))
            if key not in seen:
                receipts.append(rec)
                seen.add(key)
    return verify_payments(ob, scope, payments=payments, records=records, movements=list(found.values()))


@dataclass(frozen=True)
class SharedPaymentResult:
    created: bool
    financial_state: str
    transaction_id: str
    bill_payment: dict
    recurring_record: dict
    summary: PaymentSummary


def _event_ids(origin, receipt_id):
    identifier(receipt_id)
    if origin == "bill":
        pair = (receipt_id, str(uuid5(NAMESPACE_URL, "bill-rp-record:"+receipt_id)))
    elif origin == "recurring":
        pair = (str(uuid5(NAMESPACE_URL, "shared-bill-payment:"+receipt_id)), receipt_id)
    else:
        conflict("Origen de intención financiera desconocido.")
    if pair[0] == pair[1]:
        conflict("Los recibos originales y complementarios no pueden compartir ID.")
    return pair


def _native_amount(value):
    # The existing balance calculator consumes native floats. Reject conversion
    # that changes the decimal value instead of altering that financial formula.
    exact = money(value)
    try:
        native = float(exact)
        if money(native) != exact:
            raise ValueError()
    except (ValueError, OverflowError):
        conflict("El importe no puede conservarse en el formato financiero actual.")
    return native


def _intent(ob, origin, receipt_id, transaction_id, payload):
    _event_ids(origin, receipt_id)
    identifier(transaction_id)
    if not isinstance(payload, dict):
        conflict("La intención debe conservar el payload original.")
    fields = {"amount", "account_id", "date", "notes"}
    if origin == "recurring":
        fields |= {"mode", "due_date", "category_id", "transaction_id", "settles", "allow_overpay"}
        # Preserve the original payload/fingerprint; the public parser has always
        # accepted an ISO day prefix. No nearest-date reassignment is permitted.
        raw_due = payload.get("due_date")
        try:
            normalized = date.fromisoformat(raw_due[:10]).isoformat() if isinstance(raw_due, str) else None
        except ValueError:
            normalized = None
        if normalized != ob["original_due_date"]:
            conflict("La intención recurrente pertenece a otro vencimiento.")
    if set(payload) - fields:
        conflict("El payload contiene campos que no pertenecen al contrato de origen.")
    identifier(payload.get("account_id"))
    _native_amount(payload.get("amount"))
    if origin == "recurring" and payload.get("mode", "expense") != "expense":
        conflict("Este núcleo solo registra pagos financieros expense; mark/link requieren otra integración.")
    try:
        encoded = json.dumps({"bid" if origin == "bill" else "rid": ob["bill_id"] if origin == "bill" else ob["recurring_id"],
                              **payload}, sort_keys=True, allow_nan=False)
    except (ValueError, TypeError):
        conflict("El payload original no tiene una representación verificable.")
    return {"origin": origin, "receipt_id": receipt_id, "transaction_id": transaction_id,
            "payload": deepcopy(payload), "fingerprint": hashlib.sha256(encoded.encode()).hexdigest()}


async def _canonical_payment_obligation(database, obligation_id, expected, user, session):
    scope = await _scope(database, expected, user, session)
    await require_indexes(database)
    doc = await database.shared_obligations.find_one({"_id": identifier(obligation_id)}, session=session)
    return scope, validate_document(doc, scope)


async def _lock_payment_obligation(database, ob, scope, session):
    result = await database.shared_obligations.update_one(
        {"_id": ob["_id"], "user_id": scope.user_id, "revision": ob["revision"]},
        {"$inc": {"revision": 1}}, session=session)
    if result.matched_count != 1:
        conflict("La revisión financiera cambió; debe repetirse la transacción completa.")
    return validate_document(await database.shared_obligations.find_one({"_id": ob["_id"]}, session=session), scope)


async def _payment_summary(database, ob, scope, session):
    result = await inspect_payments(database, ob, expected_environment_id=scope.environment_id,
                                    effective_user=scope.user_id, session=session)
    if result.requires_reconciliation:
        conflict("El seguimiento sin dinero verificable necesita conciliación explícita.")
    return result


async def _read_event(database, ob, scope, origin, receipt_id, session, summary=None):
    pid, rid = _event_ids(origin, receipt_id)
    p = await database.bill_payments.find_one({"id": pid}, session=session)
    r = await database.recurring_payment_records.find_one({"id": rid}, session=session)
    if not p and not r:
        return None
    if not p or not r:
        conflict("La intención financiera perdió su recibo complementario.")
    capsule = p.get("_shared_intent")
    if not isinstance(capsule, dict) or capsule != r.get("_shared_intent"):
        conflict("La intención original no puede verificarse.")
    try:
        expected = _intent(ob, origin, receipt_id, capsule["transaction_id"], capsule["payload"])
    except KeyError:
        conflict("La intención original está incompleta.")
    if capsule != expected:
        conflict("Los IDs o el payload de origen fueron modificados.")
    for rec in (p, r):
        if (rec.get("user_id") != scope.user_id or rec.get("_shared_obligation_id") != ob["_id"]
                or rec.get("_shared_origin_receipt_id") != receipt_id
                or rec.get("_shared_financial_state") not in ("active", "annulled")
                or rec.get("transaction_id") != capsule["transaction_id"]
                or rec.get("account_id") != capsule["payload"]["account_id"]
                or money(rec.get("amount")) != money(capsule["payload"]["amount"])):
            conflict("El recibo no corresponde a su intención original.")
    source = p if origin == "bill" else r
    if source.get("request_fingerprint") != capsule["fingerprint"]:
        conflict("La huella original de idempotencia no coincide.")
    tx = await database.transactions.find_one({"id": capsule["transaction_id"]}, session=session)
    if tx and tx.get("_shared_intent") != capsule:
        conflict("El movimiento perdió su intención original.")
    if summary is None:
        summary = await _payment_summary(database, ob, scope, session)
    return SharedPaymentResult(False, source.get("_shared_financial_state"), capsule["transaction_id"],
                               deepcopy(p), deepcopy(r), summary)


async def _strict_payment_history(database, ob, scope, session, summary):
    # No implicit adoption of even apparently matching pre-R4 receipts.
    for collection, query, field in (
            (database.bill_payments, {"bill_id": ob["bill_id"]}, "bill_payment"),
            (database.recurring_payment_records, {"recurring_id": ob["recurring_id"], "due_date": ob["original_due_date"]}, "recurring_record")):
        async for receipt in collection.find(dict(query, user_id=scope.user_id), session=session):
            if field == "recurring_record" and _verified_mark(ob, receipt):
                continue
            capsule = receipt.get("_shared_intent")
            if not isinstance(capsule, dict):
                conflict("El historial no tiene intenciones R4 verificables; no se adoptará automáticamente.")
            event = await _read_event(database, ob, scope, capsule.get("origin"), capsule.get("receipt_id"), session, summary)
            if not event or getattr(event, field)["id"] != receipt["id"]:
                conflict("El historial declara una intención original distinta de su recibo.")


async def _payment_parents(database, ob, scope, session, account_id, category_id=None, *, public_request=False):
    bill = await database.bills.find_one({"id": ob["bill_id"], "user_id": scope.user_id}, session=session)
    rp = await database.recurring_payments.find_one({"id": ob["recurring_id"], "user_id": scope.user_id}, session=session)
    if (not bill or not rp or bill.get("deleted") or rp.get("deleted")
            or bill.get("recurring_payment_id") != ob["recurring_id"]
            or money(bill.get("amount")) != money(ob["actual_amount"])):
        conflict("Los padres o el importe real cambiaron sin coordinación compartida.")
    account = await database.accounts.find_one({"id": account_id, "user_id": scope.user_id}, session=session)
    if not account or account.get("deleted"):
        if public_request:
            raise HTTPException(422, "La cuenta seleccionada no existe.")
        conflict("La cuenta financiera no existe.")
    if category_id:
        cat = await database.categories.find_one({"id": category_id, "user_id": scope.user_id}, session=session)
        if not cat or cat.get("type") != "expense" or cat.get("is_group") or cat.get("deleted"):
            if public_request:
                raise HTTPException(422, "La categoría debe ser una categoría de gasto existente.")
            conflict("La categoría financiera no es verificable.")
    await coordinate(database, scope.user_id, {"bill_id": ob["bill_id"], "recurring_id": ob["recurring_id"],
                                             "account_id": account_id, "category_id": category_id}, session)
    return bill, rp


async def register_shared_payment(database, obligation_id, *, origin, receipt_id, transaction_id, payload,
                                  expected_environment_id, effective_user, session, recompute_account_balance,
                                  effective_date=None, public_request=False):
    """Internal kernel, no session/commit creation; 2D.3 dispatch is exclusive.

    Caller preserves the origin route's original IDs and model_dump payload.
    The future adapter MUST separately enforce require_activation.
    """
    scope, ob = await _canonical_payment_obligation(database, obligation_id, expected_environment_id, effective_user, session)
    capsule = _intent(ob, origin, receipt_id, transaction_id, payload)
    existing = await _read_event(database, ob, scope, origin, receipt_id, session)
    if existing:
        if existing.bill_payment["_shared_intent"] != capsule:
            conflict("La intención ya se utilizó con IDs o datos diferentes.")
        if existing.financial_state != "active":
            conflict("La intención fue anulada; no se recreará el pago.")
        return existing
    if ob["lifecycle"] != "bound":
        conflict("La obligación retirada no admite una nueva intención.")
    ob = await _lock_payment_obligation(database, ob, scope, session)
    summary = await _payment_summary(database, ob, scope, session)
    await _strict_payment_history(database, ob, scope, session, summary)
    if money(payload["amount"]) > summary.remaining:
        if public_request and summary.remaining > 0:
            raise HTTPException(422, f"El monto supera lo pendiente ({float(summary.remaining):.2f}).")
        conflict("El pago supera el pendiente común verificado.")
    amount = _native_amount(payload["amount"])
    pid, rid = _event_ids(origin, receipt_id)
    # Protect ID slots globally, including old documents with ObjectId _id.
    for collection, key in (("transactions", transaction_id), ("bill_payments", pid), ("recurring_payment_records", rid)):
        for field in ("_id", "id"):
            if await getattr(database, collection).find_one({field: key}, session=session):
                conflict("Un identificador original/complementario pertenece a otro evento.")
    bill = await database.bills.find_one({"id": ob["bill_id"], "user_id": scope.user_id}, session=session)
    rp = await database.recurring_payments.find_one({"id": ob["recurring_id"], "user_id": scope.user_id}, session=session)
    parent = bill if origin == "bill" else rp
    category = payload.get("category_id") or (parent or {}).get("category_id")
    bill, rp = await _payment_parents(database, ob, scope, session, payload["account_id"], category, public_request=public_request)
    when = effective_date or payload.get("date") or datetime.now(timezone.utc).isoformat()
    try:
        stamp = datetime.fromisoformat(when)
        if stamp.tzinfo is None:
            raise ValueError()
        if payload.get("date"):
            original = datetime.fromisoformat(payload["date"])
            if original.tzinfo is None:
                original = original.replace(tzinfo=timezone.utc)
            if original != stamp:
                raise ValueError()
    except (ValueError, TypeError):
        conflict("La fecha efectiva no es verificable.")
    notes = payload.get("notes")
    if notes is not None and not isinstance(notes, str):
        conflict("Las notas originales no son verificables.")
    notes = (notes or "").strip()[:200] or None
    now = datetime.now(timezone.utc).isoformat()
    common = dict(user_id=scope.user_id, amount=amount, account_id=payload["account_id"], date=when, notes=notes,
                  created_at=now, transaction_id=transaction_id, _shared_obligation_id=ob["_id"],
                  _shared_origin_receipt_id=receipt_id, _shared_financial_state="active", _shared_intent=deepcopy(capsule))
    series = (ob.get("bill_schedule_snapshot") or {}).get("series_id") or bill.get("series_id") or ob["bill_id"]
    p = dict(common, _id=pid, id=pid, bill_id=ob["bill_id"], series_id=series, recurring_record_id=rid)
    r = dict(common, _id=rid, id=rid, recurring_id=ob["recurring_id"], due_date=ob["original_due_date"],
             mode="link" if origin == "bill" else "expense", category_id=category,
             expected_amount=_native_amount(ob["actual_amount"]), settles=False, bill_payment_id=pid)
    (p if origin == "bill" else r)["request_fingerprint"] = capsule["fingerprint"]
    tx = dict(common, _id=transaction_id, id=transaction_id, name=(bill if origin == "bill" else rp)["name"],
              type="expense", category_id=category, to_account_id=None, debt_id=None, debt_payment_id=None,
              bill_id=ob["bill_id"], bill_payment_id=pid, recurring_payment_id=ob["recurring_id"], recurring_record_id=rid)
    tx.pop("transaction_id")
    await database.transactions.insert_one(tx, session=session)
    await database.bill_payments.insert_one(p, session=session)
    await database.recurring_payment_records.insert_one(r, session=session)
    await recompute_account_balance(payload["account_id"], session=session)
    result = await _read_event(database, ob, scope, origin, receipt_id, session)
    return SharedPaymentResult(True, result.financial_state, result.transaction_id, result.bill_payment, result.recurring_record, result.summary)


async def change_shared_payment(database, obligation_id, *, origin, receipt_id, action,
                                expected_environment_id, effective_user, session, recompute_account_balance):
    """Annul money once, or retire one/both tracking views without any refund."""
    if action not in ("annul", "retire_bill", "retire_recurring", "retire_both"):
        conflict("Transición compartida desconocida.")
    scope, ob = await _canonical_payment_obligation(database, obligation_id, expected_environment_id, effective_user, session)
    event = await _read_event(database, ob, scope, origin, receipt_id, session)
    if not event:
        conflict("La intención financiera no existe.")
    if event.financial_state == "annulled":
        return event
    views = ("bill", "recurring") if action in ("annul", "retire_both") else ("bill",) if action == "retire_bill" else ("recurring",)
    if action != "annul" and all((event.bill_payment if view == "bill" else event.recurring_record).get("deleted") for view in views):
        return event
    await _strict_payment_history(database, ob, scope, session, event.summary)
    ob = await _lock_payment_obligation(database, ob, scope, session)
    await _payment_parents(database, ob, scope, session, event.bill_payment["account_id"])
    if action == "annul":
        # R3 template creation touches this same movement: deletion conflicts and
        # retries with a fresh snapshot, then checks the template again.
        if await database.recurring_templates.find_one({"source_transaction_id": event.transaction_id}, session=session):
            conflict("El movimiento es origen de una plantilla recurrente.")
        result = await database.transactions.delete_one({"_id": event.transaction_id, "id": event.transaction_id, "user_id": scope.user_id}, session=session)
        if result.deleted_count != 1:
            conflict("El movimiento original no puede anularse inequívocamente.")
        for collection, rec in (("bill_payments", event.bill_payment), ("recurring_payment_records", event.recurring_record)):
            await getattr(database, collection).update_one({"id": rec["id"], "user_id": scope.user_id},
                {"$set": {"deleted": True, "_shared_financial_state": "annulled"}}, session=session)
        await recompute_account_balance(event.bill_payment["account_id"], session=session)
    else:
        for view in views:
            collection, rec = ("bill_payments", event.bill_payment) if view == "bill" else ("recurring_payment_records", event.recurring_record)
            await getattr(database, collection).update_one({"id": rec["id"], "user_id": scope.user_id}, {"$set": {"deleted": True}}, session=session)
            if view == "bill":
                await database.recurring_payment_records.update_one({"id": event.recurring_record["id"], "user_id": scope.user_id},
                    {"$set": {"bill_payment_id": None}}, session=session)
                fields = {"bill_id": "", "bill_payment_id": ""}
            else:
                await database.bill_payments.update_one({"id": event.bill_payment["id"], "user_id": scope.user_id},
                    {"$set": {"recurring_record_id": None}}, session=session)
                fields = {"recurring_payment_id": "", "recurring_record_id": ""}
            await database.transactions.update_one({"id": event.transaction_id, "user_id": scope.user_id}, {"$unset": fields}, session=session)
        p = await database.bill_payments.find_one({"id": event.bill_payment["id"]}, session=session)
        r = await database.recurring_payment_records.find_one({"id": event.recurring_record["id"]}, session=session)
        if p.get("deleted") and r.get("deleted"):
            await database.shared_obligations.update_one({"_id": ob["_id"]}, {"$set": {"lifecycle": "tracking_detached"}}, session=session)
            ob = await database.shared_obligations.find_one({"_id": ob["_id"]}, session=session)
    return await _read_event(database, ob, scope, origin, receipt_id, session)


@dataclass(frozen=True)
class SharedReadView:
    """Private snapshot for future readers; never return this object as an API."""
    obligation: dict
    summary: PaymentSummary
    payments: tuple
    records: tuple
    movements: tuple


async def read_shared_view(database, *, expected_environment_id, effective_user, session,
                           bill_id=None, recurring_id=None, original_due_date=None):
    """Dormant read adapter. None means verified absence, never lookup failure.

    Caller owns a snapshot transaction. No activation, adoption, indexes or
    financial writes occur here. A persisted identity requires verified R6 scope.
    """
    _transaction(session)
    identifier(effective_user)
    if bill_id is not None:
        if recurring_id is not None or original_due_date is not None:
            conflict("La consulta debe identificar una factura o un período, no ambos.")
        query = {"user_id": effective_user, "bill_id": identifier(bill_id)}
    else:
        query = {"user_id": effective_user, "recurring_id": identifier(recurring_id),
                 "original_due_date": day(original_due_date).isoformat()}
    try:
        documents = await database.shared_obligations.find(query, session=session).to_list(None)
        if not documents:
            if await has_managed_obligation(database, effective_user=effective_user, session=session,
                    bill_id=bill_id, recurring_id=recurring_id, original_due_date=original_due_date):
                conflict("El historial compartido perdió su identidad verificable.")
            return None
        if len(documents) != 1:
            conflict("La lectura compartida tiene más de una identidad.")
        ob = documents[0]
        summary = await inspect_payments(database, ob, expected_environment_id=expected_environment_id,
                                         effective_user=effective_user, session=session)
        # The same snapshot includes retired tracking receipts and active money.
        payments = await database.bill_payments.find(
            {"user_id": effective_user, "bill_id": ob["bill_id"]}, session=session).to_list(None)
        records = await database.recurring_payment_records.find(
            {"user_id": effective_user, "recurring_id": ob["recurring_id"],
             "due_date": ob["original_due_date"]}, session=session).to_list(None)
        movements = await database.transactions.find(
            {"user_id": effective_user, "id": {"$in": list(summary.transaction_ids)}}, session=session).to_list(None)
        return SharedReadView(deepcopy(ob), summary, tuple(payments), tuple(records), tuple(movements))
    except PyMongoError:
        raise HTTPException(503, "No se pudo verificar la lectura compartida.") from None


def shared_bill_public(legacy_public, view, today):
    """Keep the bill response shape, replacing only verified financial fields."""
    if view is None:
        return public_financial_document(legacy_public)
    ob, summary = view.obligation, view.summary
    if legacy_public.get("id") != ob["bill_id"]:
        conflict("La respuesta pertenece a otra factura.")
    actual = money(ob["actual_amount"])
    if money(legacy_public["amount"]) != actual:
        conflict("El importe de la factura no coincide con su identidad compartida.")
    due = ob["original_due_date"]
    paid = summary.remaining == 0
    days = (day(due) - today).days
    out = public_financial_document(legacy_public)
    out.update(due_date=due, paid_amount=float(summary.paid), remaining=float(summary.remaining),
               status="paid" if paid else "overdue" if due < today.isoformat() else "pending",
               partial=bool(summary.paid and not paid), progress=float(summary.paid / actual),
               days_left=days, reminder_active=bool(out.get("reminder_days") is not None and not paid
                                                   and 0 <= days <= out["reminder_days"]))
    if "payments" in out:
        enriched = {p["id"]: p for p in out["payments"]}
        visible = []
        for payment in sorted((p for p in view.payments if not p.get("deleted")),
                              key=lambda p: p.get("date", ""), reverse=True):
            public = public_financial_document(payment)
            if "account_name" in enriched.get(payment["id"], {}):
                public["account_name"] = enriched[payment["id"]]["account_name"]
            visible.append(public)
        out["payments"] = visible
    return out


def shared_recurring_public(legacy_state, view, today):
    """Marks/settles are tracking only; a retired receipt never refunds money."""
    if view is None:
        return public_financial_document(legacy_state)
    ob, summary = view.obligation, view.summary
    if legacy_state.get("due_date") != ob["original_due_date"]:
        conflict("La respuesta pertenece a otro vencimiento.")
    paid = summary.remaining == 0
    out = public_financial_document(legacy_state)
    out.update(expected=float(money(ob["actual_amount"])), paid=float(summary.paid),
               remaining=float(summary.remaining), partial=bool(summary.paid and not paid), overpaid=0.0,
               status="paid" if paid else "overdue" if ob["original_due_date"] < today.isoformat() else "pending",
               records=public_financial_document(sorted((r for r in view.records if not r.get("deleted")),
                                                        key=lambda r: r.get("created_at", ""))))
    return out


def shared_paid_events(views):
    """Unique verified real expenses for month summaries/calendar consumers.

    Dates come from the actual movement, not the mutable bill/recurrence dates.
    Returned documents are public copies; no receipts are counted as money.
    """
    events = {}
    for view in views:
        if view is None:
            continue
        for tx in view.movements:
            if tx["id"] in events:
                conflict("Un movimiento fue reclamado por más de una obligación.")
            events[tx["id"]] = public_financial_document(tx)
    return list(events.values())


async def read_shared_periods(database, recurring_id, *, expected_environment_id, effective_user, session):
    """Enumerate frozen periods, including periods removed from today's schedule."""
    _transaction(session)
    try:
        docs = await database.shared_obligations.find(
            {"user_id": effective_user, "recurring_id": identifier(recurring_id)}, session=session).to_list(None)
        if not docs and await has_managed_obligation(database, effective_user=effective_user, session=session,
                                                     recurring_id=recurring_id, whole_recurring=True):
            conflict("La recurrencia conserva historial R4 sin períodos verificables.")
        views = {}
        for doc in docs:
            due = day(doc.get("original_due_date")).isoformat()
            if due in views:
                conflict("Más de una identidad reclama el mismo período.")
            views[due] = await read_shared_view(database, recurring_id=recurring_id, original_due_date=due,
                expected_environment_id=expected_environment_id, effective_user=effective_user, session=session)
        return views
    except PyMongoError:
        raise HTTPException(503, "No se pudieron verificar los períodos compartidos.") from None


def shared_period_states(legacy_states, views, today):
    """Prepared common states for month summaries, occurrences and reminders."""
    states = {state["due_date"]: public_financial_document(state) for state in legacy_states}
    for due, view in views.items():
        base = states.get(due, {"due_date": due, "expected": 0, "paid": 0, "remaining": 0,
                                "status": "pending", "partial": False, "overpaid": 0, "records": []})
        states[due] = shared_recurring_public(base, view, today)
    return [states[due] for due in sorted(states)]


def shared_calendar_due(legacy_event, view, today):
    """Project one planned event; caller suppresses the matching recurring due.

    Real expenses remain separate movement events, counted exactly once. A paid
    obligation contributes no planned event, even after tracking was retired.
    """
    if view is None:
        return public_financial_document(legacy_event)
    if legacy_event.get("source") == "bill":
        matches = legacy_event.get("ref_id") == view.obligation["bill_id"]
    elif legacy_event.get("source") == "recurring":
        matches = legacy_event.get("ref_id") == view.obligation["recurring_id"]
    else:
        matches = False
    if not matches:
        conflict("El evento planificado pertenece a otra obligación.")
    if view.summary.remaining == 0:
        return None
    out = public_financial_document(legacy_event)
    due = view.obligation["original_due_date"]
    out.update(date=due, amount=float(view.summary.remaining), realized=False, counts_in_net=False,
               status="overdue" if due < today.isoformat() else "pending",
               partial=bool(view.summary.paid))
    return out


# 2D.2: task-local read snapshot; no public financial writer uses this context.
from contextvars import ContextVar
from functools import wraps
from pymongo import ReadPreference
from pymongo.read_concern import ReadConcern

_SHARED_READ = ContextVar("moneyflow_shared_read", default=None)
_READ_COLLECTIONS = ("shared_obligations", "bills", "recurring_payments", "bill_payments",
                     "recurring_payment_records", "transactions", "accounts", "categories",
                     "saving_goals", "goal_contributions", "debts")
_SHARED_FIELDS = ("_shared_obligation_id", "_shared_financial_state", "_shared_origin_receipt_id", "_shared_intent")


def _read_matches(doc, query):
    for field, value in query.items():
        if field == "$or":
            if not any(_read_matches(doc, part) for part in value):
                return False
            continue
        actual = doc.get(field)
        if isinstance(value, dict):
            for op, target in value.items():
                if op == "$exists":
                    matched = (field in doc) == target
                elif op == "$in":
                    matched = actual in target
                elif op == "$ne":
                    matched = actual != target
                elif op in ("$gte", "$lte", "$gt", "$lt"):
                    try:
                        matched = actual is not None and {"$gte": lambda: actual >= target,
                            "$lte": lambda: actual <= target, "$gt": lambda: actual > target,
                            "$lt": lambda: actual < target}[op]()
                    except TypeError:
                        matched = False  # Mongo range predicates use BSON type bracketing.
                else:
                    raise HTTPException(503, "Filtro de lectura snapshot no compatible.")
                if not matched:
                    return False
        elif actual != value:
            return False
    return True


def _read_project(doc, projection):
    if not projection:
        return deepcopy(doc)
    if any(value for key, value in projection.items() if key != "_id"):
        return {key: deepcopy(value) for key, value in doc.items()
                if projection.get(key) or (key == "_id" and projection.get(key, 1))}
    return {key: deepcopy(value) for key, value in doc.items() if projection.get(key, 1)}


class _ReadCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key, direction):
        self.docs.sort(key=lambda doc: (doc.get(key) is not None, doc.get(key)), reverse=direction == -1)
        return self

    async def to_list(self, length):
        return deepcopy(self.docs if length is None else self.docs[:length])

    def __aiter__(self):
        self.iterator = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return deepcopy(next(self.iterator))
        except StopIteration:
            raise StopAsyncIteration


class _ReadCollection:
    def __init__(self, docs):
        self.docs = docs

    def find(self, query, projection=None, *, session=None):
        return _ReadCursor([_read_project(doc, projection) for doc in self.docs if _read_matches(doc, query)])

    async def find_one(self, query, projection=None, *, session=None):
        doc = next((doc for doc in self.docs if _read_matches(doc, query)), None)
        return _read_project(doc, projection) if doc is not None else None


class _ReadSnapshot:
    def __init__(self, data, session=None):
        self.data = data
        self.session = session
        self.by_bill, self.by_period = {}, {}

    def __getattr__(self, collection):
        if collection not in self.data:
            raise HTTPException(503, "Colección no disponible en la lectura snapshot.")
        return _ReadCollection(self.data[collection])


async def _probe_shared_history(database, user, session=None):
    # Constant-sized probes, including provenance whose identity was lost.
    if await database.shared_obligations.find_one({"user_id": user}, session=session):
        return True
    query = {"user_id": user, "$or": [{field: {"$exists": True}} for field in _SHARED_FIELDS]}
    for collection in ("bills", "recurring_payments", "bill_payments", "recurring_payment_records", "transactions"):
        if await getattr(database, collection).find_one(query, session=session):
            return True
    return False


async def _load_shared_snapshot(database, expected, user, session):
    _transaction(session)
    data = {}
    for collection in _READ_COLLECTIONS:
        data[collection] = await getattr(database, collection).find({"user_id": user}, session=session).to_list(None)
    context = await database.moneyflow_metadata.find_one({"_id": "financial-context"}, session=session)
    data["moneyflow_metadata"] = [context] if context else []
    snapshot = _ReadSnapshot(data, session)
    scope = await _scope(snapshot, expected, user, session)
    for doc in data["shared_obligations"]:
        ob = validate_document(doc, scope)
        view = await read_shared_view(snapshot, bill_id=ob["bill_id"], expected_environment_id=expected,
                                      effective_user=user, session=session)
        bill = await snapshot.bills.find_one({"id": ob["bill_id"]})
        recurring = await snapshot.recurring_payments.find_one({"id": ob["recurring_id"]})
        if not bill or not recurring or bill.get("recurring_payment_id") != ob["recurring_id"]:
            conflict("La identidad compartida no conserva padres verificables.")
        for movement in view.movements:
            try:
                if not isinstance(movement.get("date"), str):
                    raise ValueError()
                datetime.fromisoformat(movement["date"].replace("Z", "+00:00"))
            except (ValueError, TypeError):
                conflict("La fecha del gasto real no permite un resumen verificable.")
        key = (ob["recurring_id"], ob["original_due_date"])
        if ob["bill_id"] in snapshot.by_bill or key in snapshot.by_period:
            conflict("La instantánea contiene identidades compartidas duplicadas.")
        snapshot.by_bill[ob["bill_id"]] = view
        snapshot.by_period[key] = view
    by_identity = {view.obligation["_id"]: view for view in snapshot.by_bill.values()}
    for collection in ("bills", "recurring_payments", "bill_payments", "recurring_payment_records", "transactions"):
        for doc in data[collection]:
            if any(field.startswith("_shared_") for field in doc):
                marker = doc.get("_shared_obligation_id")
                view = by_identity.get(marker) if isinstance(marker, str) else None
                if view is None:
                    conflict("Hay procedencia R4 sin una identidad verificable.")
                ob = view.obligation
                if collection == "bills":
                    valid = doc.get("id") == ob["bill_id"]
                elif collection == "recurring_payments":
                    valid = doc.get("id") == ob["recurring_id"]
                elif collection == "bill_payments":
                    valid = doc.get("bill_id") == ob["bill_id"] and doc.get("id") in {p["id"] for p in view.payments}
                elif collection == "recurring_payment_records":
                    valid = (doc.get("recurring_id") == ob["recurring_id"] and doc.get("due_date") == ob["original_due_date"]
                             and doc.get("id") in {r["id"] for r in view.records})
                else:
                    valid = doc.get("id") in view.summary.transaction_ids
                if not valid:
                    conflict("La procedencia R4 contradice el documento al que pertenece.")
    # Projection copy only: historical bills select/filter on the frozen due.
    for bill in data["bills"]:
        view = snapshot.by_bill.get(bill["id"])
        if view:
            if money(bill.get("amount")) != money(view.obligation["actual_amount"]):
                conflict("La factura conserva un importe incompatible con su identidad.")
            bill["due_date"] = view.obligation["original_due_date"]
    return snapshot


def read_database(database):
    """Read-only endpoint code uses cached documents only in a managed request."""
    return _SHARED_READ.get() or database


def current_shared_view(*, bill_id=None, recurring_id=None, due=None):
    snapshot = _SHARED_READ.get()
    if snapshot is None:
        return None
    return snapshot.by_bill.get(bill_id) if bill_id is not None else snapshot.by_period.get((recurring_id, due))


def current_shared_periods(recurring_id):
    snapshot = _SHARED_READ.get()
    return {} if snapshot is None else {due: view for (rid, due), view in snapshot.by_period.items() if rid == recurring_id}


async def shared_link_candidates(view):
    """Read-only restoration candidates, using the exact write-side proof.

    Never adopt unrelated expenses, match nearby dates or expose provenance.
    The GET wrapper owns the same snapshot transaction as this verification.
    """
    snapshot = _SHARED_READ.get()
    if snapshot is None:
        raise RuntimeError("Restoration candidates require the shared read snapshot")
    session = snapshot.session
    ob = view.obligation
    scope = Scope(ob["environment_id"], ob["user_id"], "single_user")
    bill = await snapshot.bills.find_one({"id": ob["bill_id"], "user_id": scope.user_id})
    recurring = await snapshot.recurring_payments.find_one({"id": ob["recurring_id"], "user_id": scope.user_id})
    if (not bill or not recurring or bill.get("deleted") or recurring.get("deleted")
            or bill.get("recurring_payment_id") != ob["recurring_id"]
            or money(bill.get("amount")) != money(ob["actual_amount"])):
        conflict("Los padres del seguimiento no pueden verificarse.")
    await _strict_payment_history(snapshot, ob, scope, session, view.summary)
    records = {record["transaction_id"]: record for record in view.records if record.get("transaction_id")}
    candidates = []
    for tx in view.movements:
        record = records.get(tx["id"])
        if not record or not record.get("deleted") or record.get("mode") != "link":
            continue
        await _verified_restore_event(snapshot, ob, scope, {"transaction_id": tx["id"]}, session, retired=True)
        for field, collection in (("account_id", "accounts"), ("category_id", "categories")):
            value = tx.get(field)
            if value:
                parent = await getattr(snapshot, collection).find_one({"id": value, "user_id": scope.user_id})
                if not parent or parent.get("deleted"):
                    conflict("Una referencia del movimiento no puede verificarse.")
        candidates.append(public_financial_document(tx))
    return sorted(candidates, key=lambda tx: (tx.get("date", ""), tx["id"]), reverse=True)[:10]


def shared_read_route(database, client, expected, user):
    """GET-only wrapper: probe absent history, otherwise one read-only snapshot.

    No feature activation, no indexes, no financial writes and no payment runner.
    ContextVar reset protects parallel requests and subsequent write handlers.
    """
    def decorate(endpoint):
        @wraps(endpoint)
        async def read(*args, **kwargs):
            try:
                if not await _probe_shared_history(database(), user()):
                    result = await endpoint(*args, **kwargs)
                    # If R4 appeared during ordinary reads, discard and reread.
                    if not await _probe_shared_history(database(), user()):
                        return public_financial_document(result)
                async with await client().start_session() as session:
                    async with session.start_transaction(read_concern=ReadConcern("snapshot"), read_preference=ReadPreference.PRIMARY):
                        snapshot = await _load_shared_snapshot(database(), expected(), user(), session)
                        token = _SHARED_READ.set(snapshot)
                        try:
                            return public_financial_document(await endpoint(*args, **kwargs))
                        finally:
                            _SHARED_READ.reset(token)
            except PyMongoError:
                raise HTTPException(503, "No se pudo verificar la lectura financiera compartida.") from None
        return read
    return decorate


async def generate_next_shared_bill(database, obligation, result, *, effective_user, session, add_period, occurrences):
    """Same transaction as money. Durable creation proof survives later edits.

    Never adopts old future bills or repairs missing historical generation.
    A legitimate deletion may remove a future bill; proof prevents recreation.
    """
    _transaction(session)
    schedule = bill_schedule(obligation)
    bill = await database.bills.find_one({"id": obligation["bill_id"], "user_id": effective_user}, session=session)
    canonical = await database.shared_obligations.find_one({"_id": obligation["_id"], "user_id": effective_user}, session=session)
    if not bill or not canonical or bill.get("recurring_payment_id") != obligation["recurring_id"]:
        conflict("La factura original no conserva su vínculo verificable.")
    if schedule["frequency"] == "once":
        if bill.get("next_bill_id") or canonical.get("next_bill_generation"):
            conflict("Una factura once conserva un siguiente período incompatible.")
        return None
    try:
        due = add_period(day(schedule["original_due_date"]), schedule["frequency"], schedule["anchor_day"]).isoformat()
    except (ValueError, OverflowError):
        conflict("La programación del siguiente período no es verificable.")
    next_id = str(uuid5(NAMESPACE_URL, "bill-next:"+obligation["bill_id"]))
    proof = dict(id=next_id, source_bill_id=obligation["bill_id"], source_obligation_id=obligation["_id"],
                 due_date=due, frequency=schedule["frequency"], anchor_day=schedule["anchor_day"], series_id=schedule["series_id"])
    previous = canonical.get("next_bill_generation")
    if previous is not None:
        if previous != proof or bill.get("next_bill_id") not in (None, next_id):
            conflict("El historial de generación no coincide con la programación original.")
        target = await database.bills.find_one({"id": next_id}, session=session)
        if target:
            if target.get("user_id") != effective_user or target.get("_bill_generation_origin") != proof:
                conflict("El siguiente período no conserva su procedencia verificable.")
            return None if target.get("deleted") else next_id
        if bill.get("next_bill_id"):
            conflict("La factura conserva un enlace a un siguiente período inexistente.")
        return None  # deleted through a legitimate route; never recreate it
    if bill.get("next_bill_id"):
        conflict("El siguiente período heredado carece de prueba de generación R4.")
    if result.summary.remaining != 0:
        return None
    if not result.created:
        conflict("El pago recuperado perdió su siguiente período; no se reparará automáticamente.")
    if await database.bills.find_one({"user_id": effective_user, "series_id": schedule["series_id"],
                                     "due_date": due}, session=session):
        conflict("Existe un siguiente período no vinculado inequívocamente; no se adoptará.")
    for field in ("_id", "id"):
        if await database.bills.find_one({field: next_id}, session=session):
            conflict("El identificador del siguiente período pertenece a otro documento.")
    keep = ("name", "provider", "amount", "category_id", "account_id", "reminder_days",
            "description", "recurring_payment_id", "icon", "color")
    fields = {key: bill.get(key) for key in keep}
    if fields.get("category_id"):
        category = await database.categories.find_one({"id": fields["category_id"], "user_id": effective_user}, session=session)
        if not category or category.get("type") != "expense" or category.get("is_group") or category.get("deleted"):
            conflict("La categoría copiada al siguiente período no es una referencia de gasto válida.")
    await coordinate(database, effective_user, fields, session)
    now = datetime.now(timezone.utc).isoformat()
    next_bill = dict(fields, _id=next_id, id=next_id, user_id=effective_user,
        series_id=schedule["series_id"], frequency=schedule["frequency"], anchor_day=schedule["anchor_day"],
        due_date=due, next_bill_id=None, created_at=now, updated_at=now, _bill_generation_origin=proof)
    recurring = await database.recurring_payments.find_one({"id": obligation["recurring_id"], "user_id": effective_user}, session=session)
    # A copied recurrence must represent the exact next bill period. Do not
    # manufacture a nearby association or detach that reference silently.
    resolve_documents(next_bill, recurring, Scope(obligation["environment_id"], effective_user), occurrences=occurrences)
    await database.bills.insert_one(next_bill, session=session)
    # Reserve the fresh period in the same transaction. Its guards must not
    # allow a downgrade to legacy money merely because it has no payments yet.
    await create_shared_obligation(database, next_id, expected_environment_id=obligation["environment_id"],
        effective_user=effective_user, session=session, occurrences=occurrences)
    await database.bills.update_one({"id": obligation["bill_id"], "user_id": effective_user},
                                    {"$set": {"next_bill_id": next_id}}, session=session)
    await database.shared_obligations.update_one({"_id": obligation["_id"], "user_id": effective_user},
                                                {"$set": {"next_bill_generation": proof}}, session=session)
    return next_id


async def dispatch_shared_payment(database, settings, *, origin, parent_id, receipt_id, transaction_id,
                                  payload, effective_user, session, occurrences, add_period,
                                  recompute_account_balance, effective_date, normalized_due=None):
    """Exclusive public POST adapter. None dispatches only unmanaged legacy work.

    Disabled/unknown managed work is left to the existing mandatory legacy guard.
    Once selected, any error propagates: no fallback, no nested transactions.
    """
    _transaction(session)
    if settings is None or getattr(settings, "shared_obligations_enabled", False) is not True:
        return None
    if origin == "bill":
        stored = await database.shared_obligations.find({"user_id": effective_user, "bill_id": parent_id}, session=session).to_list(None)
        bill = await database.bills.find_one({"id": parent_id, "user_id": effective_user}, session=session)
        if not stored and (not bill or not bill.get("recurring_payment_id")):
            return None
        bid = parent_id
    else:
        due = day(normalized_due).isoformat()
        stored = await database.shared_obligations.find({"user_id": effective_user, "recurring_id": parent_id,
                                                        "original_due_date": due}, session=session).to_list(None)
        if len(stored) > 1:
            conflict("Más de una obligación reclama el período.")
        if stored:
            bid = stored[0].get("bill_id")
        else:
            candidates = await database.bills.find({"user_id": effective_user, "recurring_payment_id": parent_id,
                                                    "due_date": due}, session=session).to_list(None)
            if not candidates:
                return None  # independent period; mandatory legacy guard still applies
            if len(candidates) != 1:
                conflict("No hay una única factura verificable para el período.")
            bid = candidates[0]["id"]
    scope = await require_activation(database, settings, effective_user=effective_user, session=session)
    administrative = origin == "recurring" and payload.get("mode") in ("link", "mark")
    if not administrative and not payload.get("account_id"):
        raise HTTPException(422, "Selecciona la cuenta de origen para registrar el gasto.")
    if origin == "recurring" and not administrative:
        try:
            money(payload.get("amount"))
        except HTTPException:
            raise HTTPException(422, "El monto pagado debe ser mayor que cero y finito.") from None
    if stored:
        if len(stored) != 1:
            conflict("Más de una identidad reclama la factura.")
        ob = validate_document(stored[0], scope)
    else:
        ob = await create_shared_obligation(database, bid, expected_environment_id=settings.expected_financial_environment_id,
            effective_user=effective_user, session=session, occurrences=occurrences)
    if administrative:
        return await register_shared_tracking(database, ob, scope, receipt_id=receipt_id, payload=payload,
            effective_date=effective_date, session=session)
    bill_schedule(ob)  # reject incomplete old identities BEFORE the financial write
    result = await register_shared_payment(database, ob["_id"], origin=origin, receipt_id=receipt_id,
        transaction_id=transaction_id, payload=payload, expected_environment_id=settings.expected_financial_environment_id,
        effective_user=effective_user, session=session, recompute_account_balance=recompute_account_balance,
        effective_date=effective_date, public_request=True)
    next_id = await generate_next_shared_bill(database, ob, result, effective_user=effective_user,
                                             session=session, add_period=add_period, occurrences=occurrences)
    if origin == "bill":
        fields = ("id", "user_id", "bill_id", "series_id", "amount", "date", "account_id", "notes",
                  "transaction_id", "recurring_record_id", "created_at")
        public = {field: result.bill_payment.get(field) for field in fields}
        if result.created:
            public["next_bill_id"] = next_id  # preserve legacy first-response vs replay shape
    else:
        fields = ("id", "user_id", "recurring_id", "due_date", "mode", "amount", "expected_amount", "date",
                  "account_id", "category_id", "notes", "transaction_id", "settles", "created_at")
        public = {field: result.recurring_record.get(field) for field in fields}
    return public_financial_document(public)


async def dispatch_shared_change(database, settings, *, origin, receipt, effective_user,
                                 session, recompute_account_balance):
    """DELETE adapter: select before legacy guards/no-op for retired receipts.

    Bill DELETE annuls money; recurring expense annuls, recurring link withdraws
    only tracking. The immutable source capsule resolves complementary IDs.
    No generation, repair, adoption or new financial intent occurs here.
    """
    _transaction(session)
    if settings is None or getattr(settings, "shared_obligations_enabled", False) is not True:
        return None  # mandatory legacy guard blocks managed/reserved history
    if not receipt or not any(key.startswith("_shared_") for key in receipt):
        return None  # legacy guard also detects inverse managed references
    scope = await require_activation(database, settings, effective_user=effective_user, session=session)
    obid = identifier(receipt.get("_shared_obligation_id"))
    if origin == "recurring" and receipt.get("mode") == "mark":
        _, ob = await _canonical_payment_obligation(database, obid, settings.expected_financial_environment_id, effective_user, session)
        if not _verified_mark(ob, receipt):
            conflict("La marca administrativa no puede verificarse.")
        if not receipt.get("deleted"):
            await _lock_payment_obligation(database, ob, scope, session)
            await coordinate(database, scope.user_id, {"bill_id": ob["bill_id"], "recurring_id": ob["recurring_id"]}, session)
            await database.recurring_payment_records.update_one({"id": receipt["id"], "user_id": scope.user_id},
                {"$set": {"deleted": True}}, session=session)
        return {"ok": True}
    capsule = receipt.get("_shared_intent")
    if not isinstance(capsule, dict):
        conflict("El recibo compartido perdió su intención original.")
    source_origin, source_id = capsule.get("origin"), capsule.get("receipt_id")
    pid, rid = _event_ids(source_origin, source_id)
    if receipt.get("user_id") != scope.user_id or receipt.get("id") != (pid if origin == "bill" else rid):
        conflict("El recibo no corresponde al origen financiero verificable.")
    if origin == "bill":
        action = "annul"
    elif origin == "recurring" and receipt.get("mode") == ("link" if source_origin == "bill" else "expense"):
        action = "annul" if receipt["mode"] == "expense" else "retire_recurring"
    else:
        conflict("El seguimiento compartido no tiene una transición verificable.")
    await change_shared_payment(database, obid, origin=source_origin, receipt_id=source_id, action=action,
        expected_environment_id=settings.expected_financial_environment_id, effective_user=effective_user,
        session=session, recompute_account_balance=recompute_account_balance)
    # Keep any generated future bill, reservation and generation proof untouched.
    # Re-paying this original period cannot generate a second future bill.
    return {"ok": True}


_TRACKING_PUBLIC = ("id", "user_id", "recurring_id", "due_date", "mode", "amount", "expected_amount",
                    "date", "account_id", "category_id", "notes", "transaction_id", "settles", "created_at")


def _tracking_capsule(ob, receipt_id, payload):
    identifier(receipt_id)
    if not isinstance(payload, dict) or payload.get("mode") not in ("mark", "link"):
        conflict("Intención administrativa inválida.")
    try:
        due = date.fromisoformat(payload["due_date"][:10]).isoformat()
        encoded = json.dumps({"rid": ob["recurring_id"], **payload}, sort_keys=True, allow_nan=False)
    except (KeyError, ValueError, TypeError):
        conflict("Payload administrativo no verificable.")
    if due != ob["original_due_date"]:
        conflict("El seguimiento pertenece a otro período.")
    return dict(environment_id=ob["environment_id"], user_id=ob["user_id"], obligation_id=ob["_id"],
                receipt_id=receipt_id, payload=deepcopy(payload), fingerprint=hashlib.sha256(encoded.encode()).hexdigest())


def _verified_mark(ob, record):
    capsule = record.get("_shared_tracking_intent")
    if capsule is None:
        return False
    if not isinstance(capsule, dict) or capsule != _tracking_capsule(ob, record["id"], capsule.get("payload")):
        conflict("La intención de marca fue alterada.")
    payload = capsule["payload"]
    if (payload["mode"] != "mark" or record.get("mode") != "mark" or record.get("transaction_id")
            or record.get("bill_payment_id") or record.get("_shared_financial_state")
            or record.get("_shared_obligation_id") != ob["_id"] or record.get("user_id") != ob["user_id"]
            or record.get("recurring_id") != ob["recurring_id"] or record.get("due_date") != ob["original_due_date"]
            or money(record.get("amount")) != money(payload.get("amount")) or record.get("settles") is not False
            or record.get("account_id") != payload.get("account_id") or record.get("category_id") != payload.get("category_id")
            or record.get("notes") != ((payload.get("notes") or "").strip()[:200] or None)
            or record.get("request_fingerprint") != capsule["fingerprint"]):
        conflict("La marca no corresponde a su intención administrativa.")
    return True


async def register_shared_tracking(database, ob, scope, *, receipt_id, payload, effective_date, session):
    """Administrative journal only; never create money, adopt history or recalculate balances."""
    bill = await database.bills.find_one({"id": ob["bill_id"], "user_id": scope.user_id}, session=session)
    recurring = await database.recurring_payments.find_one({"id": ob["recurring_id"], "user_id": scope.user_id}, session=session)
    if (not bill or not recurring or bill.get("deleted") or recurring.get("deleted")
            or bill.get("recurring_payment_id") != ob["recurring_id"] or money(bill.get("amount")) != money(ob["actual_amount"])):
        conflict("Los padres de seguimiento no son verificables.")
    capsule = _tracking_capsule(ob, receipt_id, payload)
    journal_id = str(uuid5(NAMESPACE_URL, "shared-tracking-intent:"+receipt_id))
    indexes = await database.shared_tracking_intents.index_information()
    if tuple(indexes.get("_id_", {}).get("key", ())) != (("_id", 1),):
        raise HTTPException(503, "Falta el journal administrativo provisionado; no se escribirá.")
    previous = await database.shared_tracking_intents.find_one({"_id": journal_id}, session=session)
    mode = payload["mode"]
    if previous and previous.get("capsule") != capsule:
        conflict("La Idempotency-Key administrativa ya se utilizó con otros datos.")
    # Detect cross-mode reuse of the existing public recurring-record namespace.
    collision = await database.recurring_payment_records.find_one({"id": receipt_id}, session=session)
    if collision and (mode != "mark" or not _verified_mark(ob, collision)):
        conflict("El ID ya pertenece a otra intención.")
    if previous:
        target = await database.recurring_payment_records.find_one({"id": previous.get("target_id")}, session=session)
        if not target or target.get("deleted"):
            conflict("El seguimiento fue retirado; no se restaura automáticamente en un reintento.")
        if mode == "mark":
            if not _verified_mark(ob, target):
                conflict("Marca no verificable.")
        else:
            await _verified_restore_event(database, ob, scope, payload, session, retired=False)
        public = {field: target.get(field) for field in _TRACKING_PUBLIC}
        if public != previous.get("response"):
            conflict("La respuesta administrativa original ya no coincide con el seguimiento.")
        return public_financial_document(public)
    if collision:
        conflict("La marca perdió su registro de idempotencia.")
    await _strict_payment_history(database, ob, scope, session, await _payment_summary(database, ob, scope, session))
    ob = await _lock_payment_obligation(database, ob, scope, session)
    await coordinate(database, scope.user_id, {"bill_id": ob["bill_id"], "recurring_id": ob["recurring_id"]}, session)
    if mode == "mark":
        if payload.get("transaction_id"):
            conflict("Una marca administrativa no puede referenciar un movimiento.")
        try:
            amount = _native_amount(payload.get("amount"))
        except HTTPException:
            raise HTTPException(422, "El monto administrativo debe ser mayor que cero y finito.") from None
        if payload.get("category_id"):
            category = await database.categories.find_one({"id": payload["category_id"], "user_id": scope.user_id}, session=session)
            if not category or category.get("type") != "expense" or category.get("is_group") or category.get("deleted"):
                raise HTTPException(422, "La categoría debe ser una categoría de gasto existente.")
        await coordinate(database, scope.user_id, {"account_id": payload.get("account_id"), "category_id": payload.get("category_id")}, session)
        record = dict(_id=receipt_id,id=receipt_id,user_id=scope.user_id,recurring_id=ob["recurring_id"],due_date=ob["original_due_date"],
            mode="mark",amount=amount,expected_amount=_native_amount(ob["actual_amount"]),date=effective_date,
            account_id=payload.get("account_id"),category_id=payload.get("category_id"),notes=(payload.get("notes") or "").strip()[:200] or None,
            transaction_id=None,settles=False,created_at=datetime.now(timezone.utc).isoformat(),
            _shared_obligation_id=ob["_id"],_shared_tracking_intent=capsule,request_fingerprint=capsule["fingerprint"])
        await database.recurring_payment_records.insert_one(record, session=session)
    else:
        event = await _verified_restore_event(database, ob, scope, payload, session, retired=True)
        record = event.recurring_record
        await database.recurring_payment_records.update_one({"id":record["id"],"user_id":scope.user_id}, {"$set":{"deleted":False}},session=session)
        await database.bill_payments.update_one({"id":event.bill_payment["id"],"user_id":scope.user_id}, {"$set":{"recurring_record_id":record["id"]}},session=session)
        await database.transactions.update_one({"id":event.transaction_id,"user_id":scope.user_id},
            {"$set":{"recurring_payment_id":ob["recurring_id"],"recurring_record_id":record["id"]}},session=session)
        record = await database.recurring_payment_records.find_one({"id":record["id"]},session=session)
        await _payment_summary(database, ob, scope, session)
    public = {field:record.get(field) for field in _TRACKING_PUBLIC}
    await database.shared_tracking_intents.insert_one(dict(_id=journal_id,user_id=scope.user_id,capsule=capsule,
        target_id=record["id"],response=deepcopy(public)),session=session)
    return public_financial_document(public)


async def _verified_restore_event(database, ob, scope, payload, session, *, retired):
    tx = await database.transactions.find_one({"id":identifier(payload.get("transaction_id")),"user_id":scope.user_id},session=session)
    if not tx or tx.get("_shared_obligation_id") != ob["_id"]:
        conflict("El movimiento no demuestra pertenecer a esta obligación R4.")
    capsule = tx.get("_shared_intent")
    if not isinstance(capsule, dict) or capsule.get("origin") != "bill":
        conflict("Solo puede restaurarse el seguimiento link original de un pago R4 de factura.")
    event = await _read_event(database,ob,scope,capsule["origin"],capsule.get("receipt_id"),session)
    if (not event or event.financial_state != "active" or event.bill_payment.get("deleted")
            or bool(event.recurring_record.get("deleted")) != retired or event.recurring_record.get("mode") != "link"):
        conflict("El seguimiento no está en el estado verificable requerido.")
    for field in ("account_id","category_id"):
        if payload.get(field) is not None and payload[field] != tx.get(field):
            conflict("La cuenta o categoría no coincide con el movimiento original.")
    if payload.get("amount") is not None and money(payload["amount"]) != money(tx["amount"]):
        conflict("El importe no coincide con el movimiento original.")
    return event


def _reconciliation_receipt(origin, receipt):
    fields = ("id", "user_id", "amount", "account_id", "date", "transaction_id")
    fields += ("bill_id",) if origin == "bill" else ("recurring_id", "due_date", "mode")
    public = {field: receipt.get(field) for field in fields}
    public["amount"] = _native_amount(receipt.get("amount"))
    return public


async def _verify_reconciliation_event(database, event, scope, session):
    """Original request proof, including dates/notes and deterministic money ID."""
    capsule = event.bill_payment["_shared_intent"]
    original = capsule["payload"]
    expected_tid = str(uuid5(NAMESPACE_URL, ("bill-payment-movement:" if capsule["origin"] == "bill" else
        "recurring-record-movement:")+capsule["receipt_id"]))
    if event.transaction_id != expected_tid:
        conflict("El movimiento no corresponde a la intención original.")
    receipts = (event.bill_payment, event.recurring_record)
    if any(receipt.get("notes") != ((original.get("notes") or "").strip()[:200] or None) for receipt in receipts):
        conflict("Los recibos no conservan la solicitud original.")
    dates = [datetime.fromisoformat(receipt["date"].replace("Z", "+00:00")) for receipt in receipts]
    if dates[0] != dates[1] or (original.get("date") and dates[0] != datetime.fromisoformat(original["date"].replace("Z", "+00:00"))):
        conflict("Las fechas no conservan la solicitud original.")
    if event.financial_state == "active":
        tx = await database.transactions.find_one({"id": event.transaction_id, "user_id": scope.user_id}, session=session)
        if not tx or datetime.fromisoformat(tx["date"].replace("Z", "+00:00")) != dates[0] or tx.get("notes") != receipts[0].get("notes"):
            conflict("El movimiento no conserva la solicitud original.")


async def reconcile_payment_intent(database, *, origin, parent_id, key, payload,
                                   expected_environment_id, effective_user, session):
    """Verify an original intent in a caller-owned snapshot; absolutely no writes.

    Absence is only absence in this snapshot, never proof of an aborted/in-flight
    transaction. Legacy tombstones without explicit financial provenance remain
    unverifiable. Neither lookup activates R4 or adopts historical documents.
    """
    scope = await _scope(database, expected_environment_id, effective_user, session)
    namespace = "bill-payment" if origin == "bill" else "recurring-record"
    receipt_id = str(uuid5(NAMESPACE_URL, f"{effective_user}:{namespace}:{parent_id}:{key}"))
    try:
        fingerprint = hashlib.sha256(json.dumps({"bid" if origin == "bill" else "rid": parent_id, **payload},
                                               sort_keys=True, allow_nan=False).encode()).hexdigest()
    except (ValueError, TypeError):
        raise HTTPException(422, "El payload original no es válido.") from None

    def result(status, state="unknown", receipt=None, due=None):
        return dict(version=1, status=status, financial_state=state,
                    original_request_matches=True if status in {"matched", "cancelled", "tracking_removed"} else False if status == "discrepancy" else None,
                    environment_id=scope.environment_id, user_id=scope.user_id, origin=origin,
                    parent_id=parent_id, original_due_date=due,
                    receipt=_reconciliation_receipt(origin, receipt) if receipt else None)

    collection = database.bill_payments if origin == "bill" else database.recurring_payment_records
    receipts = await collection.find({"id": receipt_id, "user_id": scope.user_id}, session=session).to_list(2)
    if len(receipts) > 1:
        return result("unverifiable")
    receipt = receipts[0] if receipts else None
    journal = None
    if origin == "recurring":
        journal = await database.shared_tracking_intents.find_one(
            {"_id": str(uuid5(NAMESPACE_URL, "shared-tracking-intent:"+receipt_id)), "user_id": scope.user_id}, session=session)
    if not receipt and not journal:
        pid, rid = _event_ids(origin, receipt_id)
        tid = str(uuid5(NAMESPACE_URL, ("bill-payment-movement:" if origin == "bill" else "recurring-record-movement:")+receipt_id))
        for target, query in ((database.bill_payments, {"id": pid}),
                              (database.recurring_payment_records, {"id": rid}),
                              (database.transactions, {"id": tid}),
                              (database.transactions, {"bill_payment_id" if origin == "bill" else "recurring_record_id": receipt_id})):
            if await target.find_one(dict(query, user_id=scope.user_id), session=session):
                return result("unverifiable")
        return result("not_found")
    saved = journal.get("capsule", {}) if journal else receipt
    if not isinstance(saved, dict) or (journal and payload.get("mode") == "link" and receipt):
        return result("unverifiable")
    saved_fingerprint = saved.get("fingerprint") if journal else receipt.get("request_fingerprint")
    if not saved_fingerprint:
        return result("unverifiable")
    if saved_fingerprint != fingerprint:
        return result("discrepancy")
    try:
        obid = saved.get("obligation_id") if journal else receipt.get("_shared_obligation_id")
        if obid:
            ob = await database.shared_obligations.find_one({"_id": obid, "user_id": scope.user_id}, session=session)
            ob = validate_document(ob, scope)
            if (origin == "bill" and ob["bill_id"] != parent_id) or (origin == "recurring" and (
                    ob["recurring_id"] != parent_id or day(payload["due_date"][:10]).isoformat() != ob["original_due_date"])):
                return result("discrepancy")
            summary = await _payment_summary(database, ob, scope, session)
            await _strict_payment_history(database, ob, scope, session, summary)
            if journal:
                if saved != _tracking_capsule(ob, receipt_id, payload):
                    return result("unverifiable")
                target = await database.recurring_payment_records.find_one(
                    {"id": journal.get("target_id"), "user_id": scope.user_id}, session=session)
                if not target:
                    return result("unverifiable")
                public = {field: target.get(field) for field in _TRACKING_PUBLIC}
                if public != journal.get("response"):
                    return result("unverifiable")
                if payload["mode"] == "mark":
                    if target["id"] != receipt_id or not _verified_mark(ob, target):
                        return result("unverifiable")
                    if payload.get("date") and datetime.fromisoformat(target["date"].replace("Z", "+00:00")) != datetime.fromisoformat(payload["date"].replace("Z", "+00:00")):
                        return result("unverifiable")
                    return result("tracking_removed" if target.get("deleted") else "matched", "none", target, ob["original_due_date"])
                if payload["mode"] != "link" or target.get("mode") != "link":
                    return result("unverifiable")
                capsule = target.get("_shared_intent") or {}
                if capsule.get("origin") != "bill" or payload.get("transaction_id") != target.get("transaction_id"):
                    return result("unverifiable")
                event = await _read_event(database, ob, scope, "bill", capsule.get("receipt_id"), session, summary)
                if not event or event.recurring_record["id"] != target["id"]:
                    return result("unverifiable")
                await _verify_reconciliation_event(database, event, scope, session)
                if event.financial_state == "annulled":
                    return result("cancelled", "annulled", target, ob["original_due_date"])
                return result("tracking_removed" if target.get("deleted") else "matched", "active", target, ob["original_due_date"])
            capsule = receipt.get("_shared_intent") or {}
            if capsule.get("origin") != origin or capsule.get("receipt_id") != receipt_id or capsule.get("payload") != payload:
                return result("unverifiable")
            event = await _read_event(database, ob, scope, origin, receipt_id, session, summary)
            if not event:
                return result("unverifiable")
            await _verify_reconciliation_event(database, event, scope, session)
            if event.financial_state == "annulled":
                return result("cancelled", "annulled", receipt, ob["original_due_date"])
            return result("tracking_removed" if receipt.get("deleted") else "matched", "active", receipt, ob["original_due_date"])
        # Legacy confirmation requires the original stored hash AND a complete
        # active graph. Missing money plus a deleted flag is not annulment proof.
        field = "bill_id" if origin == "bill" else "recurring_id"
        if receipt.get(field) != parent_id:
            return result("discrepancy")
        if any(name.startswith("_shared_") for name in receipt) or journal:
            return result("unverifiable")
        if receipt.get("deleted"):
            return result("unverifiable")
        parent = await (database.bills if origin == "bill" else database.recurring_payments).find_one(
            {"id": parent_id, "user_id": scope.user_id}, session=session)
        if not parent or parent.get("deleted"):
            return result("unverifiable")
        mode = "expense" if origin == "bill" else payload["mode"]
        due = None if origin == "bill" else day(payload["due_date"][:10]).isoformat()
        if origin == "recurring" and (receipt.get("due_date") != due or receipt.get("mode") != mode):
            return result("unverifiable")
        if mode != "link" and (money(receipt.get("amount")) != money(payload.get("amount"))
                               or receipt.get("account_id") != payload.get("account_id")):
            return result("unverifiable")
        if receipt.get("notes") != ((payload.get("notes") or "").strip()[:200] or None):
            return result("unverifiable")
        if mode != "link" and payload.get("date") and datetime.fromisoformat(receipt["date"].replace("Z", "+00:00")) != datetime.fromisoformat(payload["date"].replace("Z", "+00:00")):
            return result("unverifiable")
        tx = await (check_bill_payment if origin == "bill" else check_record)(database, scope.user_id, receipt, session)
        if mode == "mark":
            if tx or receipt.get("transaction_id"):
                return result("unverifiable")
            return result("matched", "none", receipt, due)
        if not tx or tx.get("user_id") != scope.user_id or tx.get("deleted") or tx.get("date") != receipt.get("date"):
            return result("unverifiable")
        account = await database.accounts.find_one({"id": tx.get("account_id"), "user_id": scope.user_id}, session=session)
        if not account or account.get("deleted"):
            return result("unverifiable")
        expected_tid = payload.get("transaction_id") if mode == "link" else str(uuid5(NAMESPACE_URL,
            ("bill-payment-movement:" if origin == "bill" else "recurring-record-movement:")+receipt_id))
        if tx["id"] != expected_tid:
            return result("unverifiable")
        if len(await database.transactions.find({"id": expected_tid, "user_id": scope.user_id}, session=session).to_list(2)) != 1:
            return result("unverifiable")
        return result("matched", "active", receipt, due)
    except HTTPException as error:
        if error.status_code not in (409, 422):
            raise
        return result("unverifiable")
    except (KeyError, ValueError, TypeError, AttributeError, DecimalException):
        return result("unverifiable")


async def shared_parent_context(database, settings, *, origin, parent_id, effective_user, session):
    """Select managed parents only; disabled work remains blocked by legacy guards."""
    _transaction(session)
    if settings is None or getattr(settings, "shared_obligations_enabled", False) is not True:
        return None
    lookup = dict(bill_id=parent_id) if origin == "bill" else dict(recurring_id=parent_id, whole_recurring=True)
    if not await has_managed_obligation(database, effective_user=effective_user, session=session, **lookup):
        return None
    scope = await require_activation(database, settings, effective_user=effective_user, session=session)
    query = dict(user_id=effective_user, **({"bill_id":parent_id} if origin=="bill" else {"recurring_id":parent_id}))
    docs = await database.shared_obligations.find(query,session=session).to_list(None)
    if not docs or (origin=="bill" and len(docs)!=1):
        conflict("El padre gestionado no tiene identidades inequívocas.")
    obligations=[]
    for doc in sorted(docs,key=lambda entry:entry.get("_id", "")):
        ob=validate_document(doc,scope)
        bill_schedule(ob)
        summary=await _payment_summary(database,ob,scope,session)
        await _strict_payment_history(database,ob,scope,session,summary)
        bill=await database.bills.find_one({"id":ob["bill_id"],"user_id":effective_user},session=session)
        rp=await database.recurring_payments.find_one({"id":ob["recurring_id"],"user_id":effective_user},session=session)
        if (not bill or not rp or bill.get("deleted") or rp.get("deleted") or bill.get("recurring_payment_id")!=ob["recurring_id"]
                or money(bill.get("amount"))!=money(ob["actual_amount"])):
            conflict("Los padres comprometidos no son verificables.")
        if bill.get("due_date")!=ob["original_due_date"] or bill.get("frequency")!=bill_schedule(ob)["frequency"]:
            conflict("La programación pública contradice la reserva histórica.")
        # Same lock order as payments: obligation BEFORE parent validation writes.
        ob=await _lock_payment_obligation(database,ob,scope,session)
        obligations.append((ob,summary,bill,rp))
    return scope,obligations


async def _future_generation_compatible(database, ob, bill, recurring, *, occurrences, add_period, session):
    """Read-only prospective validation. Never generate, modify or adopt a child."""
    schedule=bill_schedule(ob)
    proof=ob.get("next_bill_generation")
    if schedule["frequency"]=="once":
        if proof or bill.get("next_bill_id"):
            conflict("Una factura once conserva generación incompatible.")
        return
    due=add_period(day(ob["original_due_date"]),schedule["frequency"],schedule["anchor_day"]).isoformat()
    next_id=str(uuid5(NAMESPACE_URL,"bill-next:"+ob["bill_id"]))
    expected=dict(id=next_id,source_bill_id=ob["bill_id"],source_obligation_id=ob["_id"],due_date=due,
                  frequency=schedule["frequency"],anchor_day=schedule["anchor_day"],series_id=schedule["series_id"])
    if proof is not None:
        target=await database.bills.find_one({"id":next_id,"user_id":ob["user_id"]},session=session)
        reserved=await database.shared_obligations.find_one({"bill_id":next_id,"user_id":ob["user_id"]},session=session)
        if (proof!=expected or bill.get("next_bill_id")!=next_id or not target or target.get("deleted")
                or target.get("_bill_generation_origin")!=proof or not reserved):
            conflict("La generación comprometida no puede verificarse; no se reparará.")
        validate_document(reserved,Scope(ob["environment_id"],ob["user_id"]))
        return  # Existing child is independent; never propagate edits to it.
    if bill.get("next_bill_id"):
        conflict("El siguiente período no conserva su prueba original.")
    candidate=dict(bill,due_date=due,frequency=schedule["frequency"],anchor_day=schedule["anchor_day"],id=next_id)
    resolve_documents(candidate,recurring,Scope(ob["environment_id"],ob["user_id"]),occurrences=occurrences)
    # Generation copies defaults; validate them now, not when a payment completes.
    for field,collection in (("account_id","accounts"),("category_id","categories")):
        value=bill.get(field)
        if value:
            parent=await getattr(database,collection).find_one({"id":value,"user_id":ob["user_id"]},session=session)
            if not parent or parent.get("deleted") or (field=="category_id" and (parent.get("type")!="expense" or parent.get("is_group"))):
                conflict("Una referencia copiada impediría completar la obligación.")


async def edit_shared_bill(database, context, fields, *, session, occurrences, add_period):
    scope,entries=context
    ob,summary,bill,recurring=entries[0]
    if fields.get("recurring_payment_id")!=ob["recurring_id"] or fields["due_date"]!=bill["due_date"] or fields["frequency"]!=bill["frequency"]:
        conflict("La factura reservada no permite reasignar su vínculo ni programación.")
    amount=money(fields["amount"])
    if amount<summary.paid:
        conflict("El importe real no puede ser inferior al dinero ya pagado.")
    proposed=dict(bill,**fields)
    await _future_generation_compatible(database,ob,proposed,recurring,occurrences=occurrences,add_period=add_period,session=session)
    await coordinate(database,scope.user_id,{"bill_id":ob["bill_id"],"recurring_id":ob["recurring_id"]},session)
    await database.shared_obligations.update_one({"_id":ob["_id"]}, {"$set":{"actual_amount":_stored_money(amount)}},session=session)
    await database.bills.update_one({"id":bill["id"],"user_id":scope.user_id},
        {"$set":dict(fields,updated_at=datetime.now(timezone.utc).isoformat())},session=session)
    return public_financial_document(await database.bills.find_one({"id":bill["id"],"user_id":scope.user_id},session=session))


async def edit_shared_recurring(database, context, fields, version, *, session, today, occurrences, add_period):
    scope,entries=context
    rp=entries[0][3]
    versions=deepcopy(rp.get("versions") or [])
    if not versions:
        conflict("Falta programación histórica verificable.")
    changed=any(versions[-1].get(key)!=version.get(key) for key in ("frequency","start_date","due_day","amount"))
    recurring_bills=any(bill_schedule(entry[0])["frequency"]!="once" for entry in entries)
    if fields.get("variable")!=rp.get("variable",False):
        conflict("El cambio de modalidad requiere una política de períodos separada.")
    if recurring_bills and (changed or not _same_optional_reference(fields.get("end_date"),rp.get("end_date"))):
        conflict("La programación debe conservar la generación periódica comprometida.")
    committed=[entry[0]["original_due_date"] for entry in entries]
    for collection,query,field in ((database.bills,{"recurring_payment_id":rp["id"]},"due_date"),
                                  (database.recurring_payment_records,{"recurring_id":rp["id"]},"due_date")):
        async for doc in collection.find(dict(query,user_id=scope.user_id),session=session):
            committed.append(day(doc.get(field)).isoformat())
    cutoff=max([today.isoformat(),*committed])
    if changed:
        if version["start_date"]<=cutoff or version["start_date"]<=versions[-1]["valid_from"]:
            conflict("La nueva programación debe comenzar después de todos los períodos comprometidos.")
        versions.append(dict(version,valid_from=version["start_date"]))
    if fields.get("end_date") not in (None, "") and fields["end_date"]<max(committed):
        conflict("La finalización afecta períodos ya comprometidos.")
    proposed=dict(rp,**fields,versions=versions)
    for ob,summary,bill,_ in entries:
        await _future_generation_compatible(database,ob,bill,proposed,occurrences=occurrences,add_period=add_period,session=session)
    await coordinate(database,scope.user_id,{"recurring_id":rp["id"]},session)
    await database.recurring_payments.update_one({"id":rp["id"],"user_id":scope.user_id},
        {"$set":dict(fields,versions=versions,updated_at=datetime.now(timezone.utc).isoformat())},session=session)
    return await database.recurring_payments.find_one({"id":rp["id"],"user_id":scope.user_id},session=session)


async def guard_shared_state_change(database, context, update, *, session, today, occurrences, add_period):
    scope,entries=context
    rp=entries[0][3]
    # State transitions start today: past once periods keep their frozen history.
    if any(bill_schedule(ob)["frequency"]!="once" or ob["original_due_date"]>=today.isoformat() for ob,_,_,_ in entries):
        conflict("El estado solicitado afecta períodos reservados o generación comprometida.")
    for collection,query in ((database.bills,{"recurring_payment_id":rp["id"]}),
                             (database.recurring_payment_records,{"recurring_id":rp["id"]})):
        async for doc in collection.find(dict(query,user_id=scope.user_id),session=session):
            if day(doc.get("due_date"))>=today:
                conflict("El estado solicitado afecta seguimiento o facturas comprometidas.")
    proposed=dict(rp,**update)
    for ob,_,bill,_ in entries:
        await _future_generation_compatible(database,ob,bill,proposed,occurrences=occurrences,add_period=add_period,session=session)
    await coordinate(database,scope.user_id,{"recurring_id":rp["id"]},session)
