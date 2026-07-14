from __future__ import annotations

import subprocess
import sys


def test_model_runtime_and_llm_packages_import_in_either_order() -> None:
    import_orders = (
        "import app.services.model_runtime; import app.services.llm",
        "import app.services.llm; import app.services.model_runtime",
    )

    for statement in import_orders:
        result = subprocess.run(
            [sys.executable, "-c", statement],
            capture_output=True,
            check=False,
            text=True,
        )

        assert result.returncode == 0, result.stderr
