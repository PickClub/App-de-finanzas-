"""Explicit administrative connection adapter; no CLI, dotenv or import-time I/O.

Calling this adapter against a real server requires separate operator approval.
Offline callers must inject a fake client and block DNS/network. The adapter only
inspects: mutation remains exclusively in Initializer.apply after separate approval.
"""

from contextlib import contextmanager

from backend.production_config import MongoTarget
from backend.production_initializer import Initializer, InitializationBlocked


DATABASE_ACTIONS = frozenset({
    'find', 'listCollections', 'listIndexes', 'createCollection', 'createIndex',
})


def verify_administrative_identity(client, config):
    """Require database-scoped bootstrap rights and metadata-only insert rights."""
    grants = client.admin.command('connectionStatus', showPrivileges=True).get(
        'authInfo', {}
    ).get('authenticatedUserPrivileges', [])
    database_actions, metadata_actions = set(), set()
    for grant in grants:
        resource, actions = grant.get('resource'), set(grant.get('actions', []))
        if resource == {'db': config.database, 'collection': ''}:
            if not actions.issubset(DATABASE_ACTIONS | {'killCursors'}):
                raise InitializationBlocked('Restricted bootstrap database identity required')
            database_actions.update(actions)
        elif resource == {'db': config.database, 'collection': 'moneyflow_metadata'}:
            if not actions.issubset({'insert', 'find', 'listIndexes', 'killCursors'}):
                raise InitializationBlocked('Restricted bootstrap metadata identity required')
            metadata_actions.update(actions)
        else:
            raise InitializationBlocked('Unexpected bootstrap privilege resource')
    if not DATABASE_ACTIONS.issubset(database_actions) or 'insert' not in metadata_actions:
        raise InitializationBlocked('Dedicated bootstrap permissions required')


@contextmanager
def connect_initializer(env, *, connection_authorized=False, client_factory=None):
    """Yield (initializer, read-only plan), then close the short-lived client.

    Default invocation fails before configuration, DNS or client construction.
    Reuse existing TLS/network/timeout settings. No arbitrary driver overrides,
    certificate bypass, SRV, runtime-role expansion or implicit apply is supported.
    No full URI, original driver exception or environment mapping is logged.
    """
    if connection_authorized is not True:
        raise InitializationBlocked('Explicit connection authorization required')
    config = MongoTarget.load(env)
    if (env.get('PW_MONGO_TARGET') != 'Pickwallet-prod'
            or config.database != 'pickwallet_prod'
            or config.mongo_network_mode != 'atlas_allowlisted'):
        raise InitializationBlocked('Explicit Atlas production target required')
    client = initializer = None
    try:
        config.verify_private_network()
        if client_factory is None:
            # Lazy construction: importing this module cannot contact MongoDB.
            from pymongo import MongoClient
            client_factory = MongoClient
        client = client_factory(config.mongo_uri, connect=False, **config.mongo_options())
        verify_administrative_identity(client, config)
        initializer = Initializer(env, client[config.database])
        plan = initializer.dry_run()
        yield initializer, plan
    except Exception:
        # Do not expose driver messages, target URI or caller exception contents.
        raise InitializationBlocked('Administrative inspection unavailable') from None
    finally:
        if initializer is not None:
            # A reviewed plan cannot outlive the connection that inspected it.
            initializer._approved_plan = None
        if client is not None:
            try:
                client.close()
            except Exception:
                raise InitializationBlocked('Administrative client cleanup failed') from None
