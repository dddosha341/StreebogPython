"""
Бенчмарк: сравнение базовой и оптимизированной реализаций Стрибог.

Измеряет время вычисления хэша для входных данных разной длины,
вычисляет среднее время, пропускную способность и ускорение.
"""

from __future__ import annotations

import os
import time
from typing import Callable, List, Tuple

from .streebog import streebog_512
from .streebog_fast import streebog_512_fast


# Размеры входных данных для тестирования
BENCHMARK_SIZES: List[Tuple[str, int]] = [
    ("32 B", 32),
    ("256 B", 256),
    ("1 KB", 1024),
    ("4 KB", 4096),
    ("64 KB", 65536),
    ("1 MB", 1048576),
]


def _benchmark_single(
    hash_func: Callable[[bytes], bytes],
    data: bytes,
    iterations: int,
) -> float:
    """
    Измеряет среднее время одного вызова хэш-функции.
    Возвращает среднее время в секундах.
    """
    start = time.perf_counter()
    for _ in range(iterations):
        hash_func(data)
    elapsed = time.perf_counter() - start
    return elapsed / iterations


def run_benchmark(
    sizes: List[Tuple[str, int]] | None = None,
    min_time: float = 0.5,
) -> List[dict]:
    """
    Запускает сравнительный бенчмарк base vs fast.

    Args:
        sizes: список (label, byte_count) для тестирования. По умолчанию BENCHMARK_SIZES.
        min_time: минимальное общее время измерения на один размер (секунды).

    Returns:
        Список словарей с результатами.
    """
    if sizes is None:
        sizes = BENCHMARK_SIZES

    results: List[dict] = []

    # Заголовок таблицы
    print(f"{'Размер':>8s} | {'Base (мс)':>10s} | {'Fast (мс)':>10s} | "
          f"{'Ускорение':>10s} | {'Base (МБ/с)':>11s} | {'Fast (МБ/с)':>11s}")
    print("-" * 75)

    for label, size in sizes:
        data = os.urandom(size)

        # Верификация: base и fast дают одинаковый результат
        base_hash = streebog_512(data)
        fast_hash = streebog_512_fast(data)
        assert base_hash == fast_hash, (
            f"ОШИБКА: результаты не совпадают для {label}!"
        )

        # Определяем количество итераций (не менее 1, чтобы общее время ≥ min_time)
        # Быстрая оценка: один прогон
        t0 = time.perf_counter()
        streebog_512_fast(data)
        single_fast = time.perf_counter() - t0

        iterations = max(1, int(min_time / single_fast)) if single_fast > 0 else 100

        # Для больших данных base очень медленный — уменьшаем итерации
        t0 = time.perf_counter()
        streebog_512(data)
        single_base = time.perf_counter() - t0
        base_iterations = max(1, int(min_time / single_base)) if single_base > 0 else 1

        # Измерение
        t_base = _benchmark_single(streebog_512, data, base_iterations)
        t_fast = _benchmark_single(streebog_512_fast, data, iterations)

        speedup = t_base / t_fast if t_fast > 0 else float('inf')
        tp_base = (size / 1024 / 1024) / t_base if t_base > 0 else 0
        tp_fast = (size / 1024 / 1024) / t_fast if t_fast > 0 else 0

        result = {
            "label": label,
            "size": size,
            "base_ms": t_base * 1000,
            "fast_ms": t_fast * 1000,
            "speedup": speedup,
            "base_throughput_mbps": tp_base,
            "fast_throughput_mbps": tp_fast,
            "base_iterations": base_iterations,
            "fast_iterations": iterations,
        }
        results.append(result)

        print(
            f"{label:>8s} | "
            f"{t_base * 1000:>10.3f} | "
            f"{t_fast * 1000:>10.3f} | "
            f"{speedup:>9.1f}x | "
            f"{tp_base:>11.4f} | "
            f"{tp_fast:>11.4f}"
        )

    print()
    return results


def save_chart(results: List[dict], path: str = "data/output/benchmark.png") -> None:
    """
    Сохраняет график сравнения производительности (опционально, требует matplotlib).
    """
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print("[benchmark] matplotlib не установлен, график не сохранён.")
        return

    labels = [r["label"] for r in results]
    base_times = [r["base_ms"] for r in results]
    fast_times = [r["fast_ms"] for r in results]
    speedups = [r["speedup"] for r in results]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # График 1: Время выполнения
    x = range(len(labels))
    width = 0.35
    ax1.bar([i - width/2 for i in x], base_times, width, label='Base', color='#e74c3c')
    ax1.bar([i + width/2 for i in x], fast_times, width, label='Fast (T-tables)', color='#2ecc71')
    ax1.set_xlabel('Размер входных данных')
    ax1.set_ylabel('Время (мс)')
    ax1.set_title('Время хэширования: Base vs Fast')
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels)
    ax1.legend()
    ax1.set_yscale('log')
    ax1.grid(True, alpha=0.3)

    # График 2: Ускорение
    ax2.bar(labels, speedups, color='#3498db')
    ax2.set_xlabel('Размер входных данных')
    ax2.set_ylabel('Ускорение (раз)')
    ax2.set_title('Ускорение Fast / Base')
    ax2.grid(True, alpha=0.3)
    ax2.axhline(y=1.0, color='gray', linestyle='--', alpha=0.5)

    plt.tight_layout()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    plt.savefig(path, dpi=150)
    print(f"[benchmark] График сохранён в {path}")
