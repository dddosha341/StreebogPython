"""
Тесты на контрольных векторах из ГОСТ 34.11-2018 (Приложение А) / RFC 6986.

Тестовые сообщения:
  M1 = 0x3231...3130 (63 байта — ASCII "012345678901234567890123456789012345678901234567890123456789012"
       в порядке, определённом стандартом)
  M2 = 0xfbe2e5f0...d1 (72 байта)

Ожидаемые хэши взяты из RFC 6986, Appendix A (Test Vectors).

Важно: в стандарте сообщения записаны в виде hex-строки, где первый байт
(левый) — это байт с наименьшим адресом (индекс 0 массива).
"""

import pytest
import os
import sys

# Добавляем корень проекта в sys.path для запуска без установки пакета
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.streebog import streebog_512, streebog_256, Streebog


# ---------------------------------------------------------------------------
# Тестовые данные из RFC 6986 / ГОСТ 34.11-2018 Приложение А
# ---------------------------------------------------------------------------

# Тестовое сообщение M1 (63 байта = 504 бит)
# RFC 6986, Appendix A.1: Hex-строка читается побайтово слева направо.
M1 = bytes.fromhex(
    "32313039383736353433323130393837"
    "36353433323130393837363534333231"
    "30393837363534333231303938373635"
    "3433323130393837363534333231" "30"
)
assert len(M1) == 63, f"M1 should be 63 bytes, got {len(M1)}"

# Тестовое сообщение M2 (72 байта = 576 бит)
# RFC 6986, Appendix A.2
M2 = bytes.fromhex(
    "fbe2e5f0eee3c820fbeafaebef20fffb"
    "f0e1e0f0f520e0ed20e8ece0ebe5f0f2"
    "f120fff0eeec20f120faf2fee5e2202c"
    "e8f6f3ede220e8e6eee1e8f0f2d1202c"
    "e8f0f2e5e220e5d1"
)
assert len(M2) == 72, f"M2 should be 72 bytes, got {len(M2)}"

# Ожидаемые хэши для M1
# Внутреннее представление — little-endian (как в gostcrypto).
# Для отображения в RFC/ГОСТ-стиле нужно перевернуть байты.
M1_HASH_512 = (
    "150fd4d141347ae78253b1fc9fcd2522"
    "aaad2bf06316a5e9189b7487835bc022"
    "b85a503627136177c9d6f133a3f338c8"
    "3277ca5798bd6bc0ee34282ba0a3d353"
)

M1_HASH_256 = (
    "1ebad9552deb878020f7e5c088784b87"
    "f006f86baacb19cf094dc5d48950e0f6"
)

# Ожидаемые хэши для M2
M2_HASH_512 = (
    "9663a3abce48e5b8545169e9ede65e0c"
    "96b827afdad47ac56c8ba343b3628e64"
    "a25418a6ed0685e414a4420960c38e10"
    "2180f7e1759f8f61262185115fea5703"
)

M2_HASH_256 = (
    "0e7ab4efd0915eaac2dab58dae45d0f2"
    "8d14f83c57794b3338f7872c10542c19"
)


# ---------------------------------------------------------------------------
# Тесты для базовой реализации
# ---------------------------------------------------------------------------

class TestStreebogBase:
    """Проверка базовой реализации по контрольным векторам ГОСТ."""

    def test_m1_512(self) -> None:
        """M1 → Streebog-512."""
        result = streebog_512(M1)
        assert result.hex() == M1_HASH_512, (
            f"M1/512: ожидалось {M1_HASH_512}, получено {result.hex()}"
        )

    def test_m1_256(self) -> None:
        """M1 → Streebog-256."""
        result = streebog_256(M1)
        assert result.hex() == M1_HASH_256, (
            f"M1/256: ожидалось {M1_HASH_256}, получено {result.hex()}"
        )

    def test_m2_512(self) -> None:
        """M2 → Streebog-512."""
        result = streebog_512(M2)
        assert result.hex() == M2_HASH_512, (
            f"M2/512: ожидалось {M2_HASH_512}, получено {result.hex()}"
        )

    def test_m2_256(self) -> None:
        """M2 → Streebog-256."""
        result = streebog_256(M2)
        assert result.hex() == M2_HASH_256, (
            f"M2/256: ожидалось {M2_HASH_256}, получено {result.hex()}"
        )

    def test_incremental_update(self) -> None:
        """Проверяем, что update по частям даёт тот же результат, что и за один раз."""
        # M2 имеет длину 72 байта — подаём по частям
        h = Streebog(512)
        h.update(M2[:30])
        h.update(M2[30:50])
        h.update(M2[50:])
        assert h.digest().hex() == M2_HASH_512

    def test_empty_message_512(self) -> None:
        """Пустое сообщение → Streebog-512."""
        result = streebog_512(b"")
        expected = (
            "8e945da209aa869f0455928529bcae4679e9873ab707b55315f56ceb98bef0a7"
            "362f715528356ee83cda5f2aac4c6ad2ba3a715c1bcd81cb8e9f90bf4c1c1a8a"
        )
        assert result.hex() == expected, (
            f"empty/512: ожидалось {expected}, получено {result.hex()}"
        )

    def test_empty_message_256(self) -> None:
        """Пустое сообщение → Streebog-256."""
        result = streebog_256(b"")
        expected = (
            "3f539a213e97c802cc229d474c6aa32a825a360b2a933a949fd925208d9ce1bb"
        )
        assert result.hex() == expected, (
            f"empty/256: ожидалось {expected}, получено {result.hex()}"
        )

    def test_copy_produces_same_result(self) -> None:
        """Проверка copy() — клон даёт тот же результат."""
        h = Streebog(512)
        h.update(M1[:40])
        h_copy = h.copy()
        h.update(M1[40:])
        h_copy.update(M1[40:])
        assert h.digest() == h_copy.digest()


# ---------------------------------------------------------------------------
# Тесты для оптимизированной реализации (запускаются после создания streebog_fast)
# ---------------------------------------------------------------------------

class TestStreebogFast:
    """Проверка оптимизированной реализации — должна давать те же результаты."""

    @pytest.fixture(autouse=True)
    def _import_fast(self) -> None:
        """Пытаемся импортировать fast-реализацию; пропускаем если не готова."""
        try:
            from src.streebog_fast import streebog_512_fast, streebog_256_fast
            self._s512 = streebog_512_fast
            self._s256 = streebog_256_fast
        except ImportError:
            pytest.skip("streebog_fast ещё не реализован")

    def test_m1_512_fast(self) -> None:
        assert self._s512(M1).hex() == M1_HASH_512

    def test_m1_256_fast(self) -> None:
        assert self._s256(M1).hex() == M1_HASH_256

    def test_m2_512_fast(self) -> None:
        assert self._s512(M2).hex() == M2_HASH_512

    def test_m2_256_fast(self) -> None:
        assert self._s256(M2).hex() == M2_HASH_256

    def test_empty_512_fast(self) -> None:
        expected = (
            "8e945da209aa869f0455928529bcae4679e9873ab707b55315f56ceb98bef0a7"
            "362f715528356ee83cda5f2aac4c6ad2ba3a715c1bcd81cb8e9f90bf4c1c1a8a"
        )
        assert self._s512(b"").hex() == expected

    def test_empty_256_fast(self) -> None:
        expected = "3f539a213e97c802cc229d474c6aa32a825a360b2a933a949fd925208d9ce1bb"
        assert self._s256(b"").hex() == expected

    def test_fast_matches_base_random(self) -> None:
        """Сравнение base и fast на 100 случайных входах разной длины."""
        import random
        random.seed(42)
        for _ in range(100):
            length = random.randint(0, 1000)
            data = random.randbytes(length)
            assert self._s512(data) == streebog_512(data), f"Mismatch at length {length}"
            assert self._s256(data) == streebog_256(data), f"Mismatch at length {length}"
