"""Smoke test: verify examen package is importable and has correct version."""


def test_import_examen() -> None:
    """Assert that `import examen` works without error."""
    import examen  # noqa: F401


def test_version() -> None:
    """Assert that examen.__version__ equals '0.1.0'."""
    import examen

    assert examen.__version__ == "0.1.0"
