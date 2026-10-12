"""Explicit metadata administration; never reads or writes financial collections.

Only run after separately authorizing the exact deployment/database.
URI is obtained from MONEYFLOW_PROVISION_MONGO_URL, never application dotenv.
"""
import argparse
from datetime import datetime, timezone
import os
import uuid
from pymongo import MongoClient
from pymongo.write_concern import WriteConcern
from pymongo.errors import PyMongoError
from fastapi import HTTPException
from .financial_context import validate_metadata


def provision(database, *, mode, expected_id=None, new_id=lambda: str(uuid.uuid4())):
    collection = database.moneyflow_metadata.with_options(write_concern=WriteConcern('majority'))
    existing = collection.find_one({'_id': 'financial-context'})
    if mode == 'verify':
        return validate_metadata(existing, expected_id)
    if mode != 'create' or existing is not None:
        raise ValueError('Creation requires absent metadata. Existing identities are never replaced.')
    environment_id = new_id()
    document = {'_id': 'financial-context', 'version': 1, 'environment_id': environment_id,
                'created_at': datetime.now(timezone.utc).isoformat()}
    validate_metadata(document, environment_id)
    collection.insert_one(document)  # Unique _id also prevents concurrent replacement.
    return validate_metadata(collection.find_one({'_id': 'financial-context'}), environment_id)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('create', 'verify'), required=True)
    parser.add_argument('--database', required=True)
    parser.add_argument('--confirm-database', required=True)
    parser.add_argument('--expected-id')
    args = parser.parse_args()
    uri = os.environ.get('MONEYFLOW_PROVISION_MONGO_URL')
    if not uri or args.database != args.confirm_database or not args.database:
        parser.error('Explicit URI environment variable and matching database confirmation required.')
    if args.mode == 'verify' and not args.expected_id:
        parser.error('Verification requires --expected-id.')
    try:
        with MongoClient(uri, serverSelectionTimeoutMS=5000) as client:
            result = provision(client[args.database], mode=args.mode, expected_id=args.expected_id)
    except (PyMongoError, HTTPException, ValueError):
        raise SystemExit('Metadata operation not confirmed. Check the approved destination and verify existing metadata before attempting creation again.') from None
    print('Verified metadata for database:', args.database)
    print('MONEYFLOW_EXPECTED_ENVIRONMENT_ID=' + result)


if __name__ == '__main__':
    main()
