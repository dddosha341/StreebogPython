"""
Поиск коллизии для усечённой хэш-функции h(x) = MSB48(STREEBOG-512(x)).

MSB48 = первые 6 байтов (48 бит) дайджеста Streebog-512.

=== Метод: Birthday Attack ===

По парадоксу дней рождения, ожидаемое число попыток для нахождения коллизии
в n-битном хэше ≈ sqrt(π/2 · 2^n) ≈ 1.25 · 2^(n/2).

Для n = 48: ожидаемое число попыток ≈ 1.25 · 2^24 ≈ 20.97M.

Алгоритм:
1. Генерируем случайное сообщение x.
2. Вычисляем h48(x) = STREEBOG-512(x)[:6].
3. Проверяем, есть ли уже такой h48 в таблице.
4. Если да и сообщения различны — коллизия найдена.
5. Если нет — сохраняем (h48 → x) в таблицу.
"""

from __future__ import annotations

import json
import os
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Optional, Tuple

from .hasher_interface import hash_bytes


def h48(data: bytes) -> bytes:
    """
    Усечённая хэш-функция: первые 6 байтов (48 бит) от Streebog-512.

    Выбор MSB48 = digest[:6]:
    В нашем внутреннем LE-представлении digest[0] — младший байт,
    но для целей коллизии выбор первых/последних байтов не принципиален,
    так как все байты хэша равномерно распределены.
    """
    return hash_bytes(data, digest_size=512, impl="fast")[:6]


def find_collision(
    seed: Optional[int] = None,
    msg_size: int = 16,
    max_attempts: int = 50_000_000,
    log_interval: int = 1_000_000,
    out_dir: Optional[str] = None,
) -> Tuple[bytes, bytes, bytes, int, float]:
    """
    Поиск коллизии для h48 методом birthday attack.

    Параметры:
        seed: seed для PRNG (для воспроизводимости). None = случайный.
        msg_size: длина случайных сообщений в байтах.
        max_attempts: максимальное число попыток.
        log_interval: частота логирования прогресса.
        out_dir: директория для сохранения результата (None = не сохранять).

    Возвращает:
        (msg1, msg2, hash_prefix, attempts, elapsed_seconds)
    """
    import random

    if seed is not None:
        random.seed(seed)
        rng = random.Random(seed)
    else:
        rng = random.Random()

    # Словарь: h48_value (6 bytes) → message (bytes)
    seen: dict[bytes, bytes] = {}
    attempts = 0

    tracemalloc.start()
    start_time = time.perf_counter()

    print(f"[collision] Начат поиск коллизии для MSB48(Streebog-512)")
    print(f"[collision] Размер сообщений: {msg_size} байт, seed: {seed}")
    print(f"[collision] Ожидаемое число попыток: ~{1.25 * 2**24:.0f} (~20.97M)")
    print()

    while attempts < max_attempts:
        # Генерируем случайное сообщение
        msg = rng.randbytes(msg_size)
        prefix = h48(msg)
        attempts += 1

        if prefix in seen:
            other = seen[prefix]
            if other != msg:
                elapsed = time.perf_counter() - start_time
                current, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()

                print(f"\n[collision] КОЛЛИЗИЯ НАЙДЕНА!")
                print(f"[collision] Попыток: {attempts:,}")
                print(f"[collision] Время: {elapsed:.2f} с")
                print(f"[collision] Пиковая память: {peak / 1024 / 1024:.1f} МБ")
                print(f"[collision] msg1: {msg.hex()}")
                print(f"[collision] msg2: {other.hex()}")
                print(f"[collision] h48:  {prefix.hex()}")

                # Верификация
                full1 = hash_bytes(msg, digest_size=512, impl="fast")
                full2 = hash_bytes(other, digest_size=512, impl="fast")
                assert full1[:6] == full2[:6], "Верификация не прошла!"
                print(f"[collision] Полный хэш msg1: {full1.hex()}")
                print(f"[collision] Полный хэш msg2: {full2.hex()}")

                # Сохранение результата
                if out_dir:
                    _save_result(out_dir, msg, other, prefix, full1, full2,
                                 attempts, elapsed, peak, seed)

                return msg, other, prefix, attempts, elapsed
        else:
            seen[prefix] = msg

        if attempts % log_interval == 0:
            elapsed = time.perf_counter() - start_time
            rate = attempts / elapsed if elapsed > 0 else 0
            current, peak = tracemalloc.get_traced_memory()
            print(
                f"[collision] {attempts:>10,} попыток | "
                f"{elapsed:>7.1f}с | "
                f"{rate:>8,.0f} хэш/с | "
                f"таблица: {len(seen):,} | "
                f"память: {current / 1024 / 1024:.1f} МБ"
            )

    tracemalloc.stop()
    raise RuntimeError(
        f"Коллизия не найдена за {max_attempts:,} попыток. "
        f"Попробуйте увеличить max_attempts."
    )


def _save_result(
    out_dir: str,
    msg1: bytes, msg2: bytes, prefix: bytes,
    full1: bytes, full2: bytes,
    attempts: int, elapsed: float, peak_memory: float,
    seed: Optional[int],
) -> None:
    """Сохраняет результат коллизии в JSON."""
    path = Path(out_dir)
    path.mkdir(parents=True, exist_ok=True)

    result = {
        "msg1_hex": msg1.hex(),
        "msg2_hex": msg2.hex(),
        "h48_hex": prefix.hex(),
        "full_hash1_hex": full1.hex(),
        "full_hash2_hex": full2.hex(),
        "attempts": attempts,
        "elapsed_seconds": round(elapsed, 3),
        "peak_memory_mb": round(peak_memory / 1024 / 1024, 1),
        "seed": seed,
        "expected_attempts": round(1.25 * 2**24),
    }

    filepath = path / "collision.json"
    with open(filepath, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"[collision] Результат сохранён в {filepath}")
