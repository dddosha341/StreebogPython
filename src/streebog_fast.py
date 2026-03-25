"""
Оптимизированная реализация Стрибог (ГОСТ 34.11-2018) с предвычисленными T-таблицами.

Ключевая оптимизация: объединение S, P и L преобразований в 8 таблиц.

=== Математическое обоснование ===

Операция LPS(x) = L(P(S(x))) вычисляет:
1. S: x[i] → PI[x[i]] (подстановка каждого байта)
2. P: перестановка байтов по TAU (транспозиция 8×8)
3. L: для каждой 8-байтовой группы — GF(2)-умножение на матрицу A

После S и P, для L-группы g (байты g*8..g*8+7):
  p[g*8 + k] = PI[x[k*8 + g]]  (где k = 0..7)

L-преобразование каждой группы: val = XOR of A[k*8+bit] for set bits at positions k*8+bit
Это можно разложить: для каждого подбайта k, вклад = f(PI[x[k*8+g]], k)

T-таблица T[k][v] = XOR of A[k*8 + bit] for each set bit in PI[v]

Тогда: LPS-группа g = T[0][x[g]] ^ T[1][x[8+g]] ^ T[2][x[16+g]] ^ ... ^ T[7][x[56+g]]

Это заменяет ~64 S-подстановки + перестановку + 8×64 GF(2)-операции
на 64 табличных подстановки + 64 XOR-а 64-битных чисел.

=== Эквивалентность ===

Результат T-табличного LPS полностью идентичен последовательному S→P→L,
так как все три преобразования линейны относительно отдельных байтов
(S нелинейна, но фиксирована для каждого байта), а T-таблица кодирует
полный эффект одного входного байта на выходной 64-битный вектор.
"""

from __future__ import annotations

import copy
from typing import List, Tuple

from .constants import PI, TAU, A, C, IV_512, IV_256, BLOCK_SIZE, N_BLOCK_BITS
from .utils import xor_bytes, add_mod512


# ---------------------------------------------------------------------------
# Предвычисление T-таблиц (выполняется один раз при импорте модуля)
# ---------------------------------------------------------------------------

def _precompute_tables() -> Tuple[Tuple[int, ...], ...]:
    """
    Строит 8 таблиц T[k], k = 0..7.
    Каждая таблица содержит 256 записей (по одной для каждого возможного байта).
    T[k][v] — это 64-битное целое число, представляющее вклад значения PI[v]
    на позиции k в 8-байтовой группе L-преобразования.

    T[k][v] = XOR of A[k*8 + bit] for each set bit in PI[v]
    """
    tables: List[Tuple[int, ...]] = []
    for k in range(8):
        table: List[int] = []
        base = k * 8  # начальный индекс в массиве A
        for v in range(256):
            sv = PI[v]  # применяем S-box
            val = 0
            for bit in range(8):
                if sv & (1 << bit):
                    val ^= A[base + bit]
            table.append(val)
        tables.append(tuple(table))
    return tuple(tables)


# Таблицы вычисляются один раз при загрузке модуля (~16 КБ памяти)
T: Tuple[Tuple[int, ...], ...] = _precompute_tables()


# ---------------------------------------------------------------------------
# Оптимизированный LPS через T-таблицы
# ---------------------------------------------------------------------------

def _LPS_fast(state: bytearray) -> bytearray:
    """
    Объединённое преобразование L(P(S(state))) через T-таблицы.

    Для каждой из 8 выходных 64-битных групп (g = 0..7):
      result_g = T[0][state[g]] ^ T[1][state[8+g]] ^ T[2][state[16+g]]
                ^ T[3][state[24+g]] ^ T[4][state[32+g]] ^ T[5][state[40+g]]
                ^ T[6][state[48+g]] ^ T[7][state[56+g]]

    Обоснование индексации: state[k*8 + g] — это байт, который после
    S-подстановки и P-перестановки оказывается на позиции k в L-группе g.
    """
    result = bytearray(64)
    t0, t1, t2, t3, t4, t5, t6, t7 = T
    for g in range(8):
        val = (t0[state[g]] ^ t1[state[8 + g]] ^ t2[state[16 + g]]
               ^ t3[state[24 + g]] ^ t4[state[32 + g]] ^ t5[state[40 + g]]
               ^ t6[state[48 + g]] ^ t7[state[56 + g]])
        result[g * 8:(g + 1) * 8] = val.to_bytes(8, byteorder='little')
    return result


# ---------------------------------------------------------------------------
# Блочный шифр E и функция сжатия g_N (идентичны базовой версии,
# но используют _LPS_fast вместо _LPS)
# ---------------------------------------------------------------------------

def _X_fast(k: bytearray, a: bytearray) -> bytearray:
    """Сложение ключа (XOR)."""
    return xor_bytes(k, a)


def _E_fast(K: bytearray, m: bytearray) -> bytearray:
    """Блочный шифр E — 12 раундов с T-табличным LPS."""
    state = _X_fast(K, m)
    for i in range(12):
        state = _LPS_fast(state)
        K = _LPS_fast(_X_fast(K, bytearray(C[i])))
        state = _X_fast(K, state)
    return state


def _g_N_fast(N: bytearray, h: bytearray, m: bytearray) -> bytearray:
    """Функция сжатия g_N с T-табличным LPS."""
    K = _LPS_fast(_X_fast(bytearray(N), bytearray(h)))
    t = _E_fast(K, bytearray(m))
    return _X_fast(_X_fast(t, bytearray(h)), bytearray(m))


# ---------------------------------------------------------------------------
# Класс StreebogFast — потоковый интерфейс
# ---------------------------------------------------------------------------

class StreebogFast:
    """
    Оптимизированная реализация Стрибог с T-таблицами.
    Полностью эквивалентна базовой реализации, но быстрее за счёт
    предвычисленных таблиц для LPS-преобразования.
    """

    def __init__(self, digest_size: int = 512) -> None:
        if digest_size not in (256, 512):
            raise ValueError("digest_size must be 256 or 512")
        self.digest_size = digest_size
        self.h = bytearray(IV_256 if digest_size == 256 else IV_512)
        self.N = bytearray(64)
        self.sigma = bytearray(64)
        self._buf = bytearray()

    def copy(self) -> StreebogFast:
        """Глубокая копия состояния."""
        return copy.deepcopy(self)

    def update(self, data: bytes | bytearray) -> None:
        """Подаёт данные на вход."""
        self._buf.extend(data)
        while len(self._buf) >= BLOCK_SIZE:
            block = bytearray(self._buf[:BLOCK_SIZE])
            self._buf = self._buf[BLOCK_SIZE:]
            self.h = _g_N_fast(self.N, self.h, block)
            self.N = add_mod512(self.N, N_BLOCK_BITS)
            self.sigma = add_mod512(self.sigma, block)

    def digest(self) -> bytes:
        """Финализирует и возвращает хэш."""
        h = bytearray(self.h)
        N = bytearray(self.N)
        sigma = bytearray(self.sigma)
        buf = bytearray(self._buf)

        remaining = len(buf)
        padded = bytearray(64)
        padded[:remaining] = buf
        padded[remaining] = 0x01

        h = _g_N_fast(N, h, padded)
        bits_remaining = bytearray((remaining * 8).to_bytes(64, byteorder='little'))
        N = add_mod512(N, bits_remaining)
        sigma = add_mod512(sigma, padded)

        zero = bytearray(64)
        h = _g_N_fast(zero, h, N)
        h = _g_N_fast(zero, h, sigma)

        if self.digest_size == 256:
            return bytes(h[32:])
        return bytes(h)

    def hexdigest(self) -> str:
        """Хэш в hex-формате."""
        return self.digest().hex()


# ---------------------------------------------------------------------------
# Удобные обёртки
# ---------------------------------------------------------------------------

def streebog_512_fast(data: bytes) -> bytes:
    """Вычисляет Streebog-512 (оптимизированная версия). Возвращает 64 байта."""
    h = StreebogFast(512)
    h.update(data)
    return h.digest()


def streebog_256_fast(data: bytes) -> bytes:
    """Вычисляет Streebog-256 (оптимизированная версия). Возвращает 32 байта."""
    h = StreebogFast(256)
    h.update(data)
    return h.digest()
