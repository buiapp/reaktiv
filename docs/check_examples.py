"""Execute every interactive documentation example."""

from __future__ import annotations

import ast
import asyncio
import contextlib
import inspect
import io
from pathlib import Path

DOCS_ROOT = Path(__file__).parent


def iter_pyodide_blocks():
    for path in sorted(DOCS_ROOT.rglob("*.md")):
        lines = path.read_text().splitlines()
        index = 0

        while index < len(lines):
            if lines[index].startswith("```pyodide"):
                start_line = index + 2
                index += 1
                body: list[str] = []

                while index < len(lines) and lines[index] != "```":
                    body.append(lines[index])
                    index += 1

                yield path, start_line, "\n".join(body)

            index += 1


async def execute_example(path: Path, line: int, source: str) -> None:
    namespace = {"__name__": "__docs_example__"}
    code = compile(
        source,
        f"{path}:{line}",
        "exec",
        flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT,
    )

    with (
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        result = eval(code, namespace)
        if inspect.isawaitable(result):
            await asyncio.wait_for(result, timeout=5)


async def main() -> None:
    examples = list(iter_pyodide_blocks())

    for path, line, source in examples:
        try:
            await execute_example(path, line, source)
        except BaseException as error:
            location = path.relative_to(DOCS_ROOT.parent)
            raise RuntimeError(f"{location}:{line}: {error}") from error

    print(f"Executed {len(examples)} interactive documentation examples.")


if __name__ == "__main__":
    asyncio.run(main())
