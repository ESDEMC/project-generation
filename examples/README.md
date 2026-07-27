# Runnable examples

Each subdirectory is self-contained: its Python script is stored beside the generation definition and any local source data it uses.

Run examples from the repository root, which contains `pyproject.toml`:

```powershell
Set-Location D:\Python\project-generation
python .\examples\neutral_project\generate_project.py
```

The examples intentionally remain under the top-level `examples/` directory. The `docs/` directory contains documentation only.

See [`docs/examples.md`](../docs/examples.md) for the complete example catalog and expected outputs.
