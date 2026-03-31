"""
Xybernetex Python SDK
~~~~~~~~~~~~~~~~~~~~~

Sync usage::

    import xybernetex

    client = xybernetex.Client(api_key="...", base_url="https://your-server")

    run = client.runs.create("Analyse the fundraising readiness of Company X")

    # Stream live progress
    for event in run.stream():
        print(event.type, event.data)

    # Or with callbacks
    run.stream(
        on_step=lambda e: print(f"Step {e.step_number}: {e.action_type}"),
        on_artifact=lambda e: print(f"Artifact: {e.title}"),
        on_complete=lambda e: print(f"Done: {e.conclusion}"),
    )

    run.wait()

    # Export artifacts
    run.artifacts[0].to_docx("report.docx")
    run.artifacts[0].to_pdf("report.pdf")
    run.artifacts[0].to_xlsx("data.xlsx")
    run.artifacts[0].to_pptx("deck.pptx")

Async usage::

    import asyncio
    import xybernetex

    async def main():
        async with xybernetex.AsyncClient(api_key="...", base_url="...") as client:
            run = await client.runs.create("Build a competitor analysis for Notion")

            # Async generator
            async for event in run.stream():
                print(event.type)

            # Or async callbacks (sync or async callables both work)
            await run.stream(
                on_step=lambda e: print(e.step_number),
                on_complete=lambda e: print(e.conclusion),
            )

            await run.wait()
            run.artifacts[0].to_pdf("analysis.pdf")

    asyncio.run(main())

Optional export dependencies::

    pip install xybernetex[docx]   # Word documents
    pip install xybernetex[pdf]    # PDF (reportlab + markdown)
    pip install xybernetex[xlsx]   # Excel workbooks
    pip install xybernetex[pptx]   # PowerPoint presentations
    pip install xybernetex[all]    # Everything
"""
from __future__ import annotations

from typing import Any, Optional

from xybernetex._client import (
    APIError,
    Client,
    NotFoundError,
    Run,
    RunFailedError,
    RunsResource,
    XybernetexError,
)
from xybernetex._async_client import (
    AsyncClient,
    AsyncRun,
    AsyncRunsResource,
)
from xybernetex._models import Artifact, Event


def run(
    goal: str,
    *,
    api_key: Optional[str] = None,
    base_url: str = "http://localhost:8000",
    model: str = "llama70b",
    tools: list[Any] | None = None,
    capability_manifest: dict[str, Any] | None = None,
    poll_interval: float = 5.0,
    timeout: float | None = None,
    request_timeout: float = 30.0,
    raise_on_failure: bool = True,
) -> Run:
    """
    The simplest blocking SDK entrypoint.

    This is the easiest "just do the work" path: create a client, submit the
    goal, wait for completion, and return the finished run.
    """
    with Client(
        api_key=api_key,
        base_url=base_url,
        timeout=request_timeout,
    ) as client:
        return client.run(
            goal,
            model=model,
            tools=tools,
            capability_manifest=capability_manifest,
            wait=True,
            poll_interval=poll_interval,
            timeout=timeout,
            raise_on_failure=raise_on_failure,
        )

__all__ = [
    # Top-level helpers
    "run",
    # Clients
    "Client",
    "AsyncClient",
    # Resources
    "RunsResource",
    "AsyncRunsResource",
    # Models
    "Run",
    "AsyncRun",
    "Artifact",
    "Event",
    # Exceptions
    "XybernetexError",
    "APIError",
    "NotFoundError",
    "RunFailedError",
]

__version__ = "0.1.0"
