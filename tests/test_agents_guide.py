"""Every ``python`` block in the packaged agent guide must run as written."""

import re
from importlib import resources

import pytest

GUIDE = resources.files("reaktiv").joinpath("AGENTS.md").read_text(encoding="utf-8")
BLOCKS = re.findall(r"```python\n(.*?)```", GUIDE, flags=re.DOTALL)


def test_guide_ships_with_the_package_and_has_examples():
    assert len(BLOCKS) >= 4


@pytest.mark.parametrize("index", range(len(BLOCKS)))
def test_guide_example_runs(index):
    exec(compile(BLOCKS[index], f"AGENTS.md[block {index}]", "exec"), {"__name__": "guide"})
