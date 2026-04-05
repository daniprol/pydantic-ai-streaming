from __future__ import annotations

import pytest
from pydantic_ai.exceptions import UserError

from pydantic_ai_absurd import AbsurdAgent


def test_duplicate_task_registration_is_rejected(fake_absurd_app, base_agent) -> None:
    AbsurdAgent(fake_absurd_app, base_agent, name="support-agent-absurd")

    with pytest.raises(UserError, match="already registered"):
        AbsurdAgent(fake_absurd_app, base_agent, name="support-agent-absurd")


def test_name_is_immutable(absurd_agent) -> None:
    with pytest.raises(UserError, match="cannot be changed"):
        absurd_agent.name = "renamed-agent"


def test_on_complete_property_exposes_callback(fake_absurd_app, base_agent) -> None:
    async def on_complete(ctx) -> None:
        return None

    absurd_agent = AbsurdAgent(
        fake_absurd_app,
        base_agent,
        name="support-agent-absurd",
        on_complete=on_complete,
    )

    assert absurd_agent.on_complete is on_complete
