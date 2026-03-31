"""
Единый абстрактный слой для работы с реализациями Стрибог.

Модуль предоставляет:
- HasherProtocol: общий контракт потокового хэшера;
- create_hasher(...): фабрику base/fast реализаций;
- hash_bytes(...): унифицированную одноразовую обёртку.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from .streebog import Streebog
from .streebog_fast import StreebogFast

HasherImpl = Literal["base", "fast"]


@runtime_checkable
class HasherProtocol(Protocol):
    """Общий контракт для потоковых хэшеров Streebog."""

    digest_size: int

    def update(self, data: bytes | bytearray) -> None:
        ...

    def digest(self) -> bytes:
        ...

    def hexdigest(self) -> str:
        ...

    def copy(self) -> "HasherProtocol":
        ...


def create_hasher(digest_size: int = 512, impl: HasherImpl = "base") -> HasherProtocol:
    """Создаёт экземпляр хэшера нужной реализации."""
    if impl == "base":
        return Streebog(digest_size)
    if impl == "fast":
        return StreebogFast(digest_size)
    raise ValueError(f"Unknown hasher implementation: {impl}")


def hash_bytes(data: bytes, digest_size: int = 512, impl: HasherImpl = "base") -> bytes:
    """Унифицированное одноразовое хэширование массива байтов."""
    hasher = create_hasher(digest_size=digest_size, impl=impl)
    hasher.update(data)
    return hasher.digest()
