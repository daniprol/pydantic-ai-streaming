import pytest


@pytest.mark.asyncio
async def test_support_agent_runs_with_fake_dependencies(support_agent, agent_deps_factory) -> None:
    deps = agent_deps_factory()

    result = await support_agent.run('Check order order-123', deps=deps)

    assert isinstance(result.output, str)
    assert result.output


@pytest.mark.llm
@pytest.mark.asyncio
async def test_support_agent_runs_with_real_llm(real_support_agent, agent_deps_factory) -> None:
    deps = agent_deps_factory(conversation_id='llm-conversation-1')

    result = await real_support_agent.run('Give a short answer confirming you can help with order status.', deps=deps)

    assert isinstance(result.output, str)
    assert result.output
