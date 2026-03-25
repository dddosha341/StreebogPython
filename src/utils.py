"""
Вспомогательные функции для реализации Стрибог.

Все арифметические операции над 512-битными числами выполняются
в little-endian формате, как определено стандартом ГОСТ 34.11-2018.
"""

from __future__ import annotations


def xor_bytes(a: bytes | bytearray, b: bytes | bytearray) -> bytearray:
    """Побайтовый XOR двух блоков одинаковой длины (64 байта)."""
    return bytearray(x ^ y for x, y in zip(a, b))


def add_mod512(a: bytes | bytearray, b: bytes | bytearray) -> bytearray:
    """
    Сложение двух 512-битных чисел по модулю 2^512.

    Оба операнда интерпретируются как little-endian целые числа длиной 64 байта.
    Результат — 64 байта в little-endian.
    """
    int_a = int.from_bytes(a, byteorder='little')
    int_b = int.from_bytes(b, byteorder='little')
    result = (int_a + int_b) % (1 << 512)
    return bytearray(result.to_bytes(64, byteorder='little'))
