"""Smoke tests — verify imports and basic structure."""


def test_imports():
    """Verify core dependencies are importable."""
    import pandas
    import numpy
    import yaml
    assert True


def test_config_example_exists():
    """Verify config.yaml.example is present."""
    from pathlib import Path
    assert (Path(__file__).parent.parent / "config.yaml.example").exists()


def test_env_example_exists():
    """Verify .env.example is present."""
    from pathlib import Path
    assert (Path(__file__).parent.parent / ".env.example").exists()
