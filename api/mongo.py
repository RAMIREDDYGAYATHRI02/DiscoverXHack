from functools import lru_cache

from django.conf import settings
from pymongo import MongoClient

_test_collection = None


@lru_cache(maxsize=1)
def _client():
    return MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=3000)


def state_collection():
    if _test_collection is not None:
        return _test_collection
    return _client()[settings.MONGODB_DATABASE]["clinic_state"]


def set_test_collection(collection):
    global _test_collection
    _test_collection = collection


def clear_test_collection():
    global _test_collection
    _test_collection = None
