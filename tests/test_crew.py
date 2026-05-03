from unittest import mock


def _fake_agent():
    return mock.MagicMock()


def _make_task_class():
    """Return a Task replacement that stores kwargs as attributes without pydantic validation."""
    def _factory(**kw):
        t = mock.MagicMock()
        for k, v in kw.items():
            setattr(t, k, v)
        return t
    m = mock.MagicMock(side_effect=_factory)
    return m


def test_chunk_task_description_contains_file_paths():
    files = [
        {"path": "src/app.ts", "description": "main entry"},
        {"path": "src/index.ts", "description": "index"},
    ]
    with mock.patch("backend.orchestrator.crew.Task", _make_task_class()):
        from backend.orchestrator.crew import build_generate_chunk_task
        task = build_generate_chunk_task(_fake_agent(), files, "Build a todo app")
    assert "src/app.ts" in task.description
    assert "src/index.ts" in task.description
    assert "Build a todo app" in task.description


def test_chunk_task_description_forbids_placeholders():
    files = [{"path": "src/app.ts", "description": "entry"}]
    with mock.patch("backend.orchestrator.crew.Task", _make_task_class()):
        from backend.orchestrator.crew import build_generate_chunk_task
        task = build_generate_chunk_task(_fake_agent(), files, "spec")
    assert "<path>" not in task.description
    assert "<content>" not in task.description


def test_chunk_task_expected_output_mentions_headers():
    files = [{"path": "src/app.ts", "description": "entry"}]
    with mock.patch("backend.orchestrator.crew.Task", _make_task_class()):
        from backend.orchestrator.crew import build_generate_chunk_task
        task = build_generate_chunk_task(_fake_agent(), files, "spec")
    assert "===" in task.expected_output
