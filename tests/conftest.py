"""Pytest hooks: skip ``@pytest.mark.slow`` unless ``--slow`` or ``RUN_SLOW=1``."""

from __future__ import annotations

import os

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--slow",
        action="store_true",
        default=False,
        help="Run model-heavy / long-running tests marked @pytest.mark.slow",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    run_slow = config.getoption("--slow") or os.environ.get("RUN_SLOW", "").strip() in {
        "1",
        "true",
        "yes",
    }
    if run_slow:
        return
    skip = pytest.mark.skip(reason="slow test; pass --slow or RUN_SLOW=1")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)
