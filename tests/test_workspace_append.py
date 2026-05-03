import pytest
from pathlib import Path
from backend.workspace_manager import WorkspaceManager


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.workspace_manager.WORKSPACE_ROOT", tmp_path)
    return WorkspaceManager("test-project")


def test_append_text_creates_file(ws):
    ws.append_text("_ors/run_log.txt", "first line\n")
    content = (ws.root / "_ors/run_log.txt").read_text(encoding="utf-8")
    assert content == "first line\n"


def test_append_text_accumulates(ws):
    ws.append_text("_ors/run_log.txt", "first\n")
    ws.append_text("_ors/run_log.txt", "second\n")
    content = (ws.root / "_ors/run_log.txt").read_text(encoding="utf-8")
    assert content == "first\nsecond\n"


def test_append_text_does_not_overwrite(ws):
    ws.write_text("_ors/run_log.txt", "existing\n")
    ws.append_text("_ors/run_log.txt", "new\n")
    content = (ws.root / "_ors/run_log.txt").read_text(encoding="utf-8")
    assert content == "existing\nnew\n"
