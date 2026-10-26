import pytest

from src.settings import Settings


def test_project_from_modal_state(monkeypatch):
    monkeypatch.delenv("context.projectId", raising=False)
    monkeypatch.setenv("modal.state.slyProjectId", "42")
    assert Settings.from_env() == Settings(project_id=42)


def test_missing_project_fails_early(monkeypatch):
    for key in ("modal.state.slyProjectId", "context.projectId", "PROJECT_ID"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError, match="No project"):
        Settings.from_env()
