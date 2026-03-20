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

__all__ = [
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
