"""Explicit, one-shot Atlas connectivity check with a dedicated read-only identity."""

import os
import sys

from backend.production_config import MongoTarget, required


def main():
    if sys.argv[1:] != ["--connect"] or os.environ.get("PW_ATLAS_PROBE_ENABLED") != "1":
        print("Atlas probe disabled.")
        return 2
    stage = "configuration"
    try:
        if os.environ.get("PW_MONGO_TARGET") != "Pickwallet-prod":
            raise ValueError
        target = MongoTarget.load(
            {**os.environ, "PW_MONGO_URI": required(os.environ, "PW_ATLAS_PROBE_URI")}
        )
        stage = "DNS policy"
        target.verify_private_network()

        from pymongo import MongoClient

        stage = "TLS and replica identity"
        options = target.mongo_options()
        options.update(
            connect=False, retryWrites=False, retryReads=False, timeoutMS=5000
        )
        with MongoClient(target.mongo_uri, **options) as client:
            hello = client.admin.command("hello")
            if (
                hello.get("setName") != target.replica_set
                or set(hello.get("hosts", ())) != set(target.mongo_hosts)
                or hello.get("isWritablePrimary") is not True
            ):
                raise ValueError

            stage = "authentication and privilege scope"
            info = client.admin.command("connectionStatus", showPrivileges=True)[
                "authInfo"
            ]
            grants = info["authenticatedUserPrivileges"]
            if (
                len(info["authenticatedUsers"]) != 1
                or len(grants) != 1
                or grants[0]["resource"]
                != {"db": target.database, "collection": "moneyflow_metadata"}
                or set(grants[0]["actions"]) != {"listIndexes"}
            ):
                raise ValueError
    except Exception:
        # Driver exceptions may contain destinations or connection details.
        print(f"Atlas probe failed at {stage}.", file=sys.stderr)
        return 1
    print("Atlas TLS, replica inventory and read-only authentication verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
