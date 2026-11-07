import asyncio
import logging

from ddgs import DDGS
from livekit.agents import RunContext, function_tool

# Search engines hand back ten-plus results by default; the agent only needs a
# few to answer, and every extra result is context the model re-reads each turn.
MAX_RESULTS = 5


def _search(query: str) -> str:
    """Run a DuckDuckGo text search. Blocking; see the tool below."""
    with DDGS() as ddgs:
        results = ddgs.text(query, max_results=MAX_RESULTS)

    if not results:
        return f"No results found for {query!r}."

    return "\n".join(
        f"{result.get('title') or ''} ({result.get('href') or ''}): "
        f"{result.get('body') or ''}".strip()
        for result in results
    )


@function_tool()
async def search_web(context: RunContext, query: str):
    """
    Use this tool to search the web for information related to the given query.
    """
    try:
        # The search client is synchronous, so run it in a worker thread. Doing
        # it inline would block the event loop for the several seconds a search
        # takes, which stalls audio playback and turn detection for the whole
        # call rather than just delaying this one reply.
        results = await asyncio.to_thread(_search, query)
        logging.info(f"web search results for query '{query}': {results}")
        return results
    except Exception as e:
        logging.error(f"Error occurred while searching the web: {e}")
        raise
