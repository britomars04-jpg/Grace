# Agent behavior is covered by the simulations in scenarios.yaml, which run full
# conversations against the agent on LiveKit Cloud (see README.md). The eval
# below is kept as an example of the in-process testing framework
# (https://docs.livekit.io/agents/start/testing/) for turn-level checks that
# don't need a live session. Uncomment it and run `uv run pytest` to use it.
#
# import textwrap
#
# import pytest
# from livekit.agents import AgentSession, inference, llm
#
# from agent import Assistant
#
#
# def _judge_llm() -> llm.LLM:
#     return inference.LLM(model="openai/gpt-4.1-mini")
#
#
# @pytest.mark.asyncio
# async def test_offers_assistance() -> None:
#     """Evaluation of the agent's friendly nature."""
#     async with (
#         _judge_llm() as judge_llm,
#         AgentSession() as session,
#     ):
#         await session.start(Assistant())
#
#         # Run an agent turn following the user's greeting
#         result = await session.run(user_input="Hello")
#
#         # Evaluate the agent's response for friendliness
#         await (
#             result.expect.next_event()
#             .is_message(role="assistant")
#             .judge(
#                 judge_llm,
#                 intent=textwrap.dedent(
#                     """\
#                     Greets the user in a friendly manner.
#
#                     Optional context that may or may not be included:
#                     - Offer of assistance with any request the user may have
#                     - Other small talk or chit chat is acceptable, so long as it is friendly and not too intrusive
#                     """
#                 ),
#             )
#         )
#
#         # Ensures there are no function calls or other unexpected events
#         result.expect.no_more_events()

from __future__ import annotations

import pytest
from livekit.agents import llm
from livekit.plugins import google

import agent


@pytest.fixture(autouse=True)
def _google_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """The realtime model raises at construction without a key; no request is made."""
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")


def test_realtime_model_retries_the_initial_connection() -> None:
    """A failed first handshake must not end the call.

    The Google realtime plugin only retries a connection once a session has been
    established, so the initial handshake needs its own retry. The fallback
    adapter supplies it by swapping to another model instance, and each instance
    opens a fresh connection.
    """
    wrapper = agent.build_realtime_llm()

    assert isinstance(wrapper, llm.RealtimeModelFallbackAdapter)
    assert agent.REALTIME_MAX_ATTEMPTS >= 2
    # private, but this is the list of models the adapter fails over between
    assert len(wrapper._models) == agent.REALTIME_MAX_ATTEMPTS
    assert all(
        isinstance(m, google.beta.realtime.RealtimeModel) for m in wrapper._models
    )


def test_realtime_model_allows_a_slow_handshake() -> None:
    """The handshake timeout must leave room for the client's fallback addresses."""
    assert agent.REALTIME_CONNECT_TIMEOUT_SECONDS >= 10
