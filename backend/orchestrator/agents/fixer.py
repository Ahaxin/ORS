from crewai import Agent


def make_fixer(llm) -> Agent:
    return Agent(
        role="Code Fixer",
        goal="Given a list of review issues, fix only the specific files and lines mentioned. Output corrected file content.",
        backstory="You apply targeted fixes without rewriting unrelated code. Change the minimum needed to resolve each issue.",
        llm=llm,
        verbose=True,
    )
