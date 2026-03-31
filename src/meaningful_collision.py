"""
Построение осмысленной коллизии для h(x) = MSB48(STREEBOG-512(x)).

Два валидных BMP-изображения с визуально различным содержимым,
но одинаковым значением MSB48 хэша.

=== Подход ===

Формат BMP (Windows Bitmap) идеален для этой задачи:
1. Заголовок BMP содержит поле bfSize (размер файла), но большинство
   просмотрщиков игнорируют данные после объявленных пиксельных данных.
2. Мы создаём два BMP-изображения (например, "X" и "O") и дописываем
   управляемый суффикс после пиксельных данных.
3. Просмотрщики отображают только заявленные пиксели, суффикс не виден.
4. При хэшировании учитывается весь файл, включая суффикс.

=== Оптимизация ===

Предвычисляем состояние Streebog после обработки всех полных блоков
каждого изображения. Для каждого нового суффикса:
- Клонируем предвычисленное состояние
- Дообрабатываем только оставшийся хвост + суффикс
- Финализируем хэш

Это сокращает работу с O(размер_изображения) до O(размер_суффикса) на попытку.

=== Birthday Attack между двумя множествами ===

- Генерируем суффиксы для изображения A, сохраняем h48 → suffix_a в таблицу.
- Генерируем суффиксы для изображения B, проверяем h48 против таблицы A.
- Ожидаемое число попыток: ~2^24 (по парадоксу дней рождения).
"""

from __future__ import annotations

import os
import struct
import time
import tracemalloc
from pathlib import Path
from typing import Optional, Tuple

from .hasher_interface import HasherProtocol, create_hasher, hash_bytes


# ---------------------------------------------------------------------------
# Генерация BMP-изображений
# ---------------------------------------------------------------------------

def _create_bmp(width: int, height: int, pixels_func) -> bytes:
    """
    Создаёт 24-битное несжатое BMP-изображение.

    Args:
        width: ширина в пикселях
        height: высота в пикселях
        pixels_func: функция (x, y) -> (r, g, b), y=0 — нижний ряд (BMP-конвенция)

    BMP-формат (little-endian):
    - Файловый заголовок (14 байт): сигнатура BM, размер файла, смещение данных
    - DIB-заголовок BITMAPINFOHEADER (40 байт): размеры, bpp, сжатие и т.д.
    - Пиксельные данные: строки снизу вверх, BGR, выравнивание по 4 байта
    """
    row_size = (width * 3 + 3) & ~3  # выравнивание строки до кратных 4 байт
    pixel_data_size = row_size * height
    file_size = 54 + pixel_data_size  # 14 (file header) + 40 (DIB) + pixels

    # Файловый заголовок (14 байт)
    file_header = struct.pack('<2sIHHI',
        b'BM',           # сигнатура
        file_size,       # размер файла
        0,               # reserved1
        0,               # reserved2
        54,              # смещение до пиксельных данных
    )

    # DIB-заголовок BITMAPINFOHEADER (40 байт)
    dib_header = struct.pack('<IiiHHIIiiII',
        40,              # размер DIB-заголовка
        width,           # ширина
        height,          # высота (положительное = bottom-up)
        1,               # цветовые плоскости
        24,              # бит на пиксель
        0,               # без сжатия (BI_RGB)
        pixel_data_size, # размер пиксельных данных
        2835,            # горизонтальное разрешение (72 dpi)
        2835,            # вертикальное разрешение
        0,               # количество цветов (0 = 2^bpp)
        0,               # значимые цвета
    )

    # Пиксельные данные (строки снизу вверх)
    pixel_data = bytearray()
    for y in range(height):
        row = bytearray()
        for x in range(width):
            r, g, b = pixels_func(x, y)
            row += bytes([b, g, r])  # BMP использует BGR
        # Выравнивание строки до 4 байт
        row += b'\x00' * (row_size - width * 3)
        pixel_data += row

    return file_header + dib_header + bytes(pixel_data)


def _x_pattern(x: int, y: int) -> Tuple[int, int, int]:
    """Рисует 'X' — белые диагонали на чёрном фоне."""
    # Координаты нормализованы к [0, 63] для изображения 64x64
    if abs(x - y) < 4 or abs(x - (63 - y)) < 4:
        return (255, 255, 255)
    return (0, 0, 0)


def _o_pattern(x: int, y: int) -> Tuple[int, int, int]:
    """Рисует 'O' — белое кольцо на чёрном фоне."""
    cx, cy = 32, 32
    r = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
    if 18 < r < 26:
        return (255, 255, 255)
    return (0, 0, 0)


# ---------------------------------------------------------------------------
# Предвычисление состояния хэшера
# ---------------------------------------------------------------------------

def _precompute_hash_state(image_data: bytes) -> Tuple[HasherProtocol, bytearray]:
    """
    Обрабатывает все полные 64-байтовые блоки изображения
    и возвращает (hasher_state, remaining_bytes).

    Для каждого суффикса можно клонировать hasher_state,
    дообработать remaining + suffix и финализировать.
    """
    hasher = create_hasher(digest_size=512, impl="fast")
    # Обрабатываем все полные блоки
    full_blocks = (len(image_data) // 64) * 64
    if full_blocks > 0:
        hasher.update(image_data[:full_blocks])
    remaining = bytearray(image_data[full_blocks:])
    return hasher, remaining


def _hash_with_suffix(
    base_hasher: HasherProtocol,
    remaining: bytearray,
    suffix: bytes,
) -> bytes:
    """
    Дохэширует remaining + suffix, используя клон предвычисленного состояния.
    Возвращает полный 64-байтовый дайджест.
    """
    h = base_hasher.copy()
    h.update(remaining + suffix)
    return h.digest()


# ---------------------------------------------------------------------------
# Поиск осмысленной коллизии
# ---------------------------------------------------------------------------

def find_meaningful_collision(
    out_dir: str = "data/output",
    suffix_size: int = 32,
    max_attempts: int = 50_000_000,
    log_interval: int = 500_000,
) -> Tuple[bytes, bytes, bytes]:
    """
    Находит два BMP-изображения с одинаковым MSB48(Streebog-512).

    Создаёт два изображения 64x64: "X" и "O".
    Дописывает случайные суффиксы и ищет совпадение h48.

    Возвращает: (image_a_bytes, image_b_bytes, h48_value)
    """
    import random
    rng = random.Random(42)

    print("[meaningful] Создание BMP-изображений (64x64, 24-bit)...")
    img_a = _create_bmp(64, 64, _x_pattern)
    img_b = _create_bmp(64, 64, _o_pattern)
    print(f"[meaningful] Изображение A (X-паттерн): {len(img_a)} байт")
    print(f"[meaningful] Изображение B (O-паттерн): {len(img_b)} байт")

    # Предвычисление состояний
    print("[meaningful] Предвычисление состояний хэшера...")
    state_a, rem_a = _precompute_hash_state(img_a)
    state_b, rem_b = _precompute_hash_state(img_b)
    print(f"[meaningful] Остаток A: {len(rem_a)} байт, остаток B: {len(rem_b)} байт")

    # Birthday attack: таблица для A, проверка с B
    seen_a: dict[bytes, bytes] = {}  # h48 → suffix
    attempts = 0
    half = max_attempts // 2

    tracemalloc.start()
    start_time = time.perf_counter()

    print(f"[meaningful] Начат поиск коллизии (birthday attack между двумя изображениями)")
    print(f"[meaningful] Ожидаемое число попыток: ~{1.25 * 2**24:.0f}")
    print()

    while attempts < max_attempts:
        # Генерируем суффикс для A и вычисляем h48
        suffix_a = rng.randbytes(suffix_size)
        digest_a = _hash_with_suffix(state_a, rem_a, suffix_a)
        prefix_a = digest_a[:6]
        seen_a[prefix_a] = suffix_a
        attempts += 1

        # Генерируем суффикс для B и проверяем
        suffix_b = rng.randbytes(suffix_size)
        digest_b = _hash_with_suffix(state_b, rem_b, suffix_b)
        prefix_b = digest_b[:6]
        attempts += 1

        if prefix_b in seen_a:
            elapsed = time.perf_counter() - start_time
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            matched_suffix_a = seen_a[prefix_b]
            final_a = img_a + matched_suffix_a
            final_b = img_b + suffix_b

            # Верификация
            verify_a = hash_bytes(final_a, digest_size=512, impl="fast")[:6]
            verify_b = hash_bytes(final_b, digest_size=512, impl="fast")[:6]
            assert verify_a == verify_b, "Верификация не прошла!"

            print(f"\n[meaningful] КОЛЛИЗИЯ НАЙДЕНА!")
            print(f"[meaningful] Попыток: {attempts:,}")
            print(f"[meaningful] Время: {elapsed:.2f} с")
            print(f"[meaningful] h48: {prefix_b.hex()}")

            # Сохранение
            _save_meaningful_result(out_dir, final_a, final_b, prefix_b,
                                    hash_bytes(final_a, digest_size=512, impl="fast"),
                                    hash_bytes(final_b, digest_size=512, impl="fast"),
                                    attempts, elapsed)

            return final_a, final_b, prefix_b

        if attempts % log_interval == 0:
            elapsed = time.perf_counter() - start_time
            rate = attempts / elapsed if elapsed > 0 else 0
            current, _ = tracemalloc.get_traced_memory()
            print(
                f"[meaningful] {attempts:>10,} попыток | "
                f"{elapsed:>7.1f}с | "
                f"{rate:>8,.0f} хэш/с | "
                f"таблица: {len(seen_a):,} | "
                f"память: {current / 1024 / 1024:.1f} МБ"
            )

    tracemalloc.stop()
    raise RuntimeError(f"Коллизия не найдена за {max_attempts:,} попыток.")


def _save_meaningful_result(
    out_dir: str,
    img_a: bytes, img_b: bytes, h48_val: bytes,
    full_hash_a: bytes, full_hash_b: bytes,
    attempts: int, elapsed: float,
) -> None:
    """Сохраняет изображения и метаданные коллизии."""
    path = Path(out_dir)
    path.mkdir(parents=True, exist_ok=True)

    # Сохраняем BMP-файлы
    (path / "image1_X.bmp").write_bytes(img_a)
    (path / "image2_O.bmp").write_bytes(img_b)

    # Метаданные
    import json
    meta = {
        "image1": "image1_X.bmp",
        "image2": "image2_O.bmp",
        "image1_size": len(img_a),
        "image2_size": len(img_b),
        "h48_hex": h48_val.hex(),
        "full_hash1_hex": full_hash_a.hex(),
        "full_hash2_hex": full_hash_b.hex(),
        "attempts": attempts,
        "elapsed_seconds": round(elapsed, 3),
        "description": (
            "Image1 содержит паттерн 'X' (белые диагонали на чёрном фоне). "
            "Image2 содержит паттерн 'O' (белое кольцо на чёрном фоне). "
            "Оба файла — валидные BMP, отображаются стандартными просмотрщиками. "
            "Суффиксы после пиксельных данных игнорируются при отображении, "
            "но учитываются при хэшировании."
        ),
    }
    with open(path / "meaningful_collision.json", "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print(f"[meaningful] Изображения сохранены в {path}/")
    print(f"[meaningful] image1_X.bmp ({len(img_a)} байт)")
    print(f"[meaningful] image2_O.bmp ({len(img_b)} байт)")
