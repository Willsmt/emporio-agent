from emporio.agent.agent import Agent
from emporio.agent.prompts import build_system_prompt
from emporio.agent.providers import create_provider
from emporio.agent.tool_registry import build_tools
from emporio.config import DB_PATH
from emporio.settings import Settings
from emporio.tools.db import connect_readonly


def build_agent(settings: Settings) -> Agent:
    conn = connect_readonly(DB_PATH)
    tools = build_tools(conn, today=lambda: settings.now().date())
    return Agent(
        provider=create_provider(settings),
        tools=tools,
        system_prompt=lambda: build_system_prompt(settings.now()),
    )
