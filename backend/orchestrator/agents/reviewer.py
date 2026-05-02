from crewai import Agent


def make_reviewer(llm) -> Agent:
    return Agent(
        role="Code Reviewer",
        goal="Review generated code files for correctness and completeness. List specific issues with file paths. Output 'PASS' if no issues.",
        backstory="You are a senior engineer who catches missing imports, type errors, and broken contracts. Thorough but not pedantic.",
        llm=llm,
        verbose=True,
    )
