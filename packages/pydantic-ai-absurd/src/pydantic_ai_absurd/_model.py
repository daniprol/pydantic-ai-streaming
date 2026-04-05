from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from absurd_sdk import AsyncTaskContext

from pydantic_ai._run_context import RunContext
from pydantic_ai.agent import EventStreamHandler
from pydantic_ai.exceptions import UserError
from pydantic_ai.messages import ModelMessage, ModelResponse, ModelResponseStreamEvent
from pydantic_ai.models import Model, ModelRequestParameters, StreamedResponse
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RequestUsage

from ._serialization import dump_model_response, load_model_response


class CompletedStreamedResponse(StreamedResponse):
    def __init__(
        self, model_request_parameters: ModelRequestParameters, response: ModelResponse
    ):
        self.model_request_parameters = model_request_parameters
        self._response = response

    async def _get_event_iterator(self) -> AsyncIterator[ModelResponseStreamEvent]:
        return
        yield  # pragma: no cover

    def get(self) -> ModelResponse:
        return self._response

    def usage(self) -> RequestUsage:
        return self._response.usage

    @property
    def model_name(self) -> str:
        return self._response.model_name

    @property
    def provider_name(self) -> str | None:
        return self._response.provider_name

    @property
    def provider_url(self) -> str | None:
        return getattr(self._response, "provider_url", None)

    @property
    def timestamp(self) -> datetime:
        return self._response.timestamp


class AbsurdModel(WrapperModel):
    def __init__(
        self,
        wrapped: Model,
        *,
        step_name_prefix: str,
        get_context: Any,
        event_stream_handler: EventStreamHandler[Any] | None = None,
    ):
        super().__init__(wrapped)
        self._step_name_prefix = step_name_prefix
        self._get_context = get_context
        self._event_stream_handler = event_stream_handler

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        absurd_ctx = self._get_context()
        if absurd_ctx is None:
            return await super().request(
                messages, model_settings, model_request_parameters
            )

        async def run_request() -> dict[str, Any]:
            response = await super(AbsurdModel, self).request(
                messages, model_settings, model_request_parameters
            )
            return dump_model_response(response)

        response = await absurd_ctx.step(
            f"{self._step_name_prefix}__model.request", run_request
        )
        return load_model_response(response)

    @asynccontextmanager
    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        run_context: RunContext[Any] | None = None,
    ) -> AsyncIterator[StreamedResponse]:
        absurd_ctx = self._get_context()
        if absurd_ctx is None:
            async with super().request_stream(
                messages,
                model_settings,
                model_request_parameters,
                run_context,
            ) as streamed_response:
                yield streamed_response
                return

        if run_context is None:
            raise UserError(
                "An Absurd model cannot be used with `pydantic_ai.direct.model_request_stream()` as it requires a `run_context`. Set an `event_stream_handler` on the agent and use `agent.run()` instead."
            )
        if self._event_stream_handler is None:
            raise UserError(
                "Absurd durable streaming requires an `event_stream_handler` set at agent creation time. Use `agent.run()` instead of direct streaming APIs."
            )

        async def run_stream_request() -> dict[str, Any]:
            async with super(AbsurdModel, self).request_stream(
                messages,
                model_settings,
                model_request_parameters,
                run_context,
            ) as streamed_response:
                await self._event_stream_handler(run_context, streamed_response)
                async for _ in streamed_response:
                    pass
            return dump_model_response(streamed_response.get())

        response = await absurd_ctx.step(
            f"{self._step_name_prefix}__model.request_stream",
            run_stream_request,
        )
        yield CompletedStreamedResponse(
            model_request_parameters, load_model_response(response)
        )
