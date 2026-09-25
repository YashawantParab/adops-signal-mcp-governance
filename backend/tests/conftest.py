"""Shared test fixtures. Keeps the whole suite hermetic against whatever is in
the developer's ambient environment (most importantly backend/.env, which is
gitignored and holds a real OPENAI_API_KEY for local manual runs) - tests must
never non-deterministically pass or fail depending on whether a real provider
key happens to be configured on the machine running them.
"""
from __future__ import annotations

import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def _hermetic_provider_env(monkeypatch):
    """Force every test to see no LLM/Jev provider key by default, regardless
    of backend/.env or the real process environment. Settings() reads env
    vars ahead of the .env file, so setting them to "" here overrides
    whatever is in .env; get_settings() is @lru_cache'd, so its cache must be
    cleared both before (in case an earlier test already populated it from
    the real environment before this fixture ran) and after (so the next
    test - including one outside this fixture's reach - never sees a Settings
    object built from a mutated env)."""
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("TYPESAFE_API_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
