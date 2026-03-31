"""
Тесты единого интерфейса хэшера и фабрики реализации.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.hasher_interface import create_hasher, hash_bytes


def test_factory_base_and_fast_match_512() -> None:
    data = b"streebog interface test 512"
    base = hash_bytes(data, digest_size=512, impl="base")
    fast = hash_bytes(data, digest_size=512, impl="fast")
    assert base == fast


def test_factory_base_and_fast_match_256() -> None:
    data = b"streebog interface test 256"
    base = hash_bytes(data, digest_size=256, impl="base")
    fast = hash_bytes(data, digest_size=256, impl="fast")
    assert base == fast


def test_incremental_update_via_factory() -> None:
    data = b"streaming update by chunks"
    h = create_hasher(digest_size=512, impl="fast")
    h.update(data[:5])
    h.update(data[5:15])
    h.update(data[15:])
    chunked = h.digest()
    one_shot = hash_bytes(data, digest_size=512, impl="fast")
    assert chunked == one_shot


def test_copy_reproducible_digest() -> None:
    payload = b"copy behavior"
    h1 = create_hasher(digest_size=256, impl="base")
    h1.update(payload[:4])
    h2 = h1.copy()
    h1.update(payload[4:])
    h2.update(payload[4:])
    assert h1.digest() == h2.digest()
