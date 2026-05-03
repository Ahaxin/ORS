from crewai import Task


def build_clarify_task(agent, spec: str) -> Task:
    return Task(
        description=f"The user wants to build: {spec}\n\nAsk clarifying questions and output a structured spec.",
        expected_output='JSON: {name, description, features: [], constraints: [], tech_notes: ""}',
        agent=agent,
    )


def build_architect_task(agent, refined_spec: str) -> Task:
    return Task(
        description=f"Given this spec:\n{refined_spec}\n\nDecide tech stack, choose a database, produce a file list.",
        expected_output='JSON: {database, orm, files: [{path, description}]}',
        agent=agent,
    )


def build_generate_task(agent, plan: str, spec: str) -> Task:
    return Task(
        description=(
            f"Generate all files in this plan:\n{plan}\n\nSpec: {spec}\n\n"
            "Output every file using this EXACT format — replace the path and content with real values:\n\n"
            "=== FILE: src/index.ts ===\n"
            "console.log('hello');\n\n"
            "=== FILE: src/app.ts ===\n"
            "export default {};\n\n"
            "Follow that pattern for every file. Do not use placeholder text like <path> or <content>."
        ),
        expected_output=(
            "All files separated by === FILE: <actual path> === headers, "
            "each followed immediately by the full file content. No placeholders."
        ),
        agent=agent,
    )


def build_generate_chunk_task(agent, files: list[dict], spec: str) -> Task:
    file_list = "\n".join(f"- {f['path']}: {f['description']}" for f in files)
    return Task(
        description=(
            f"Generate ONLY these files:\n{file_list}\n\nSpec: {spec}\n\n"
            "Output each file using this EXACT format:\n\n"
            "=== FILE: src/index.ts ===\n"
            "// content here\n\n"
            "=== FILE: src/app.ts ===\n"
            "// content here\n\n"
            "Do not use placeholder text. Replace every path and content with real values."
        ),
        expected_output="All assigned files with === FILE: <actual path> === headers and full content. No placeholders.",
        agent=agent,
    )


def build_review_task(agent, file_tree: str, files_content: str) -> Task:
    return Task(
        description=f"Review:\nFile tree:\n{file_tree}\n\nContent:\n{files_content}",
        expected_output="'PASS' or list of issues: {file, issue, suggestion}",
        agent=agent,
    )


def build_fix_task(agent, issues: str, files_content: str) -> Task:
    return Task(
        description=f"Fix these issues:\n{issues}\n\nFiles:\n{files_content}",
        expected_output="Corrected files using === FILE: <actual path> === headers with full content. No placeholders.",
        agent=agent,
    )
