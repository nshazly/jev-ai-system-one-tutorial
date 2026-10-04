import pytest

CONFIG_VARS = ("API_TOKEN", "DEFAULT_MODEL", "DEFAULT_BASE_URL", "DEFAULT_ENDPOINT")


@pytest.fixture(autouse=True)
def isolated_config_env(monkeypatch):
    """Keep shell or direnv settings (e.g. a DefAPI token) out of every test."""
    for name in CONFIG_VARS:
        monkeypatch.delenv(name, raising=False)
