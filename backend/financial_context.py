"""Read-only identity verification. Never provisions metadata or opens a client."""
from datetime import datetime
from uuid import UUID
from fastapi import HTTPException
from pymongo.errors import PyMongoError


def validate_environment_id(value):
    try:
        parsed = UUID(value)
        if parsed.version != 4 or str(parsed) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(503, 'El contexto financiero no está provisionado o no coincide con la configuración esperada.') from None
    return str(parsed)


def validate_metadata(document, expected_id):
    expected = validate_environment_id(expected_id)
    try:
        if not document or document.get('_id') != 'financial-context' or type(document.get('version')) is not int or document['version'] != 1:
            raise ValueError()
        actual = validate_environment_id(document['environment_id'])
        if actual != expected:
            raise ValueError()
        created = datetime.fromisoformat(document['created_at'])
        if created.tzinfo is None:
            raise ValueError()
    except (ValueError, TypeError, KeyError, AttributeError):
        raise HTTPException(503, 'El contexto financiero no está provisionado o no coincide con la configuración esperada.') from None
    return actual


async def get_financial_context(database, expected_id, user_id, session=None):
    # An absent/invalid pin cannot be satisfied by blindly trusting a copied DB.
    validate_environment_id(expected_id)
    try:
        document = await database.moneyflow_metadata.find_one({'_id': 'financial-context'}, session=session)
    except PyMongoError:
        raise HTTPException(503, 'No se puede verificar el contexto financiero.') from None
    environment_id = validate_metadata(document, expected_id)
    return {'version': 1, 'environment_id': environment_id, 'user_id': user_id, 'mode': 'single_user',
            'capabilities': {'expected_context_headers': True, 'debt_payment_reconciliation': True,
                             'cross_device_recovery': False, 'bill_payment_context_headers': True,
                             'recurring_payment_context_headers': True,
                             'bill_payment_delete_context_headers': True,
                             'recurring_payment_delete_context_headers': True,
                             'bill_payment_reconciliation': True,
                             'recurring_payment_reconciliation': True}}


async def verify_payment_context(database, expected_id, effective_user, environment_header, user_header, session):
    context = await get_financial_context(database, expected_id, effective_user, session=session)
    if environment_header != context['environment_id'] or user_header != context['user_id']:
        raise HTTPException(409, 'El entorno o usuario efectivo del pago no coincide. No se registró el pago.')
