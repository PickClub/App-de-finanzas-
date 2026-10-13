"""R4 2D.1 read projections on newly created synthetic snapshot databases.

No existing databases are opened or cleaned; setup uses the previously audited
new-UUID core fixture and its command audit, and retains every new test database.
"""
import os
import unittest
from backend.tests import test_shared_payments_mongodb as core_mongo
from backend.tests.test_shared_reads import ReadCases, EndpointReadCases


@unittest.skipUnless(os.environ.get("MONEYFLOW_R4_READ_REAL_TESTS") == "1", "Explicit R4 read opt-in required")
class SharedReadMongoTests(ReadCases, EndpointReadCases, unittest.IsolatedAsyncioTestCase):
    asyncSetUp = core_mongo.SharedPaymentMongoTests.asyncSetUp
    asyncTearDown = core_mongo.SharedPaymentMongoTests.asyncTearDown
