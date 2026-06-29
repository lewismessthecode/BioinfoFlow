from __future__ import annotations

import re

from app.services.run_helpers import generate_run_id


def test_generate_run_id_uses_128_bits_of_entropy():
    run_id = generate_run_id()

    assert re.fullmatch(r"run_[0-9a-f]{32}", run_id)
