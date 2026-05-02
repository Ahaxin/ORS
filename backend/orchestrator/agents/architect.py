from crewai import Agent


def make_architect(llm) -> Agent:
    return Agent(
        role="Software Architect",
        goal="Given a refined spec, decide the tech stack and database, break the work into a file list, and output a JSON plan.",
        backstory="You are a Next.js full-stack architect. You produce precise, minimal task plans and choose the right database for each project.",
        llm=llm,
        verbose=True,
    )
