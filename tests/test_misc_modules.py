import importlib
import json
import runpy
import sys

from src import collision_search, meaningful_collision


def test_h48_is_first_6_bytes() -> None:
    msg = b"abc"
    full = collision_search.hash_bytes(msg, digest_size=512, impl="fast")
    assert collision_search.h48(msg) == full[:6]


def test_save_result_writes_json(tmp_path) -> None:
    collision_search._save_result(
        str(tmp_path),
        b"\x01",
        b"\x02",
        b"\x03" * 6,
        b"\x04" * 64,
        b"\x05" * 64,
        attempts=2,
        elapsed=0.1,
        peak_memory=1024.0,
        seed=7,
    )
    payload = json.loads((tmp_path / "collision.json").read_text(encoding="utf-8"))
    assert payload["attempts"] == 2
    assert payload["h48_hex"] == ("03" * 6)


def test_precompute_and_hash_with_suffix() -> None:
    img = meaningful_collision._create_bmp(8, 8, meaningful_collision._x_pattern)
    base, rem = meaningful_collision._precompute_hash_state(img)
    d1 = meaningful_collision._hash_with_suffix(base, rem, b"\xAA")
    d2 = meaningful_collision.hash_bytes(img + b"\xAA", digest_size=512, impl="fast")
    assert d1 == d2


def test_save_meaningful_result_writes_files(tmp_path) -> None:
    meaningful_collision._save_meaningful_result(
        str(tmp_path),
        b"BM" + b"\x00" * 10,
        b"BM" + b"\x11" * 10,
        b"\xAA" * 6,
        b"\xBB" * 64,
        b"\xCC" * 64,
        attempts=5,
        elapsed=0.2,
    )
    assert (tmp_path / "image1_X.bmp").exists()
    assert (tmp_path / "image2_O.bmp").exists()
    meta = json.loads((tmp_path / "meaningful_collision.json").read_text())
    assert meta["attempts"] == 5


def test_src_init_exports() -> None:
    mod = importlib.import_module("src")
    assert "streebog_512" in mod.__all__
    assert "create_hasher" in mod.__all__


def test_module_main_invokes_cli_main(monkeypatch) -> None:
    called = {"ok": False}
    monkeypatch.setattr("src.cli.main", lambda: called.__setitem__("ok", True))
    sys.modules.pop("src.__main__", None)
    runpy.run_module("src.__main__", run_name="__main__")
    assert called["ok"] is True


def test_find_collision_quick(monkeypatch, tmp_path) -> None:
    seq = [b"A" * 16, b"B" * 16]
    prefixes = {seq[0]: b"\x99" * 6, seq[1]: b"\x99" * 6}

    class DummyRandom:
        def __init__(self):
            self.i = 0

        def randbytes(self, size: int) -> bytes:
            val = seq[self.i]
            self.i += 1
            return val

    monkeypatch.setattr("random.Random", lambda *a, **k: DummyRandom())
    monkeypatch.setattr(collision_search, "h48", lambda data: prefixes[data])
    monkeypatch.setattr(collision_search, "hash_bytes", lambda data, **k: prefixes[data] + data + b"\x00" * (64 - 6 - len(data)))
    monkeypatch.setattr(collision_search.time, "perf_counter", lambda: 10.0)
    monkeypatch.setattr(collision_search.tracemalloc, "start", lambda: None)
    monkeypatch.setattr(collision_search.tracemalloc, "stop", lambda: None)
    monkeypatch.setattr(collision_search.tracemalloc, "get_traced_memory", lambda: (0, 2048))
    saved = {"ok": False}
    monkeypatch.setattr(collision_search, "_save_result", lambda *args, **kwargs: saved.__setitem__("ok", True))

    m1, m2, p, attempts, _ = collision_search.find_collision(
        seed=1, msg_size=16, max_attempts=10, log_interval=2, out_dir=str(tmp_path)
    )
    assert m1 != m2
    assert p == b"\x99" * 6
    assert attempts == 2
    assert saved["ok"] is True


def test_find_meaningful_collision_quick(monkeypatch, tmp_path) -> None:
    def fake_create_bmp(width, height, pixels_func):
        marker = b"\x01" if pixels_func is meaningful_collision._x_pattern else b"\x02"
        return b"BM" + marker + b"\x00" * 99

    monkeypatch.setattr(meaningful_collision, "_create_bmp", fake_create_bmp)

    class DummyRandom:
        def randbytes(self, size: int) -> bytes:
            return b"\x01" * size

    monkeypatch.setattr("random.Random", lambda *a, **k: DummyRandom())
    monkeypatch.setattr(meaningful_collision, "_precompute_hash_state", lambda image: (object(), bytearray()))

    calls = {"n": 0}

    def fake_hash_with_suffix(base, rem, suffix):
        calls["n"] += 1
        # 1-й вызов A, 2-й вызов B -> сразу коллизия
        if calls["n"] in (1, 2):
            return b"\x77" * 6 + b"\x00" * 58
        return b"\x88" * 6 + b"\x00" * 58

    monkeypatch.setattr(meaningful_collision, "_hash_with_suffix", fake_hash_with_suffix)
    monkeypatch.setattr(meaningful_collision, "hash_bytes", lambda data, **k: b"\x77" * 6 + b"\x11" * 58)
    monkeypatch.setattr(meaningful_collision.time, "perf_counter", lambda: 20.0)
    monkeypatch.setattr(meaningful_collision.tracemalloc, "start", lambda: None)
    monkeypatch.setattr(meaningful_collision.tracemalloc, "stop", lambda: None)
    monkeypatch.setattr(meaningful_collision.tracemalloc, "get_traced_memory", lambda: (0, 1024))
    saved = {"ok": False}
    monkeypatch.setattr(meaningful_collision, "_save_meaningful_result", lambda *a, **k: saved.__setitem__("ok", True))

    a, b, p = meaningful_collision.find_meaningful_collision(
        out_dir=str(tmp_path), suffix_size=4, max_attempts=4, log_interval=2
    )
    assert a != b
    assert p == b"\x77" * 6
    assert saved["ok"] is True

