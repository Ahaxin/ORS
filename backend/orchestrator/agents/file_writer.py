from crewai import Agent


def make_file_writer(llm) -> Agent:
    return Agent(
        role="Code File Writer",
        goal="Generate complete, working Next.js code files based on the architect's plan. Output each file with its path and full content.",
        backstory="You are an expert Next.js developer. You write production-quality TypeScript with no placeholders or TODOs.",
        llm=llm,
        verbose=True,
    )
