# Guide for Coding Agents

This page is written for AI coding agents that write code using reaktiv. The
same guide ships inside the package as `reaktiv/AGENTS.md`, so it always
matches the installed version. To use it in your project, add a line like this
to your own `AGENTS.md` (or `CLAUDE.md`):

```text
When writing code with reaktiv, follow the guide in the installed package:
python -c "import reaktiv, pathlib; print(pathlib.Path(reaktiv.__file__).with_name('AGENTS.md'))"
```

An index for agents is also available at [`/llms.txt`](llms.txt).

---

--8<-- "src/reaktiv/AGENTS.md"
