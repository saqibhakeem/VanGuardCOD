"""Framework-less AsyncGroq agent runtime with parallel tool execution and HITL gating."""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import get_settings

ToolStatus = Literal["SUCCESS", "ERROR", "PAUSED_FOR_APPROVAL", "REJECTED"]

Handler = Callable[[BaseModel], Awaitable[Any]]
DynamicApprovalReason = Callable[[BaseModel], Awaitable[str | None]]
EventSink = Callable[[dict[str, Any]], Awaitable[None] | None]


class ToolCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: f"call_{uuid4().hex[:12]}")
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: int = 1
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float = 0.0
    status: ToolStatus
    tool_call_id: str | None = None
    approval_id: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class AgentStepTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: int
    model: str
    llm_ms: float
    tool_ms: float
    assistant_text: str | None = None
    finish_reason: str | None = None
    tool_traces: list[ToolTrace] = Field(default_factory=list)


class AgentTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    paused: bool = False
    approval_ids: list[str] = Field(default_factory=list)
    traces: list[AgentStepTrace] = Field(default_factory=list)
    tool_traces: list[ToolTrace] = Field(default_factory=list)
    llm_ms: float = 0.0
    tool_ms: float = 0.0
    latency_ms: float = 0.0
    model: str = ""


class ApprovalDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str | None = None
    order_id: str | None = None
    call_session_id: str | None = None
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str


class ApprovalGate(Protocol):
    async def __call__(self, draft: ApprovalDraft) -> str: ...


class ToolExecutionError(RuntimeError):
    """Raised by tool handlers when a business rule blocks execution."""


@dataclass(slots=True)
class RegisteredTool:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Handler
    requires_approval: bool = False
    approval_reason: str | None = None
    dynamic_approval_reason: DynamicApprovalReason | None = None

    def function_schema(self) -> dict[str, Any]:
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema,
            },
        }


def _normalize_arguments(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, str):
        if not raw.strip():
            return {}
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("tool arguments must decode to a JSON object")
        return parsed
    if isinstance(raw, dict):
        return raw
    raise ValueError("tool arguments must be a JSON object")


class ToolRegistry:
    """Registry of strict Pydantic tools with parallel and approval-aware execution."""

    def __init__(self, *, tool_timeout_s: float = 15.0) -> None:
        self._tools: dict[str, RegisteredTool] = {}
        self.tool_timeout_s = tool_timeout_s

    def register(self, tool: RegisteredTool) -> RegisteredTool:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool
        return tool

    def add(
        self,
        *,
        name: str,
        description: str,
        args_model: type[BaseModel],
        handler: Handler,
        requires_approval: bool = False,
        approval_reason: str | None = None,
        dynamic_approval_reason: DynamicApprovalReason | None = None,
    ) -> RegisteredTool:
        return self.register(
            RegisteredTool(
                name=name,
                description=description,
                args_model=args_model,
                handler=handler,
                requires_approval=requires_approval,
                approval_reason=approval_reason,
                dynamic_approval_reason=dynamic_approval_reason,
            )
        )

    def tool(
        self,
        *,
        name: str,
        description: str,
        args_model: type[BaseModel],
        requires_approval: bool = False,
        approval_reason: str | None = None,
        dynamic_approval_reason: DynamicApprovalReason | None = None,
    ) -> Callable[[Handler], Handler]:
        def decorator(handler: Handler) -> Handler:
            self.add(
                name=name,
                description=description,
                args_model=args_model,
                handler=handler,
                requires_approval=requires_approval,
                approval_reason=approval_reason,
                dynamic_approval_reason=dynamic_approval_reason,
            )
            return handler

        return decorator

    def get(self, name: str) -> RegisteredTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"unknown tool: {name}") from exc

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def tool_schemas(self) -> list[dict[str, Any]]:
        return [tool.function_schema() for tool in self._tools.values()]

    async def execute(
        self,
        call: ToolCallRequest,
        *,
        step: int = 1,
        gate: ApprovalGate | None = None,
        bypass_approval: bool = False,
    ) -> ToolTrace:
        started = time.perf_counter()
        trace = ToolTrace(
            step=step,
            tool_name=call.name,
            arguments=dict(call.arguments),
            status="ERROR",
            tool_call_id=call.id,
        )

        try:
            tool = self.get(call.name)
        except KeyError as exc:
            trace.duration_ms = round((time.perf_counter() - started) * 1000, 2)
            trace.error = str(exc)
            return trace

        try:
            parsed = _normalize_arguments(call.arguments)
            validated = tool.args_model.model_validate(parsed)
        except ValidationError as exc:
            trace.arguments = parsed if "parsed" in locals() else dict(call.arguments)
            trace.duration_ms = round((time.perf_counter() - started) * 1000, 2)
            trace.error = f"validation_error: {json.dumps(exc.errors(include_url=False))}"
            return trace
        except (json.JSONDecodeError, ValueError) as exc:
            trace.duration_ms = round((time.perf_counter() - started) * 1000, 2)
            trace.error = f"invalid_arguments: {exc}"
            return trace

        trace.arguments = validated.model_dump()

        approval_reason: str | None = None
        if tool.requires_approval:
            approval_reason = tool.approval_reason or f"{tool.name} requires operator approval"
        elif tool.dynamic_approval_reason is not None:
            try:
                approval_reason = await tool.dynamic_approval_reason(validated)
            except Exception as exc:  # noqa: BLE001
                trace.duration_ms = round((time.perf_counter() - started) * 1000, 2)
                trace.error = f"approval_check_failed: {type(exc).__name__}: {exc}"
                return trace

        if approval_reason is not None and not bypass_approval:
            if gate is None:
                trace.duration_ms = round((time.perf_counter() - started) * 1000, 2)
                trace.error = "approval_gate_unavailable"
                return trace
            approval_id = await gate(
                ApprovalDraft(
                    tool_name=tool.name,
                    arguments=trace.arguments,
                    reason=approval_reason,
                )
            )
            trace.status = "PAUSED_FOR_APPROVAL"
            trace.approval_id = approval_id
            trace.duration_ms = round((time.perf_counter() - started) * 1000, 2)
            return trace

        try:
            raw_result = await asyncio.wait_for(
                tool.handler(validated), timeout=self.tool_timeout_s
            )
            trace.result = self._normalize_result(raw_result)
            trace.status = "SUCCESS"
        except asyncio.TimeoutError:
            trace.status = "ERROR"
            trace.error = f"tool_timeout: exceeded {self.tool_timeout_s}s"
        except ToolExecutionError as exc:
            trace.status = "ERROR"
            trace.error = str(exc)
        except Exception as exc:  # noqa: BLE001
            trace.status = "ERROR"
            trace.error = f"{type(exc).__name__}: {exc}"

        trace.duration_ms = round((time.perf_counter() - started) * 1000, 2)
        return trace

    async def execute_parallel(
        self,
        calls: Sequence[ToolCallRequest],
        *,
        step: int = 1,
        gate: ApprovalGate | None = None,
        bypass_approval: bool = False,
    ) -> list[ToolTrace]:
        if not calls:
            return []
        return list(
            await asyncio.gather(
                *(
                    self.execute(
                        call, step=step, gate=gate, bypass_approval=bypass_approval
                    )
                    for call in calls
                )
            )
        )

    @staticmethod
    def _normalize_result(raw_result: Any) -> dict[str, Any]:
        if raw_result is None:
            return {}
        if isinstance(raw_result, BaseModel):
            return raw_result.model_dump()
        if isinstance(raw_result, dict):
            return raw_result
        return {"value": raw_result}


class InMemoryApprovalGate:
    """Test and demo gate that records drafts without touching the database."""

    def __init__(self) -> None:
        self.drafts: list[ApprovalDraft] = []
        self.approval_ids: list[str] = []

    async def __call__(self, draft: ApprovalDraft) -> str:
        approval_id = str(uuid4())
        self.drafts.append(draft)
        self.approval_ids.append(approval_id)
        return approval_id


class _MockFunction:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


class _MockToolCall:
    def __init__(self, call_id: str, name: str, arguments: dict[str, Any]) -> None:
        self.id = call_id
        self.type = "function"
        self.function = _MockFunction(name, json.dumps(arguments))


class _MockMessage:
    def __init__(
        self, content: str | None, tool_calls: list[_MockToolCall] | None = None
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls or None


class _MockChoice:
    def __init__(
        self, content: str | None, tool_calls: list[_MockToolCall] | None, finish_reason: str
    ) -> None:
        self.message = _MockMessage(content, tool_calls)
        self.finish_reason = finish_reason


class _MockCompletion:
    def __init__(
        self, content: str | None, tool_calls: list[_MockToolCall] | None, finish_reason: str
    ) -> None:
        self.choices = [_MockChoice(content, tool_calls, finish_reason)]
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def _build_mock_completion(
    content: str | None = None,
    tool_calls: Sequence[dict[str, Any] | tuple[str, dict[str, Any]]] | None = None,
) -> _MockCompletion:
    built: list[_MockToolCall] = []
    for index, item in enumerate(tool_calls or []):
        if isinstance(item, tuple):
            name, arguments = item
        else:
            name = str(item.get("name"))
            arguments = dict(item.get("arguments") or {})
        built.append(_MockToolCall(f"call_mock_{index + 1}", name, arguments))
    return _MockCompletion(
        content,
        built or None,
        "tool_calls" if built else "stop",
    )


def text_completion(content: str) -> _MockCompletion:
    return _build_mock_completion(content=content)


def tool_call_completion(
    calls: Sequence[dict[str, Any] | tuple[str, dict[str, Any]]],
) -> _MockCompletion:
    return _build_mock_completion(tool_calls=calls)


class _MockCompletions:
    def __init__(self, client: "MockGroqClient") -> None:
        self._client = client

    async def create(self, **kwargs: Any) -> _MockCompletion:
        return await self._client._next_completion(kwargs)  # noqa: SLF001


class _MockChat:
    def __init__(self, client: "MockGroqClient") -> None:
        self.completions = _MockCompletions(client)


class MockGroqClient:
    """Deterministic AsyncGroq stand-in used when no API key is configured."""

    def __init__(
        self,
        *,
        context: dict[str, Any] | None = None,
        script: Sequence[Any] | None = None,
    ) -> None:
        self.context = context or {}
        self.script = list(script or [])
        self.calls: list[dict[str, Any]] = []
        self.chat = _MockChat(self)

    async def _next_completion(self, kwargs: dict[str, Any]) -> _MockCompletion:
        self.calls.append(kwargs)
        if self.script:
            item = self.script.pop(0)
            if isinstance(item, str):
                return text_completion(item)
            if isinstance(item, _MockCompletion):
                return item
            return _build_mock_completion(
                content=item.get("content"),
                tool_calls=item.get("tool_calls"),
            )
        return self._plan(kwargs)

    def _plan(self, kwargs: dict[str, Any]) -> _MockCompletion:
        messages = kwargs.get("messages") or []
        tools = kwargs.get("tools") or []
        available = {
            str(tool.get("function", {}).get("name"))
            for tool in tools
            if isinstance(tool, dict)
        }
        last = messages[-1] if messages else {}
        if last.get("role") == "tool":
            return text_completion("Noted. Is there anything else I can help with?")

        utterance = str(last.get("content") or "").strip()
        lower = utterance.lower()
        order_id = str(self.context.get("order_id") or "")
        landmark = str(self.context.get("verified_landmark") or "Near the main market gate")
        window = str(self.context.get("delivery_window") or "Tomorrow 4 PM")
        cod_amount = float(self.context.get("cod_amount") or 0.0)
        address = str(self.context.get("raw_address") or "")

        def call(name: str, arguments: dict[str, Any]) -> tuple[str, dict[str, Any]]:
            return (name, arguments)

        if ("parallel" in lower or "both" in lower) and {
            "confirm_cod_order",
            "reschedule_delivery_window",
        }.issubset(available):
            return _build_mock_completion(
                tool_calls=[
                    call(
                        "confirm_cod_order",
                        {
                            "order_id": order_id,
                            "verified_landmark": landmark,
                            "delivery_window": window,
                        },
                    ),
                    call(
                        "reschedule_delivery_window",
                        {
                            "order_id": order_id,
                            "new_window": window,
                            "updated_landmark": landmark,
                        },
                    ),
                ]
            )

        if "cancel" in lower and "cancel_cod_order" in available:
            return _build_mock_completion(
                tool_calls=[
                    call(
                        "cancel_cod_order",
                        {"order_id": order_id, "cancellation_reason": utterance},
                    )
                ]
            )

        change_words = ("address", "city", "sector", "price", "discount", "change")
        if any(word in lower for word in change_words):
            if "request_price_or_city_modification" in available:
                return _build_mock_completion(
                    tool_calls=[
                        call(
                            "request_price_or_city_modification",
                            {
                                "order_id": order_id,
                                "new_address": address,
                                "requested_cod_amount": cod_amount,
                                "reason": utterance,
                            },
                        )
                    ]
                )
            if "request_address_reroute" in available:
                return _build_mock_completion(
                    tool_calls=[
                        call(
                            "request_address_reroute",
                            {
                                "order_id": order_id,
                                "proposed_address": address,
                                "caller_role": "customer",
                            },
                        )
                    ]
                )

        if (
            any(word in lower for word in ("rider", "failed", "locked", "unreachable", "attempt"))
            and "log_rider_delivery_attempt" in available
        ):
            return _build_mock_completion(
                tool_calls=[
                    call(
                        "log_rider_delivery_attempt",
                        {
                            "order_id": order_id,
                            "rider_issue": utterance,
                            "gps_note": "Rider reported from the delivery location",
                        },
                    )
                ]
            )

        if (
            any(word in lower for word in ("reschedule", "tomorrow", "evening", "window", "time"))
            and "reschedule_delivery_window" in available
        ):
            return _build_mock_completion(
                tool_calls=[
                    call(
                        "reschedule_delivery_window",
                        {
                            "order_id": order_id,
                            "new_window": window,
                            "updated_landmark": landmark,
                        },
                    )
                ]
            )

        if (
            any(word in lower for word in ("confirm", "yes", "deliver", "dispatch", "sure"))
            and "confirm_cod_order" in available
        ):
            return _build_mock_completion(
                tool_calls=[
                    call(
                        "confirm_cod_order",
                        {
                            "order_id": order_id,
                            "verified_landmark": landmark,
                            "delivery_window": window,
                        },
                    )
                ]
            )

        if (
            any(word in lower for word in ("status", "track", "lookup", "find", "order"))
            and "lookup_order_by_phone_or_ref" in available
        ):
            query = str(self.context.get("customer_phone") or self.context.get("external_order_id") or utterance)
            return _build_mock_completion(
                tool_calls=[call("lookup_order_by_phone_or_ref", {"query": query})]
            )

        if "confirm_cod_order" in available:
            return text_completion(
                f"Just to confirm, should we dispatch this order for PKR {cod_amount:.0f} cash on delivery?"
            )
        return text_completion("I can help with that. Could you share your order number or phone number?")


@dataclass(slots=True)
class AgentProfile:
    name: str
    system_prompt: str
    greeting: str


def _parse_completion(
    completion: Any,
) -> tuple[str | None, list[ToolCallRequest], str | None]:
    choice = completion.choices[0]
    message = choice.message
    content = getattr(message, "content", None)
    raw_calls = getattr(message, "tool_calls", None) or []
    requests: list[ToolCallRequest] = []
    for index, raw in enumerate(raw_calls):
        function = getattr(raw, "function", None)
        if function is None and isinstance(raw, dict):
            function = raw.get("function")
        if function is None:
            continue
        if isinstance(function, dict):
            name = function.get("name")
            raw_arguments = function.get("arguments")
        else:
            name = getattr(function, "name", None)
            raw_arguments = getattr(function, "arguments", "{}")
        if isinstance(raw_arguments, str):
            try:
                arguments = json.loads(raw_arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
        else:
            arguments = raw_arguments or {}
        call_id = getattr(raw, "id", None)
        if call_id is None and isinstance(raw, dict):
            call_id = raw.get("id")
        if not isinstance(arguments, dict):
            arguments = {}
        if name:
            requests.append(
                ToolCallRequest(
                    id=str(call_id or f"call_{index + 1}"),
                    name=str(name),
                    arguments=arguments,
                )
            )
    finish_reason = getattr(choice, "finish_reason", None)
    return content, requests, finish_reason


class AutonomousVoiceAgent:
    """Native asyncio agent loop over AsyncGroq chat completions."""

    def __init__(
        self,
        *,
        profile: AgentProfile,
        registry: ToolRegistry,
        context: dict[str, Any] | None = None,
        client: Any | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tool_rounds: int = 4,
        approval_gate: ApprovalGate | None = None,
        on_event: EventSink | None = None,
        history: Sequence[dict[str, Any]] | None = None,
        llm_timeout_s: float = 20.0,
    ) -> None:
        settings = get_settings()
        self.profile = profile
        self.registry = registry
        self.context = context or {}
        self.model = model or settings.llm_model
        self.temperature = settings.llm_temperature if temperature is None else temperature
        self.max_tool_rounds = max_tool_rounds
        self.approval_gate = approval_gate
        self.on_event = on_event
        self.llm_timeout_s = llm_timeout_s
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": profile.system_prompt}
        ]
        for entry in history or ():
            role = entry.get("role")
            content = entry.get("content")
            if role in {"user", "assistant"} and content:
                self.messages.append({"role": role, "content": content})
        self.paused = False
        self.pending_approval_ids: list[str] = []
        self._client = client
        self._step = 0

    def _get_client(self) -> Any:
        if self._client is None:
            settings = get_settings()
            if settings.mock_mode:
                self._client = MockGroqClient(context=self.context)
            else:
                from groq import AsyncGroq

                self._client = AsyncGroq(api_key=settings.groq_api_key)
        return self._client

    async def _emit(self, event: dict[str, Any]) -> None:
        if self.on_event is None:
            return
        outcome = self.on_event(event)
        if inspect.isawaitable(outcome):
            await outcome

    async def start(self) -> AgentTurn:
        text = self.profile.greeting
        self.messages.append({"role": "assistant", "content": text})
        await self._emit({"event": "transcript_update", "role": "assistant", "text": text})
        return AgentTurn(text=text, model=self.model)

    async def run_turn(self, user_text: str) -> AgentTurn:
        if self.paused:
            raise RuntimeError("agent is paused awaiting operator approval")
        self.messages.append({"role": "user", "content": user_text})
        await self._emit({"event": "transcript_update", "role": "user", "text": user_text})
        return await self._drive()

    async def resume(
        self,
        *,
        tool_name: str,
        approved: bool,
        result: dict[str, Any] | None = None,
        operator_note: str | None = None,
    ) -> AgentTurn:
        self.paused = False
        self.pending_approval_ids = []
        decision = "approved" if approved else "rejected"
        note = operator_note or f"Operator {decision} the {tool_name} request."
        self.messages.append(
            {
                "role": "user",
                "content": f"{note} Tool result: {json.dumps(result or {})}",
            }
        )
        return await self._drive()

    async def _chat(self) -> tuple[str | None, list[ToolCallRequest], str | None]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": self.messages,
            "temperature": self.temperature,
            "max_tokens": 320,
        }
        schemas = self.registry.tool_schemas()
        if schemas:
            kwargs["tools"] = schemas
            kwargs["tool_choice"] = "auto"
        completion = await asyncio.wait_for(
            self._get_client().chat.completions.create(**kwargs),
            timeout=self.llm_timeout_s,
        )
        return _parse_completion(completion)

    async def _drive(self) -> AgentTurn:
        turn_started = time.perf_counter()
        traces: list[AgentStepTrace] = []
        all_tool_traces: list[ToolTrace] = []
        total_llm_ms = 0.0
        total_tool_ms = 0.0

        for _ in range(self.max_tool_rounds):
            self._step += 1
            step = self._step
            llm_started = time.perf_counter()
            content, calls, finish_reason = await self._chat()
            llm_ms = round((time.perf_counter() - llm_started) * 1000, 2)
            total_llm_ms += llm_ms

            if not calls:
                text = (content or "").strip() or "Understood."
                self.messages.append({"role": "assistant", "content": text})
                traces.append(
                    AgentStepTrace(
                        step=step,
                        model=self.model,
                        llm_ms=llm_ms,
                        tool_ms=0.0,
                        assistant_text=text,
                        finish_reason=finish_reason,
                    )
                )
                await self._emit(
                    {"event": "transcript_update", "role": "assistant", "text": text}
                )
                return AgentTurn(
                    text=text,
                    paused=False,
                    traces=traces,
                    tool_traces=all_tool_traces,
                    llm_ms=round(total_llm_ms, 2),
                    tool_ms=round(total_tool_ms, 2),
                    latency_ms=round((time.perf_counter() - turn_started) * 1000, 2),
                    model=self.model,
                )

            self.messages.append(
                {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments),
                            },
                        }
                        for call in calls
                    ],
                }
            )

            tool_started = time.perf_counter()
            tool_traces = await self.registry.execute_parallel(
                calls, step=step, gate=self.approval_gate
            )
            tool_ms = round((time.perf_counter() - tool_started) * 1000, 2)
            total_tool_ms += tool_ms
            all_tool_traces.extend(tool_traces)

            for trace in tool_traces:
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": trace.tool_call_id or trace.tool_name,
                        "content": json.dumps(
                            {
                                "status": trace.status,
                                "result": trace.result,
                                "error": trace.error,
                            }
                        ),
                    }
                )
                await self._emit(
                    {
                        "event": "tool_trace",
                        **trace.model_dump(),
                    }
                )

            traces.append(
                AgentStepTrace(
                    step=step,
                    model=self.model,
                    llm_ms=llm_ms,
                    tool_ms=tool_ms,
                    assistant_text=content,
                    finish_reason=finish_reason,
                    tool_traces=tool_traces,
                )
            )

            paused = [trace for trace in tool_traces if trace.status == "PAUSED_FOR_APPROVAL"]
            if paused:
                hold_text = (
                    "Let me confirm that with our operations team. Please hold for a moment."
                )
                self.paused = True
                self.pending_approval_ids = [
                    trace.approval_id for trace in paused if trace.approval_id
                ]
                self.messages.append({"role": "assistant", "content": hold_text})
                await self._emit(
                    {"event": "transcript_update", "role": "assistant", "text": hold_text}
                )
                return AgentTurn(
                    text=hold_text,
                    paused=True,
                    approval_ids=self.pending_approval_ids,
                    traces=traces,
                    tool_traces=all_tool_traces,
                    llm_ms=round(total_llm_ms, 2),
                    tool_ms=round(total_tool_ms, 2),
                    latency_ms=round((time.perf_counter() - turn_started) * 1000, 2),
                    model=self.model,
                )

        fallback = "I have recorded that request. Our operations team will follow up shortly."
        self.messages.append({"role": "assistant", "content": fallback})
        return AgentTurn(
            text=fallback,
            paused=False,
            traces=traces,
            tool_traces=all_tool_traces,
            llm_ms=round(total_llm_ms, 2),
            tool_ms=round(total_tool_ms, 2),
            latency_ms=round((time.perf_counter() - turn_started) * 1000, 2),
            model=self.model,
        )
