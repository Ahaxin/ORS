import json
from pathlib import Path

WORKSPACE_ROOT = Path("workspace")


class WorkspaceManager:
    def __init__(self, project_slug: str):
        self.root = WORKSPACE_ROOT / project_slug
        self.root.mkdir(parents=True, exist_ok=True)

    def write_file(self, relative_path: str, content: str):
        target = self.root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def write_json(self, relative_path: str, data: dict):
        self.write_file(relative_path, json.dumps(data, indent=2))

    def write_text(self, relative_path: str, content: str):
        self.write_file(relative_path, content)

    def append_text(self, relative_path: str, content: str):
        target = self.root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as f:
            f.write(content)

    def read_file(self, relative_path: str) -> str:
        return (self.root / relative_path).read_text(encoding="utf-8")

    def list_files(self) -> list[str]:
        return [
            str(p.relative_to(self.root)).replace("\\", "/")
            for p in self.root.rglob("*")
            if p.is_file()
        ]

    def file_tree(self) -> str:
        return "\n".join(sorted(self.list_files()))
