from crewai import Agent


def make_clarifier(llm) -> Agent:
    return Agent(
        role="Requirements Clarifier",
        goal="Ask focused questions to fully understand what the user wants to build. Output a structured spec as JSON.",
        backstory="You are a senior product manager. Given a vague idea, you ask the minimum questions needed to produce a clear, unambiguous spec.",
        llm=llm,
        verbose=True,
    )
