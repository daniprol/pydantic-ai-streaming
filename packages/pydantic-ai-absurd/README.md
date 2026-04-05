## pydantic-ai-absurd

Lightweight Absurd durable execution integration for PydanticAI.

```python
from absurd_sdk import AsyncAbsurd
from pydantic_ai import Agent
from pydantic_ai_absurd import AbsurdAgent

app = AsyncAbsurd('postgresql://postgres:postgres@localhost:5432/app', queue_name='agents')
base_agent = Agent('test', name='support-agent', output_type=str)

durable_agent = AbsurdAgent(
    app,
    base_agent,
    name='support-agent-absurd',
    tool_step_mode='auto',
)

result = await durable_agent.run('Hello')
print(result.output)
```

For durable streaming, set an `event_stream_handler` at agent creation time and call `agent.run(...)`.
Direct `run_stream()`, `run_stream_events()`, and `iter()` are intentionally unsupported.
