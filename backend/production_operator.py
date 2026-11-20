"""Explicit operator CLI; email input on stdin, no public enrollment or recovery issuance."""

import logging
import os
import sys
from pymongo import MongoClient
from backend.auth_core import AuthService, normalize_email
from backend.auth_mongodb import Store, retry_auth
from backend.production_config import ProductionConfig
from backend.production_services import SMTPDelivery, MongoRateLimiter, verify_database


def main():
    if sys.argv[1:] not in (["invite"], ["recover"]):
        raise SystemExit(
            "Expected invite or recover; normalized recipient email on stdin"
        )
    try:
        config = ProductionConfig.load(os.environ)
        config.verify_private_network()
        email = normalize_email(sys.stdin.readline(513).strip())
        with MongoClient(config.mongo_uri, **config.mongo_options()) as client:
            db = verify_database(client, config)
            MongoRateLimiter(db, config.rate_secret).check(
                "operator-" + sys.argv[1], email, 3, 3600
            )
            operator = object()
            auth = AuthService(
                Store(db), SMTPDelivery(config), lambda actor: actor is operator
            )
            retry_auth(getattr(auth, sys.argv[1]), operator, email)
        print("Account message submitted")
    except Exception:
        logging.getLogger("pickwallet.security").warning(
            "operator_account_operation_failed"
        )
        raise SystemExit(
            "Account operation failed; no sensitive details recorded"
        ) from None


if __name__ == "__main__":
    main()
