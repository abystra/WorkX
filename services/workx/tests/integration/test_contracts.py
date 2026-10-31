"""Repository-level gates: committed OpenAPI is current; import-linter rules hold and actually catch violations."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from workx.entrypoints.cli import REPO_ROOT, main


def test_openapi_contract_is_current() -> None:
    assert main(["openapi", "--check"]) == 0


def _lint_imports(cwd: Path, pythonpath: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(pythonpath)}
    binary = Path(sys.executable).with_name("lint-imports")
    return subprocess.run([str(binary)], cwd=cwd, env=env, capture_output=True, text=True, check=False)


def test_import_contracts_hold() -> None:
    result = _lint_imports(REPO_ROOT, REPO_ROOT / "services" / "workx" / "src")
    assert result.returncode == 0, result.stdout + result.stderr


def test_import_contracts_catch_domain_importing_trusted(tmp_path: Path) -> None:
    src = tmp_path / "src"
    shutil.copytree(REPO_ROOT / "services" / "workx" / "src" / "workx", src / "workx")
    (src / "workx" / "trusted" / "secret_thing.py").write_text("VALUE = 1\n")
    (src / "workx" / "domains" / "leaky.py").write_text("from workx.trusted import secret_thing\n")
    shutil.copy(REPO_ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    result = _lint_imports(tmp_path, src)
    assert result.returncode != 0
    assert "workx.domains.leaky" in result.stdout
