import io
import os
import sys
import types

import pytest

from src import benchmark, cli


def test_benchmark_single_runs_iterations() -> None:
    calls = {"n": 0}

    def fake_hash(data: bytes) -> bytes:
        calls["n"] += 1
        return data

    avg = benchmark._benchmark_single(fake_hash, b"x", iterations=5)
    assert calls["n"] == 5
    assert avg >= 0


def test_run_benchmark_with_small_sizes() -> None:
    results = benchmark.run_benchmark(sizes=[("tiny", 8)], min_time=0.0001)
    assert len(results) == 1
    assert results[0]["label"] == "tiny"
    assert results[0]["speedup"] > 0


def test_save_chart_without_matplotlib(monkeypatch, tmp_path, capsys) -> None:
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "matplotlib":
            raise ImportError("no matplotlib in test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    benchmark.save_chart([{"label": "x", "base_ms": 1, "fast_ms": 1, "speedup": 1}], str(tmp_path / "a.png"))
    assert "matplotlib не установлен" in capsys.readouterr().out


def test_cmd_hash_from_file(monkeypatch, tmp_path, capsys) -> None:
    p = tmp_path / "sample.bin"
    p.write_bytes(b"abc")

    class DummyHasher:
        digest_size = 512

        def __init__(self) -> None:
            self._data = b""

        def update(self, data: bytes) -> None:
            self._data += data

        def hexdigest(self) -> str:
            return self._data.hex()

        def digest(self) -> bytes:
            return self._data

        def copy(self):
            return self

    monkeypatch.setattr("src.hasher_interface.create_hasher", lambda **kwargs: DummyHasher())
    args = type("Args", (), {"file": str(p), "fast": False, "alg": 512})
    cli.cmd_hash(args)
    assert capsys.readouterr().out.strip() == "616263"


def test_cmd_hash_from_stdin(monkeypatch, capsys) -> None:
    class DummyHasher:
        digest_size = 512

        def __init__(self) -> None:
            self._data = b""

        def update(self, data: bytes) -> None:
            self._data += data

        def hexdigest(self) -> str:
            return "ok-" + self._data.decode("ascii")

        def digest(self) -> bytes:
            return self._data

        def copy(self):
            return self

    monkeypatch.setattr("src.hasher_interface.create_hasher", lambda **kwargs: DummyHasher())
    monkeypatch.setattr(sys, "stdin", type("S", (), {"buffer": io.BytesIO(b"xyz")})())
    args = type("Args", (), {"file": None, "fast": True, "alg": 256})
    cli.cmd_hash(args)
    assert capsys.readouterr().out.strip() == "ok-xyz"


def test_main_without_command_exits(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["streebog"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1


def test_main_dispatches_hash(monkeypatch) -> None:
    called = {"ok": False}

    def fake_cmd(args):
        called["ok"] = True

    monkeypatch.setattr(cli, "cmd_hash", fake_cmd)
    monkeypatch.setattr(sys, "argv", ["streebog", "hash", "--alg", "512"])
    cli.main()
    assert called["ok"] is True


def test_main_dispatches_other_commands(monkeypatch) -> None:
    flags = {"collision": 0, "meaningful": 0, "bench": 0, "selftest": 0}
    monkeypatch.setattr(cli, "cmd_collision", lambda args: flags.__setitem__("collision", 1))
    monkeypatch.setattr(cli, "cmd_meaningful_collision", lambda args: flags.__setitem__("meaningful", 1))
    monkeypatch.setattr(cli, "cmd_bench", lambda args: flags.__setitem__("bench", 1))
    monkeypatch.setattr(cli, "cmd_selftest", lambda args: flags.__setitem__("selftest", 1))

    monkeypatch.setattr(sys, "argv", ["streebog", "collision"])
    cli.main()
    monkeypatch.setattr(sys, "argv", ["streebog", "meaningful-collision"])
    cli.main()
    monkeypatch.setattr(sys, "argv", ["streebog", "bench"])
    cli.main()
    monkeypatch.setattr(sys, "argv", ["streebog", "selftest"])
    cli.main()
    assert flags == {"collision": 1, "meaningful": 1, "bench": 1, "selftest": 1}


def test_cmd_collision_and_meaningful_and_bench(monkeypatch, tmp_path) -> None:
    seen = {"collision": False, "meaningful": False, "chart": False}

    monkeypatch.setattr("src.collision_search.find_collision", lambda **kwargs: seen.__setitem__("collision", True))
    monkeypatch.setattr("src.meaningful_collision.find_meaningful_collision", lambda **kwargs: seen.__setitem__("meaningful", True))
    monkeypatch.setattr("src.benchmark.run_benchmark", lambda: [{"label": "x"}])
    monkeypatch.setattr("src.benchmark.save_chart", lambda results, path: seen.__setitem__("chart", path.endswith(".png")))

    cli.cmd_collision(type("Args", (), {"seed": 1, "out_dir": str(tmp_path), "max_attempts": 10}))
    cli.cmd_meaningful_collision(type("Args", (), {"out_dir": str(tmp_path), "max_attempts": 10}))
    cli.cmd_bench(type("Args", (), {"chart": str(tmp_path / "c.png")}))
    assert seen == {"collision": True, "meaningful": True, "chart": True}


def test_cmd_selftest_success(monkeypatch, capsys) -> None:
    from tests.test_vectors import M1, M2, M1_HASH_512, M1_HASH_256, M2_HASH_512, M2_HASH_256

    mapping_512 = {M1: bytes.fromhex(M1_HASH_512), M2: bytes.fromhex(M2_HASH_512), b"": bytes.fromhex(
        "8e945da209aa869f0455928529bcae4679e9873ab707b55315f56ceb98bef0a7"
        "362f715528356ee83cda5f2aac4c6ad2ba3a715c1bcd81cb8e9f90bf4c1c1a8a"
    )}
    mapping_256 = {M1: bytes.fromhex(M1_HASH_256), M2: bytes.fromhex(M2_HASH_256), b"": bytes.fromhex(
        "3f539a213e97c802cc229d474c6aa32a825a360b2a933a949fd925208d9ce1bb"
    )}

    monkeypatch.setattr("src.streebog.streebog_512", lambda data: mapping_512.get(data, b"\xAB" * 64))
    monkeypatch.setattr("src.streebog.streebog_256", lambda data: mapping_256.get(data, b"\xCD" * 32))
    monkeypatch.setattr("src.streebog_fast.streebog_512_fast", lambda data: mapping_512.get(data, b"\xAB" * 64))
    monkeypatch.setattr("src.streebog_fast.streebog_256_fast", lambda data: mapping_256.get(data, b"\xCD" * 32))
    monkeypatch.setattr("random.randbytes", lambda n: b"\x42" * n)
    monkeypatch.setattr("random.randint", lambda a, b: 5)
    cli.cmd_selftest(type("Args", (), {}))
    assert "Все тесты пройдены!" in capsys.readouterr().out


def test_save_chart_with_fake_matplotlib(monkeypatch, tmp_path) -> None:
    class DummyAx:
        def bar(self, *args, **kwargs):
            return None

        def set_xlabel(self, *args, **kwargs):
            return None

        def set_ylabel(self, *args, **kwargs):
            return None

        def set_title(self, *args, **kwargs):
            return None

        def set_xticks(self, *args, **kwargs):
            return None

        def set_xticklabels(self, *args, **kwargs):
            return None

        def legend(self, *args, **kwargs):
            return None

        def set_yscale(self, *args, **kwargs):
            return None

        def grid(self, *args, **kwargs):
            return None

        def axhline(self, *args, **kwargs):
            return None

    class DummyPltModule(types.ModuleType):
        def __init__(self):
            super().__init__("matplotlib.pyplot")

        def subplots(self, *args, **kwargs):
            return object(), (DummyAx(), DummyAx())

        def tight_layout(self):
            return None

        def savefig(self, path, dpi=150):
            with open(path, "wb") as f:
                f.write(b"x")

    dummy_matplotlib = types.ModuleType("matplotlib")
    dummy_matplotlib.use = lambda backend: None
    monkeypatch.setitem(sys.modules, "matplotlib", dummy_matplotlib)
    monkeypatch.setitem(sys.modules, "matplotlib.pyplot", DummyPltModule())
    out = tmp_path / "chart.png"
    benchmark.save_chart([{"label": "x", "base_ms": 1, "fast_ms": 0.5, "speedup": 2}], str(out))
    assert out.exists()

