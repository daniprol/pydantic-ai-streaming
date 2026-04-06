from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pydantic_ai import Agent, CallDeferred, DeferredToolRequests, RunContext
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


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding='utf-8').strip()


def _prompt_contains(ctx: RunContext[AgentDependencies], marker: str) -> bool:
    prompt = ctx.prompt
    if isinstance(prompt, str):
        return marker in prompt
    return False


def _prepare_hitl_tool_for_tests(marker: str):
    async def prepare(ctx: RunContext[AgentDependencies], tool_def):
        if not isinstance(ctx.model, TestModel):
            return tool_def
        if _prompt_contains(ctx, marker):
            return tool_def
        return None

    return prepare


async def _prepare_standard_tool_for_tests(ctx: RunContext[AgentDependencies], tool_def):
    if not isinstance(ctx.model, TestModel):
        return tool_def
    if any(
        _prompt_contains(ctx, marker)
        for marker in ('[hitl-approval]', '[hitl-decision]', '[hitl-form]')
    ):
        return None
    return tool_def


def build_model(settings: Settings) -> OpenAIChatModel | TestModel:
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
        model_settings={'thinking': settings.thinking_level},
    )


def build_support_agent(
    settings: Settings,
    support_client: FakeSupportClient | None = None,
) -> Agent[AgentDependencies, str | DeferredToolRequests]:
    support_client = support_client or FakeSupportClient()
    helper_agent = build_research_agent(settings)

    agent = Agent(
        build_model(settings),
        instructions=_load_prompt('support_system_prompt.txt'),
        deps_type=AgentDependencies,
        output_type=[str, DeferredToolRequests],
        name='support-assistant',
        model_settings={'thinking': settings.thinking_level},
    )

    @agent.tool(prepare=_prepare_standard_tool_for_tests)
    async def lookup_order_status(
        ctx: RunContext[AgentDependencies], order_id: str
    ) -> dict[str, str]:
        return await support_client.lookup_order_status(order_id)

    @agent.tool(prepare=_prepare_standard_tool_for_tests)
    async def check_service_health(
        ctx: RunContext[AgentDependencies], service_name: str
    ) -> dict[str, str]:
        return await support_client.check_platform_health(service_name)

    @agent.tool(prepare=_prepare_standard_tool_for_tests)
    async def search_help_center(
        ctx: RunContext[AgentDependencies], question: str
    ) -> list[dict[str, str]]:
        return await support_client.search_help_articles(question)

    @agent.tool(prepare=_prepare_standard_tool_for_tests)
    async def ask_policy_researcher(_: RunContext[AgentDependencies], question: str) -> str:
        result = await helper_agent.run(question)
        return result.output

    @agent.tool(requires_approval=True, prepare=_prepare_hitl_tool_for_tests('[hitl-approval]'))
    async def request_human_approval(
        ctx: RunContext[AgentDependencies],
        summary: str,
    ) -> str:
        return f'Approved action: {summary}'

    @agent.tool(prepare=_prepare_hitl_tool_for_tests('[hitl-decision]'))
    async def request_human_decision(
        ctx: RunContext[AgentDependencies],
        title: str,
        description: str,
    ) -> dict[str, str]:
        raise CallDeferred(
            metadata={
                'title': title,
                'description': description,
                'acceptLabel': 'Accept',
                'rejectLabel': 'Reject',
            }
        )

    @agent.tool(prepare=_prepare_hitl_tool_for_tests('[hitl-form]'))
    async def collect_human_form(
        ctx: RunContext[AgentDependencies],
        title: str,
        description: str,
    ) -> dict[str, object]:
        raise CallDeferred(
            metadata={
                'title': title,
                'description': description,
                'submitLabel': 'Send form',
                'schema': {
                    'fields': [
                        {
                            'name': 'email',
                            'label': 'Email',
                            'kind': 'text',
                            'required': True,
                            'placeholder': 'name@example.com',
                        },
                        {
                            'name': 'notes',
                            'label': 'Notes',
                            'kind': 'textarea',
                            'required': False,
                            'placeholder': 'Add any extra context',
                        },
                    ]
                },
            }
        )

    return agent
