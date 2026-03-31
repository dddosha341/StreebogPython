"""
CLI-интерфейс для проекта Стрибог.

Команды:
  hash       — вычислить хэш файла или stdin
  collision  — поиск коллизии для MSB48
  meaningful-collision — осмысленная коллизия (два BMP-изображения)
  bench      — бенчмарк base vs fast
  selftest   — запуск контрольных тестов
"""

from __future__ import annotations

import argparse
import sys
import os


def cmd_hash(args: argparse.Namespace) -> None:
    """Вычисление хэша файла."""
    from .hasher_interface import create_hasher

    # Чтение данных
    if args.file:
        with open(args.file, 'rb') as f:
            data = f.read()
    else:
        data = sys.stdin.buffer.read()

    impl = "fast" if args.fast else "base"
    hasher = create_hasher(digest_size=args.alg, impl=impl)
    hasher.update(data)
    print(hasher.hexdigest())


def cmd_collision(args: argparse.Namespace) -> None:
    """Поиск коллизии для MSB48(Streebog-512)."""
    from .collision_search import find_collision

    find_collision(
        seed=args.seed,
        out_dir=args.out_dir,
        max_attempts=args.max_attempts,
    )


def cmd_meaningful_collision(args: argparse.Namespace) -> None:
    """Построение осмысленной коллизии для двух BMP-изображений."""
    from .meaningful_collision import find_meaningful_collision

    find_meaningful_collision(
        out_dir=args.out_dir,
        max_attempts=args.max_attempts,
    )


def cmd_bench(args: argparse.Namespace) -> None:
    """Запуск бенчмарка."""
    from .benchmark import run_benchmark, save_chart

    results = run_benchmark()
    if args.chart:
        save_chart(results, path=args.chart)


def cmd_selftest(args: argparse.Namespace) -> None:
    """Запуск контрольных тестов ГОСТ."""
    from .streebog import streebog_512, streebog_256
    from .streebog_fast import streebog_512_fast, streebog_256_fast

    # M1 — 63 байта
    m1 = bytes.fromhex(
        "32313039383736353433323130393837"
        "36353433323130393837363534333231"
        "30393837363534333231303938373635"
        "3433323130393837363534333231" "30"
    )
    # M2 — 72 байта
    m2 = bytes.fromhex(
        "fbe2e5f0eee3c820fbeafaebef20fffb"
        "f0e1e0f0f520e0ed20e8ece0ebe5f0f2"
        "f120fff0eeec20f120faf2fee5e2202c"
        "e8f6f3ede220e8e6eee1e8f0f2d1202c"
        "e8f0f2e5e220e5d1"
    )

    tests = [
        ("M1/512 base", streebog_512(m1).hex(),
         "150fd4d141347ae78253b1fc9fcd2522aaad2bf06316a5e9189b7487835bc022"
         "b85a503627136177c9d6f133a3f338c83277ca5798bd6bc0ee34282ba0a3d353"),
        ("M1/256 base", streebog_256(m1).hex(),
         "1ebad9552deb878020f7e5c088784b87f006f86baacb19cf094dc5d48950e0f6"),
        ("M2/512 base", streebog_512(m2).hex(),
         "9663a3abce48e5b8545169e9ede65e0c96b827afdad47ac56c8ba343b3628e64"
         "a25418a6ed0685e414a4420960c38e102180f7e1759f8f61262185115fea5703"),
        ("M2/256 base", streebog_256(m2).hex(),
         "0e7ab4efd0915eaac2dab58dae45d0f28d14f83c57794b3338f7872c10542c19"),
        ("M1/512 fast", streebog_512_fast(m1).hex(),
         "150fd4d141347ae78253b1fc9fcd2522aaad2bf06316a5e9189b7487835bc022"
         "b85a503627136177c9d6f133a3f338c83277ca5798bd6bc0ee34282ba0a3d353"),
        ("M1/256 fast", streebog_256_fast(m1).hex(),
         "1ebad9552deb878020f7e5c088784b87f006f86baacb19cf094dc5d48950e0f6"),
    ]

    all_pass = True
    for name, got, expected in tests:
        ok = got == expected
        status = "OK" if ok else "FAIL"
        print(f"  [{status}] {name}")
        if not ok:
            print(f"         expected: {expected}")
            print(f"         got:      {got}")
            all_pass = False

    # Проверка base == fast на случайных данных
    import random
    random.seed(12345)
    for i in range(20):
        data = random.randbytes(random.randint(0, 500))
        b512 = streebog_512(data)
        f512 = streebog_512_fast(data)
        if b512 != f512:
            print(f"  [FAIL] random test {i}: base != fast")
            all_pass = False
    if all_pass:
        print(f"  [OK] 20 random base==fast tests")

    if all_pass:
        print("\nВсе тесты пройдены!")
    else:
        print("\nЕсть ошибки!")
        sys.exit(1)


def main() -> None:
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(
        prog="streebog",
        description="Стрибог (ГОСТ 34.11-2018) — хэш-функция и инструменты",
    )
    subparsers = parser.add_subparsers(dest="command", help="Доступные команды")

    # --- hash ---
    p_hash = subparsers.add_parser("hash", help="Вычислить хэш")
    p_hash.add_argument("--alg", type=int, choices=[256, 512], default=512,
                        help="Размер хэша (256 или 512 бит)")
    p_hash.add_argument("--file", "-f", type=str, default=None,
                        help="Путь к файлу (по умолчанию — stdin)")
    p_hash.add_argument("--fast", action="store_true",
                        help="Использовать оптимизированную реализацию")
    p_hash.set_defaults(func=cmd_hash)

    # --- collision ---
    p_coll = subparsers.add_parser("collision",
                                    help="Поиск коллизии для MSB48")
    p_coll.add_argument("--out-dir", type=str, default="data/output",
                        help="Директория для результата")
    p_coll.add_argument("--seed", type=int, default=None,
                        help="Seed для PRNG")
    p_coll.add_argument("--max-attempts", type=int, default=50_000_000,
                        help="Максимальное число попыток")
    p_coll.set_defaults(func=cmd_collision)

    # --- meaningful-collision ---
    p_mcoll = subparsers.add_parser("meaningful-collision",
                                     help="Осмысленная коллизия (BMP)")
    p_mcoll.add_argument("--out-dir", type=str, default="data/output",
                         help="Директория для результата")
    p_mcoll.add_argument("--max-attempts", type=int, default=50_000_000,
                         help="Максимальное число попыток")
    p_mcoll.set_defaults(func=cmd_meaningful_collision)

    # --- bench ---
    p_bench = subparsers.add_parser("bench", help="Бенчмарк base vs fast")
    p_bench.add_argument("--chart", type=str, default=None, nargs='?',
                         const="data/output/benchmark.png",
                         help="Путь для сохранения графика")
    p_bench.set_defaults(func=cmd_bench)

    # --- selftest ---
    p_test = subparsers.add_parser("selftest", help="Запуск контрольных тестов")
    p_test.set_defaults(func=cmd_selftest)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
