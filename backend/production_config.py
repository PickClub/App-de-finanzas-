"""Production-only configuration. No dotenv, implicit defaults or network I/O."""

from dataclasses import dataclass, field
from ipaddress import ip_address, ip_network
import re
from urllib.parse import urlsplit, parse_qsl, unquote
from uuid import UUID
import socket


class ConfigurationError(ValueError):
    pass


def required(env, key):
    value = env.get(key, "")
    if not value or value != value.strip() or any(c in value for c in "\r\n"):
        raise ConfigurationError(f"Missing or invalid {key}")
    return value


def https_origin(value):
    url = urlsplit(value)
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.path
        or url.query
        or url.fragment
        or url.port not in (None, 443)
        or "*" in value
        or not re.fullmatch(
            r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", url.hostname
        )
        or url.hostname.endswith((".local", ".localhost"))
    ):
        raise ConfigurationError("An explicit HTTPS DNS origin is required")
    try:
        ip_address(url.hostname)
    except ValueError:
        return value
    raise ConfigurationError("Public origins must use DNS")


@dataclass(frozen=True, kw_only=True)
class MongoTarget:
    mongo_uri: str = field(repr=False)
    database: str
    replica_set: str
    mongo_hosts: tuple
    environment_id: str
    mongo_network_mode: str
    mongo_egress_cidrs: tuple

    @classmethod
    def load(cls, env):
        if env.get("APP_ENV") != "production":
            raise ConfigurationError("MongoDB target requires APP_ENV=production")
        try:
            uri = required(env, "PW_MONGO_URI")
            parsed = urlsplit(uri)
            # Deliberately support seed lists, not SRV: topology is explicit and independently checked.
            if parsed.scheme != "mongodb" or not parsed.username or not parsed.password:
                raise ConfigurationError("MongoDB authentication is required")
            password = unquote(parsed.password)
            if len(password) < 16 or len(set(password)) < 8:
                raise ConfigurationError("MongoDB requires a strong dedicated password")
            database = required(env, "PW_MONGO_DATABASE")
            if (
                not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{2,62}", database)
                or database
                in (
                    "r3_security_synthetic",
                    "development_local_finanzas",
                    "app_finanzas",
                    "test",
                    "admin",
                    "local",
                    "config",
                )
                or parsed.path != "/" + database
            ):
                raise ConfigurationError(
                    "Explicit dedicated production database required"
                )
            network_mode = env.get("PW_MONGO_NETWORK_MODE", "private")
            if network_mode not in ("private", "atlas_allowlisted"):
                raise ConfigurationError("Unsupported MongoDB network mode")
            egress = ()
            if network_mode == "atlas_allowlisted":
                egress = tuple(
                    ip_network(v, strict=True)
                    for v in required(env, "PW_MONGO_EGRESS_CIDRS").split(",")
                )
                if (
                    not 1 <= len(egress) <= 3
                    or len(set(egress)) != len(egress)
                    or any(
                        v.version != 4
                        or v.prefixlen != 32
                        or not v.network_address.is_global
                        or v.network_address.is_multicast
                        for v in egress
                    )
                ):
                    raise ConfigurationError(
                        "Atlas requires explicit dedicated public IPv4 /32 egress identities"
                    )
            pairs = parse_qsl(parsed.query, strict_parsing=True)
            query = dict(pairs)
            replica = required(env, "PW_MONGO_REPLICA_SET")
            if (
                len(query) != len(pairs)
                or query
                != {
                    "tls": "true",
                    "replicaSet": replica,
                    "authSource": (
                        "admin" if network_mode == "atlas_allowlisted" else database
                    ),
                    "authMechanism": "SCRAM-SHA-256",
                }
                or parsed.fragment
            ):
                raise ConfigurationError(
                    "MongoDB requires strict TLS, replica set and explicitly scoped SCRAM"
                )
            hosts = tuple(required(env, "PW_MONGO_HOSTS").split(","))
            if tuple(parsed.netloc.rsplit("@", 1)[1].split(",")) != hosts:
                raise ConfigurationError("MongoDB host inventory mismatch")
            for member in hosts:
                host, port = member.rsplit(":", 1)
                if (
                    int(port) != 27017
                    or host in ("localhost", "127.0.0.1", "0.0.0.0")
                    or not re.fullmatch(r"[a-zA-Z0-9.-]+", host)
                ):
                    raise ConfigurationError(
                        "Dedicated private MongoDB members on 27017 required"
                    )
            if len(set(hosts)) != len(hosts):
                raise ConfigurationError("Duplicate MongoDB member")
            if network_mode == "atlas_allowlisted" and (
                len(hosts) != 3
                or any(
                    not re.fullmatch(
                        r"[a-z0-9-]+(?:\.[a-z0-9-]+)*\.mongodb\.net:27017", member
                    )
                    for member in hosts
                )
            ):
                raise ConfigurationError(
                    "Atlas beta requires exactly three explicit Atlas DNS members"
                )
            target = env.get("PW_MONGO_TARGET")
            if target is not None and (
                target != "Pickwallet-prod"
                or network_mode != "atlas_allowlisted"
                or database != "pickwallet_prod"
            ):
                raise ConfigurationError("MongoDB production target mismatch")
            environment = str(UUID(required(env, "PW_ENVIRONMENT_ID")))
            if UUID(environment).version != 4:
                raise ConfigurationError("UUID4 environment required")
            if environment != env["PW_ENVIRONMENT_ID"]:
                raise ConfigurationError("Canonical UUID4 environment required")
            return cls(
                mongo_uri=uri,
                database=database,
                replica_set=replica,
                mongo_hosts=hosts,
                environment_id=environment,
                mongo_network_mode=network_mode,
                mongo_egress_cidrs=egress,
            )
        except ConfigurationError:
            raise
        except Exception:
            raise ConfigurationError(
                "Invalid production MongoDB configuration"
            ) from None

    def verify_private_network(self):
        """Resolve all seed addresses before a driver can open a socket."""
        try:
            for member in self.mongo_hosts:
                host, port = member.rsplit(":", 1)
                addresses = socket.getaddrinfo(host, int(port), type=socket.SOCK_STREAM)
                if not addresses:
                    raise ValueError()
                for row in addresses:
                    address = ip_address(row[4][0])
                    if (
                        address.is_loopback
                        or address.is_link_local
                        or address.is_unspecified
                        or address.is_multicast
                    ):
                        raise ValueError()
                    if self.mongo_network_mode == "private" and not address.is_private:
                        raise ValueError()
                    if (
                        self.mongo_network_mode == "atlas_allowlisted"
                        and not address.is_global
                    ):
                        raise ValueError()

        except Exception:
            raise ConfigurationError(
                "MongoDB DNS does not match the approved network mode"
            ) from None

    def mongo_options(self):
        # Initial low-volume beta: retain driver pool size, bound waits and short OLTP I/O.
        return dict(
            tz_aware=True,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            socketTimeoutMS=30000,
            waitQueueTimeoutMS=5000,
            retryWrites=True,
            w="majority",
            readPreference="primary",
            tls=True,
        )


@dataclass(frozen=True)
class ProductionConfig(MongoTarget):
    public_origin: str
    allowed_origins: tuple
    trusted_proxies: tuple
    smtp_host: str
    smtp_username: str = field(repr=False)
    smtp_password: str = field(repr=False)
    mail_from: str
    rate_secret: bytes = field(repr=False)

    @classmethod
    def load(cls, env):
        target = MongoTarget.load(env)
        try:
            origin = https_origin(required(env, "PW_PUBLIC_ORIGIN"))
            origins = tuple(
                https_origin(v) for v in required(env, "PW_ALLOWED_ORIGINS").split(",")
            )
            proxies = tuple(
                ip_network(v, strict=True)
                for v in required(env, "PW_TRUSTED_PROXIES").split(",")
            )
            if any(p.prefixlen == 0 or not p.is_private for p in proxies):
                raise ConfigurationError(
                    "Only explicit private proxy networks are permitted"
                )
            smtp_password = required(env, "PW_SMTP_PASSWORD")
            if len(smtp_password) < 16 or len(set(smtp_password)) < 8:
                raise ConfigurationError("SMTP requires a dedicated provider secret")
            secret = required(env, "PW_RATE_SECRET")
            if len(secret) < 64 or len(set(secret)) < 16:
                raise ConfigurationError(
                    "PW_RATE_SECRET must be independently generated with high entropy"
                )
            from backend.auth_core import normalize_email

            return cls(
                **vars(target),
                public_origin=origin,
                allowed_origins=origins,
                trusted_proxies=proxies,
                smtp_host=required(env, "PW_SMTP_HOST"),
                smtp_username=required(env, "PW_SMTP_USERNAME"),
                smtp_password=smtp_password,
                mail_from=normalize_email(required(env, "PW_MAIL_FROM")),
                rate_secret=secret.encode(),
            )
        except ConfigurationError:
            raise
        except Exception:
            raise ConfigurationError("Invalid production configuration") from None
