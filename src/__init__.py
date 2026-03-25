"""
Стрибог (ГОСТ 34.11-2018) — реализация на Python.

Экспортируемые функции:
- streebog_512, streebog_256 — базовая (референсная) реализация
- streebog_512_fast, streebog_256_fast — оптимизированная реализация с T-таблицами
"""

from .streebog import streebog_512, streebog_256

try:
    from .streebog_fast import streebog_512_fast, streebog_256_fast
except ImportError:
    pass

__all__ = [
    "streebog_512",
    "streebog_256",
    "streebog_512_fast",
    "streebog_256_fast",
]
