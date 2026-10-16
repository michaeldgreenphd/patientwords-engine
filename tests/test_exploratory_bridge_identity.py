"""Source-checkout binding for the synthetic bridge, without model runtimes."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

BRIDGE = Path(__file__).parent / "manual" / "exploratory_bridge.py"


@pytest.fixture
def bridge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, Path]:
    root = tmp_path / "adapter"
    source = root / "src" / "lens_interop" / "artifact.py"
    source.parent.mkdir(parents=True)
    source.write_text("def load_verified_lens(): pass\ndef paired_readouts(): pass\n")
    adapter = ModuleType("lens_interop")
    exec(compile(source.read_text(), str(source), "exec"), adapter.__dict__)
    monkeypatch.setitem(sys.modules, "lens_interop", adapter)
    monkeypatch.setitem(sys.modules, "torch", ModuleType("torch"))
    spec = importlib.util.spec_from_file_location("source_checked_bridge", BRIDGE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, root


def test_matching_checkout_and_symlink_succeed(bridge: tuple[ModuleType, Path], tmp_path: Path) -> None:
    module, root = bridge
    module.require_jpp_checkout(root)
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    module.require_jpp_checkout(alias)


@pytest.mark.parametrize("name", ["load_verified_lens", "paired_readouts"])
def test_each_import_must_come_from_declared_checkout(
    bridge: tuple[ModuleType, Path], tmp_path: Path, name: str,
) -> None:
    module, root = bridge
    foreign = tmp_path / "other.py"
    foreign.write_text(f"def {name}(): pass\n")
    namespace: dict = {}
    exec(compile(foreign.read_text(), str(foreign), "exec"), namespace)
    setattr(module, name, namespace[name])
    with pytest.raises(ValueError, match="jpp_source_mismatch"):
        module.require_jpp_checkout(root)


def test_wrong_declared_root_refuses_before_output_creation(
    bridge: tuple[ModuleType, Path], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> None:
    module, root = bridge
    other = tmp_path / "other"
    source = other / "src" / "lens_interop" / "artifact.py"
    source.parent.mkdir(parents=True)
    source.write_bytes((root / "src" / "lens_interop" / "artifact.py").read_bytes())
    output = tmp_path / "exploratory_methods"
    monkeypatch.setattr(sys, "argv", [str(BRIDGE), "--jpp-root", str(other), "--out", str(output)])
    with pytest.raises(SystemExit) as caught:
        module.main()
    assert caught.value.code == 2
    assert "jpp_source_mismatch" in capsys.readouterr().err
    assert not output.exists()
