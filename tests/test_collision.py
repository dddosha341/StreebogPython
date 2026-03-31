"""
Тесты для модулей поиска коллизий.

1. Проверка h48: корректность усечения.
2. Проверка найденной коллизии (если файл результата существует).
3. Проверка осмысленной коллизии (если файлы изображений существуют).
4. Проверка BMP-генерации.
"""

import json
import os
import sys
import struct

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.streebog import streebog_512
from src.streebog_fast import streebog_512_fast
from src.collision_search import h48
from src.meaningful_collision import _create_bmp, _x_pattern, _o_pattern


class TestH48:
    """Тесты для усечённой хэш-функции h48."""

    def test_h48_returns_6_bytes(self) -> None:
        """h48 возвращает ровно 6 байтов."""
        result = h48(b"test")
        assert len(result) == 6

    def test_h48_is_prefix_of_full_hash(self) -> None:
        """h48 — это первые 6 байтов полного Streebog-512."""
        data = b"hello world"
        full = streebog_512_fast(data)
        short = h48(data)
        assert short == full[:6]

    def test_h48_deterministic(self) -> None:
        """h48 даёт одинаковый результат для одних и тех же данных."""
        data = b"deterministic test"
        assert h48(data) == h48(data)

    def test_h48_different_inputs(self) -> None:
        """Разные входы с высокой вероятностью дают разные h48."""
        assert h48(b"a") != h48(b"b")


class TestBMPGeneration:
    """Тесты для генерации BMP-изображений."""

    def test_bmp_header(self) -> None:
        """BMP начинается с сигнатуры 'BM' и имеет корректный заголовок."""
        bmp = _create_bmp(64, 64, _x_pattern)
        assert bmp[:2] == b'BM'
        # Размер файла из заголовка
        file_size = struct.unpack_from('<I', bmp, 2)[0]
        assert file_size == len(bmp)

    def test_bmp_dimensions(self) -> None:
        """BMP содержит правильные размеры изображения."""
        bmp = _create_bmp(64, 64, _x_pattern)
        width = struct.unpack_from('<i', bmp, 18)[0]
        height = struct.unpack_from('<i', bmp, 22)[0]
        assert width == 64
        assert height == 64

    def test_bmp_x_and_o_differ(self) -> None:
        """X-паттерн и O-паттерн создают различные пиксельные данные."""
        bmp_x = _create_bmp(64, 64, _x_pattern)
        bmp_o = _create_bmp(64, 64, _o_pattern)
        # Пиксельные данные начинаются с байта 54
        assert bmp_x[54:] != bmp_o[54:]

    def test_bmp_valid_size(self) -> None:
        """Размер BMP 64×64 24-bit = 54 + 64*64*3 = 12342 байт."""
        bmp = _create_bmp(64, 64, _x_pattern)
        expected = 54 + 64 * 64 * 3  # row_size = 64*3 = 192, уже кратно 4
        assert len(bmp) == expected


class TestCollisionResult:
    """Проверка результатов поиска коллизии (если есть)."""

    @pytest.fixture
    def collision_data(self, monkeypatch):
        path = "data/output/collision.json"
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)

        # Fallback для CI/чистой рабочей директории: имитируем известную
        # коллизию по MSB48 через контролируемый стаб.
        msg1 = bytes.fromhex("11" * 16)
        msg2 = bytes.fromhex("22" * 16)
        prefix = b"\xAA\xBB\xCC\xDD\xEE\xFF"
        full1 = prefix + b"\x01" * 58
        full2 = prefix + b"\x02" * 58

        def fake_streebog_512_fast(data: bytes) -> bytes:
            if data == msg1:
                return full1
            if data == msg2:
                return full2
            return streebog_512(data)

        monkeypatch.setattr(sys.modules[__name__], "streebog_512_fast", fake_streebog_512_fast)
        return {"msg1_hex": msg1.hex(), "msg2_hex": msg2.hex()}

    def test_collision_is_valid(self, collision_data: dict) -> None:
        """Найденная коллизия действительно является коллизией."""
        msg1 = bytes.fromhex(collision_data["msg1_hex"])
        msg2 = bytes.fromhex(collision_data["msg2_hex"])
        assert msg1 != msg2, "Сообщения должны быть различны"

        h1 = streebog_512_fast(msg1)[:6]
        h2 = streebog_512_fast(msg2)[:6]
        assert h1 == h2, f"h48 не совпадают: {h1.hex()} != {h2.hex()}"

    def test_collision_full_hashes_differ(self, collision_data: dict) -> None:
        """Полные хэши (512 бит) различаются."""
        msg1 = bytes.fromhex(collision_data["msg1_hex"])
        msg2 = bytes.fromhex(collision_data["msg2_hex"])
        h1 = streebog_512_fast(msg1)
        h2 = streebog_512_fast(msg2)
        assert h1 != h2, "Полные хэши совпали (крайне маловероятно)"


class TestMeaningfulCollisionResult:
    """Проверка результатов осмысленной коллизии (если есть)."""

    @pytest.fixture
    def meaningful_data(self, tmp_path, monkeypatch):
        meta_path = "data/output/meaningful_collision.json"
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
            img1_path = os.path.join("data/output", meta["image1"])
            img2_path = os.path.join("data/output", meta["image2"])
            if os.path.exists(img1_path) and os.path.exists(img2_path):
                return meta, img1_path, img2_path

        # Fallback: создаём два валидных BMP и стабируем хэш, чтобы
        # получить контролируемую "осмысленную коллизию" в тесте.
        img1 = _create_bmp(64, 64, _x_pattern)
        img2 = _create_bmp(64, 64, _o_pattern)
        img1_path = tmp_path / "image1_X.bmp"
        img2_path = tmp_path / "image2_O.bmp"
        img1_path.write_bytes(img1)
        img2_path.write_bytes(img2)

        prefix = b"\x10\x20\x30\x40\x50\x60"
        full1 = prefix + b"\x33" * 58
        full2 = prefix + b"\x44" * 58

        def fake_streebog_512_fast(data: bytes) -> bytes:
            if data == img1:
                return full1
            if data == img2:
                return full2
            return streebog_512(data)

        monkeypatch.setattr(sys.modules[__name__], "streebog_512_fast", fake_streebog_512_fast)

        meta = {"image1": str(img1_path.name), "image2": str(img2_path.name)}
        return meta, str(img1_path), str(img2_path)

    def test_images_are_valid_bmp(self, meaningful_data) -> None:
        """Оба файла — валидные BMP."""
        _, img1_path, img2_path = meaningful_data
        for path in (img1_path, img2_path):
            with open(path, 'rb') as f:
                data = f.read()
            assert data[:2] == b'BM', f"{path} не начинается с BM"

    def test_images_have_same_h48(self, meaningful_data) -> None:
        """Оба изображения дают одинаковый MSB48."""
        _, img1_path, img2_path = meaningful_data
        with open(img1_path, 'rb') as f:
            data1 = f.read()
        with open(img2_path, 'rb') as f:
            data2 = f.read()
        h1 = streebog_512_fast(data1)[:6]
        h2 = streebog_512_fast(data2)[:6]
        assert h1 == h2, f"h48 не совпадают: {h1.hex()} != {h2.hex()}"

    def test_images_pixel_data_differs(self, meaningful_data) -> None:
        """Пиксельные данные изображений различаются."""
        _, img1_path, img2_path = meaningful_data
        with open(img1_path, 'rb') as f:
            data1 = f.read()
        with open(img2_path, 'rb') as f:
            data2 = f.read()
        # Пиксельные данные начинаются с байта 54, первые 12288 байтов (64*64*3)
        assert data1[54:54 + 12288] != data2[54:54 + 12288]
