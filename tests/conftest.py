import pytest


@pytest.fixture(autouse=True)
def isolate_ai_secrets(monkeypatch):
    for name in ('AI_PROVIDER', 'DEEPSEEK_API_KEY', 'DEEPSEEK_MODEL', 'OPENAI_API_KEY', 'OPENAI_MODEL'):
        monkeypatch.delenv(name, raising=False)
