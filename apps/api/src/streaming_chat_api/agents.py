from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.providers.azure import AzureProvider
from pydantic_ai.providers.openai import OpenAIProvider

from streaming_chat_api.settings import Settings
from streaming_chat_api.support_client import FakeSupportClient


PROMPTS_DIR = Path(__file__).resolve().parent / 'prompts'


@dataclass(slots=True)
class AgentDependencies:
    conversation_id: str
    support_client: FakeSupportClient


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding='utf-8').strip()


def build_model(settings: Settings):
    if settings.use_test_model:
        return TestModel()

    provider = AzureProvider(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.openai_api_version,
    )
    return OpenAIChatModel(
        settings.azure_openai_model,
        provider=cast(OpenAIProvider, provider),
    )


def build_research_agent(settings: Settings) -> Agent[None, str]:
    return Agent(
        build_model(settings),
        instructions=_load_prompt('research_system_prompt.txt'),
        output_type=str,
        name='support-researcher',
    )


def build_support_agent(settings: Settings) -> Agent[AgentDependencies, str]:
    helper_agent = build_research_agent(settings)
    agent = Agent(
        build_model(settings),
        instructions=_load_prompt('support_system_prompt.txt'),
        deps_type=AgentDependencies,
        output_type=str,
        name='support-assistant',
    )

    @agent.tool
    async def lookup_order_status(
        ctx: RunContext[AgentDependencies], order_id: str
    ) -> dict[str, str]:
        return await ctx.deps.support_client.lookup_order_status(order_id)

    @agent.tool
    async def check_service_health(
        ctx: RunContext[AgentDependencies], service_name: str
    ) -> dict[str, str]:
        return await ctx.deps.support_client.check_platform_health(service_name)

    @agent.tool
    async def search_help_center(
        ctx: RunContext[AgentDependencies], question: str
    ) -> list[dict[str, str]]:
        return await ctx.deps.support_client.search_help_articles(question)

    @agent.tool
    async def ask_policy_researcher(_: RunContext[AgentDependencies], question: str) -> str:
        result = await helper_agent.run(question)
        return result.output

    return agent
