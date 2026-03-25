"""
Базовая (референсная) реализация алгоритма Стрибог — ГОСТ 34.11-2018.

Это чистая, понятная реализация, строго следующая стандарту.
Каждая операция (S, P, L, LPS, E, g_N, padding, финализация)
выделена в отдельную функцию с комментариями.

Порядок байтов / endianness:
- Состояние хэша (h), сообщение, ключи — массивы из 64 байтов.
- Арифметика счётчика N и контрольной суммы Σ — little-endian.
- S-box применяется побайтово к массиву.
- P — перестановка элементов массива байтов.
- L — обрабатывает 8 групп по 8 байтов; каждая группа — 64-бит слово в little-endian.
- MSB (старшие биты) в little-endian представлении — это последние байты массива.
  Поэтому Streebog-256 возвращает h[32:64].
"""

from __future__ import annotations

import copy
from typing import Optional

from .constants import PI, TAU, A, C, IV_512, IV_256, BLOCK_SIZE, N_BLOCK_BITS
from .utils import xor_bytes, add_mod512


# ---------------------------------------------------------------------------
# Примитивы преобразования (S, P, L, LPS, X)
# ---------------------------------------------------------------------------

def _S(state: bytearray) -> bytearray:
    """
    Нелинейная подстановка S (SubBytes).
    Каждый байт заменяется через таблицу PI (π).
    """
    return bytearray(PI[b] for b in state)


def _P(state: bytearray) -> bytearray:
    """
    Перестановка P (Permutation).
    Переставляет байты состояния по таблице TAU (τ).
    Эквивалентно транспозиции матрицы 8×8.
    """
    return bytearray(state[TAU[i]] for i in range(64))


def _L(state: bytearray) -> bytearray:
    """
    Линейное преобразование L.

    Состояние разбивается на 8 групп по 8 байтов.
    Каждая группа интерпретируется как 64-битное слово (little-endian)
    и умножается на матрицу A в GF(2):

        result = 0
        for j in range(64):
            if bit j of word is set:
                result ^= A[j]

    Бит 0 (LSB) первого байта группы соответствует A[0],
    бит 7 первого байта — A[7], бит 0 второго байта — A[8], и т.д.
    """
    result = bytearray(64)
    for i in range(8):
        # Извлекаем 64-битное слово (little-endian)
        val = int.from_bytes(state[i * 8:(i + 1) * 8], byteorder='little')
        res = 0
        # Перебираем все 64 бита слова
        t = val
        for j in range(64):
            if t & 1:
                res ^= A[j]
            t >>= 1
        result[i * 8:(i + 1) * 8] = res.to_bytes(8, byteorder='little')
    return result


def _LPS(state: bytearray) -> bytearray:
    """
    Композиция L ∘ P ∘ S — один раунд подстановочно-перестановочной сети.
    """
    return _L(_P(_S(state)))


def _X(k: bytearray, a: bytearray) -> bytearray:
    """
    Сложение ключа X[k] — побайтовый XOR.
    """
    return xor_bytes(k, a)


# ---------------------------------------------------------------------------
# Блочный шифр E (12 раундов)
# ---------------------------------------------------------------------------

def _E(K: bytearray, m: bytearray) -> bytearray:
    """
    Блочный шифр E(K, m) — 12-раундовая подстановочно-перестановочная сеть.

    Структура:
        state = K ⊕ m           (первый ключевой XOR, ключ K₁ = K)
        for i = 1..12:
            state = LPS(state)
            K = LPS(K ⊕ C[i])   (вычисление следующего раундового ключа)
            state = K ⊕ state
        return state

    Итого: 13 ключевых XOR-ов (K₁..K₁₃) и 12 применений LPS к состоянию.
    """
    state = _X(K, m)
    for i in range(12):
        state = _LPS(state)
        K = _LPS(_X(K, bytearray(C[i])))
        state = _X(K, state)
    return state


# ---------------------------------------------------------------------------
# Функция сжатия g_N
# ---------------------------------------------------------------------------

def _g_N(N: bytearray, h: bytearray, m: bytearray) -> bytearray:
    """
    Функция сжатия g_N(h, m):
        K = LPS(h ⊕ N)
        return E(K, m) ⊕ h ⊕ m

    Это вариант конструкции Миягучи-Пренеля.
    N — значение счётчика (64 байта), влияет на ключ.
    """
    K = _LPS(_X(bytearray(N), bytearray(h)))
    t = _E(K, bytearray(m))
    return _X(_X(t, bytearray(h)), bytearray(m))


# ---------------------------------------------------------------------------
# Класс Streebog — потоковый интерфейс (update / digest)
# ---------------------------------------------------------------------------

class Streebog:
    """
    Реализация хэш-функции Стрибог (ГОСТ 34.11-2018).

    Поддерживает два режима:
      - digest_size=512 → Streebog-512 (IV = 0x00 * 64)
      - digest_size=256 → Streebog-256 (IV = 0x01 * 64)

    Использование:
        h = Streebog(512)
        h.update(data)
        result = h.digest()

    Или через вспомогательные функции:
        result = streebog_512(data)
        result = streebog_256(data)
    """

    def __init__(self, digest_size: int = 512) -> None:
        if digest_size not in (256, 512):
            raise ValueError("digest_size must be 256 or 512")
        self.digest_size = digest_size
        self.h = bytearray(IV_256 if digest_size == 256 else IV_512)
        self.N = bytearray(64)       # счётчик обработанных бит (little-endian)
        self.sigma = bytearray(64)   # контрольная сумма Σ (аккумулятор блоков)
        self._buf = bytearray()      # буфер для неполного блока

    def copy(self) -> Streebog:
        """Создаёт глубокую копию состояния хэшера (для collision search)."""
        return copy.deepcopy(self)

    def update(self, data: bytes | bytearray) -> None:
        """
        Подаёт данные на вход хэш-функции.

        Полные 64-байтовые блоки обрабатываются сразу через g_N.
        Неполный остаток буферизуется до следующего вызова update или digest.
        """
        self._buf.extend(data)
        while len(self._buf) >= BLOCK_SIZE:
            block = bytearray(self._buf[:BLOCK_SIZE])
            self._buf = self._buf[BLOCK_SIZE:]
            # Сжатие: h = g_N(N, h, block)
            self.h = _g_N(self.N, self.h, block)
            # Обновляем счётчик бит: N += 512
            self.N = add_mod512(self.N, N_BLOCK_BITS)
            # Обновляем контрольную сумму: Σ += block (как 512-бит LE число)
            self.sigma = add_mod512(self.sigma, block)

    def digest(self) -> bytes:
        """
        Финализирует хэш и возвращает результат.

        Этапы финализации (ГОСТ 34.11-2018, раздел 6):
        1. Дополнение (padding): оставшиеся байты дополняются до 64 байтов:
           - в позицию len(buf) ставится байт 0x01
           - остальные байты (от len(buf)+1 до 63) — нули
           Сообщение M размещается в начале блока (младшие байты).

        2. Обработка дополненного блока:
           h = g_N(N, h, padded_block)
           N += len(buf) * 8
           Σ += padded_block

        3. Финальные сжатия (с N = 0):
           h = g_0(h, N)
           h = g_0(h, Σ)

        4. Усечение для 256-бит варианта:
           Возвращаются последние 32 байта (MSB в LE-представлении).
        """
        # Работаем с копией состояния, чтобы digest() можно было вызвать повторно
        h = bytearray(self.h)
        N = bytearray(self.N)
        sigma = bytearray(self.sigma)
        buf = bytearray(self._buf)

        # --- Шаг 1: Дополнение (padding) ---
        remaining = len(buf)
        padded = bytearray(64)
        padded[:remaining] = buf
        # Байт 0x01 ставится сразу после данных сообщения.
        # Если remaining < 64, позиция [remaining] = 0x01.
        # Если remaining == 0, весь блок = 0x01 || 0x00^63.
        padded[remaining] = 0x01

        # --- Шаг 2: Обработка дополненного блока ---
        h = _g_N(N, h, padded)
        # Обновляем N на количество бит в неполном блоке
        bits_remaining = bytearray((remaining * 8).to_bytes(64, byteorder='little'))
        N = add_mod512(N, bits_remaining)
        # Обновляем Σ
        sigma = add_mod512(sigma, padded)

        # --- Шаг 3: Финальные сжатия ---
        zero = bytearray(64)
        h = _g_N(zero, h, N)
        h = _g_N(zero, h, sigma)

        # --- Шаг 4: Усечение ---
        if self.digest_size == 256:
            # MSB₂₅₆ — старшие 256 бит = последние 32 байта в LE-представлении
            return bytes(h[32:])
        return bytes(h)

    def hexdigest(self) -> str:
        """Возвращает хэш в виде шестнадцатеричной строки."""
        return self.digest().hex()


# ---------------------------------------------------------------------------
# Вспомогательные функции (удобные обёртки)
# ---------------------------------------------------------------------------

def streebog_512(data: bytes) -> bytes:
    """Вычисляет Streebog-512 от данных. Возвращает 64 байта."""
    h = Streebog(512)
    h.update(data)
    return h.digest()


def streebog_256(data: bytes) -> bytes:
    """Вычисляет Streebog-256 от данных. Возвращает 32 байта."""
    h = Streebog(256)
    h.update(data)
    return h.digest()
