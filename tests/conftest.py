import os
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from nila.api.app import create_app
from nila.core.config import Settings
from nila.core.runtime import Services, build_services

TEST_TOKEN = "test-only-token-not-a-real-credential-12345"


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("NILA_"):
            monkeypatch.delenv(name)


@pytest.fixture
def config(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        api_token=SecretStr(TEST_TOKEN),
        llm_provider="demo",
    )


@pytest.fixture
async def runtime(config: Settings) -> AsyncIterator[Services]:
    services = build_services(config)
    try:
        yield services
    finally:
        await services.close()


@pytest.fixture
def client(config: Settings) -> Iterator[TestClient]:
    with TestClient(
        create_app(config),
        base_url="http://127.0.0.1",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    ) as value:
        yield value
