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
        description=f"Generate all files in this plan:\n{plan}\n\nSpec: {spec}\n\nOutput: === FILE: <path> ===\n<content>",
        expected_output="All files with === FILE: <path> === separators and full content.",
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
        expected_output="Corrected files in === FILE: <path> === format.",
        agent=agent,
    )
