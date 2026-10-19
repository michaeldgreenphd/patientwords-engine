"""Regenerate the test-only response models; never edit generated.py by hand."""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA = HERE.parent / "contracts" / "simulated_scenarios.v1.schema.json"


def generate(output: Path) -> None:
    """Use the separately locked development toolchain, without network access."""
    subprocess.run([
        sys.executable, "-m", "datamodel_code_generator", "--input", str(SCHEMA),
        "--input-file-type", "jsonschema", "--output-model-type", "pydantic_v2.BaseModel",
        "--target-python-version", "3.11", "--use-standard-collections", "--use-union-operator",
        "--disable-timestamp", "--class-name", "SimulatedScenarios", "--output", str(output),
    ], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = HERE / "generated.py"
    if args.check:
        with tempfile.TemporaryDirectory(prefix="pw-client-") as directory:
            output = Path(directory) / "generated.py"
            generate(output)
            if output.read_bytes() != target.read_bytes():
                raise SystemExit("generated client models differ: run scripts/boundary_client/generate.py")
        print("generated client models: byte-identical")
    else:
        generate(target)


if __name__ == "__main__":
    main()
