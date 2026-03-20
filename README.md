# Xybernetex Python SDK

![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![PyPI](https://img.shields.io/pypi/v/xybernetex.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

The official Python SDK for the [Xybernetex](https://app.xybernetex.com) agent platform. Submit goals, stream agent reasoning in real time, and retrieve structured artifacts — all from a clean, typed interface.

---

## Table of Contents

- [Quick Install](#quick-install)
- [Authentication](#authentication)
- [Quick Start](#quick-start)
- [Streaming](#streaming)
- [Async Usage](#async-usage)
- [Async Streaming](#async-streaming)
- [Async Streaming with Callbacks](#async-streaming-with-callbacks)
- [Models](#models)
- [Event Reference](#event-reference)
- [Artifact Export](#artifact-export)
- [Error Handling](#error-handling)
- [Full Working Example](#full-working-example)
- [API Reference](#api-reference)
- [Development / Contributing](#development--contributing)

---

## Quick Install

```bash
pip install xybernetex
```

### Optional extras

Install additional extras to unlock artifact export formats:

```bash
pip install "xybernetex[docx]"   # Export artifacts as Word documents
pip install "xybernetex[pdf]"    # Export artifacts as PDFs
pip install "xybernetex[xlsx]"   # Export artifacts as Excel spreadsheets
pip install "xybernetex[pptx]"   # Export artifacts as PowerPoint presentations
pip install "xybernetex[all]"    # Install all export extras
```

**Requirements:** Python 3.10 or later, `requests>=2.31`, `httpx>=0.27`

---

## Authentication

API keys are issued per account and carry the prefix `xyk_`.

**Generate a key:**

1. Sign in at [app.xybernetex.com](https://app.xybernetex.com)
2. Navigate to **Settings → API Keys**
3. Click **Create new key** and copy the value immediately — it is only shown once

**Pass your key to the client:**

```python
from xybernetex import Client

client = Client(api_key="xyk_your_key_here")
```

Store keys in environment variables rather than source code:

```python
import os
from xybernetex import Client

client = Client(api_key=os.environ["XYBERNETEX_API_KEY"])
```

You can also override the base URL for self-hosted deployments:

```python
client = Client(
    api_key=os.environ["XYBERNETEX_API_KEY"],
    base_url="https://your-private-deployment.example.com",
)
```

---

## Quick Start

Submit a goal and block until the agent finishes. The `wait()` call polls the API and returns once the run reaches a terminal state.

```python
import os
from xybernetex import Client, RunFailedError

client = Client(api_key=os.environ["XYBERNETEX_API_KEY"])

run = client.runs.submit(
    goal="Research the top five open-source LLM frameworks and summarize their trade-offs.",
    model="llama70b",
)

print(f"Run started: {run.run_id}")
print(f"Status: {run.status}")

run = run.wait(poll_interval=2.0, timeout=300.0)

print(f"Finished with status: {run.status}")
print(f"Goal: {run.goal}")
```

After `wait()` returns you can access any artifacts produced during the run (see [Artifact Export](#artifact-export)).

---

## Streaming

Use `run.stream()` to consume server-sent events as the agent works. This gives you step-by-step visibility into the agent's actions, focus, and rewards in real time.

```python
import os
from xybernetex import Client

client = Client(api_key=os.environ["XYBERNETEX_API_KEY"])

run = client.runs.submit(
    goal="Write a Python script that fetches the current Bitcoin price.",
    model="llama70b",
)

stream = run.stream()

if stream is None:
    print("No stream available for this run, falling back to polling.")
    run = run.wait()
else:
    for event in stream:
        if event.type == "step":
            print(f"[Step {event.step_number}] {event.action_type} — focus: {event.focus}")
            if event.reward is not None:
                print(f"  Reward: {event.reward}")

        elif event.type == "completed":
            print(f"Run completed. Conclusion: {event.conclusion}")

        elif event.type == "failed":
            print(f"Run failed: {event.error}")

        elif event.type == "cancelled":
            print("Run was cancelled.")

        elif event.type == "stream_end":
            print("Stream closed.")
            break
```

`run.stream()` returns `None` when the endpoint does not support SSE for the current run. Always guard against `None` before iterating.

---

## Async Usage

`AsyncClient` mirrors the sync interface but all blocking calls are coroutines. Use it inside any `asyncio`-based application or framework (FastAPI, aiohttp, etc.).

```python
import asyncio
import os
from xybernetex import AsyncClient, RunFailedError

async def main():
    client = AsyncClient(api_key=os.environ["XYBERNETEX_API_KEY"])

    run = await client.runs.submit(
        goal="Produce a SWOT analysis for a hypothetical EV startup.",
        model="mistral",
    )

    print(f"Run started: {run.run_id}")

    run = await run.wait(poll_interval=2.0, timeout=600.0)

    print(f"Status: {run.status}")

asyncio.run(main())
```

`wait()` raises `RunFailedError` if the run ends with status `"failed"`. Wrap it in a `try/except` when you need to inspect the failed run object (see [Error Handling](#error-handling)).

---

## Async Streaming

`AsyncRun.stream()` returns an `_AsyncStream` object that supports two consumption patterns depending on your needs.

### Pattern 1 — Async iteration

Receive each event as it arrives:

```python
import asyncio
import os
from xybernetex import AsyncClient

async def main():
    client = AsyncClient(api_key=os.environ["XYBERNETEX_API_KEY"])

    run = await client.runs.submit(
        goal="List ten creative names for a developer tools company.",
        model="qwen",
    )

    async for event in run.stream():
        if event.type == "step":
            print(f"[Step {event.step_number}] {event.action_type}")

        elif event.type == "completed":
            print(f"Done. Conclusion: {event.conclusion}")
            break

asyncio.run(main())
```

### Pattern 2 — Await for completion

Await the stream directly to block until the run finishes, discarding intermediate events:

```python
import asyncio
import os
from xybernetex import AsyncClient

async def main():
    client = AsyncClient(api_key=os.environ["XYBERNETEX_API_KEY"])

    run = await client.runs.submit(
        goal="Summarize the history of the Rust programming language.",
        model="llama70b",
    )

    completed_run = await run.stream()
    print(f"Finished: {completed_run.status}")

asyncio.run(main())
```

---

## Async Streaming with Callbacks

Pass `on_event` and `on_complete` callbacks to `stream()` for a handler-based style. Both sync and async callables are accepted.

### Sync callbacks

```python
import asyncio
import os
from xybernetex import AsyncClient, Event, AsyncRun

def handle_event(event: Event) -> None:
    if event.type == "step":
        print(f"[Step {event.step_number}] {event.action_type} — {event.focus}")

def handle_complete(run: AsyncRun) -> None:
    print(f"Run {run.run_id} finished with status: {run.status}")

async def main():
    client = AsyncClient(api_key=os.environ["XYBERNETEX_API_KEY"])

    run = await client.runs.submit(
        goal="Draft a one-page executive summary on the state of AI in 2025.",
        model="llama70b",
    )

    await run.stream(on_event=handle_event, on_complete=handle_complete)

asyncio.run(main())
```

### Async callbacks

```python
import asyncio
import os
from xybernetex import AsyncClient, Event, AsyncRun

async def handle_event(event: Event) -> None:
    if event.type == "step":
        await asyncio.sleep(0)  # yield to event loop
        print(f"[Step {event.step_number}] {event.action_type}")

async def handle_complete(run: AsyncRun) -> None:
    print(f"Completed: {run.run_id}")

async def main():
    client = AsyncClient(api_key=os.environ["XYBERNETEX_API_KEY"])

    run = await client.runs.submit(
        goal="Create a competitive analysis of the top three cloud providers.",
        model="mistral",
    )

    await run.stream(on_event=handle_event, on_complete=handle_complete)

asyncio.run(main())
```

---

## Models

| Model ID | Description |
|---|---|
| `"llama"` | LLaMA (base tier) — fast, cost-efficient for straightforward tasks |
| `"llama70b"` | LLaMA 70B (default) — high-quality reasoning, recommended for most workloads |
| `"mistral"` | Mistral — strong instruction-following and structured output generation |
| `"qwen"` | Qwen — multilingual capability, well-suited for non-English goals |

Pass the model ID string to `runs.submit()`:

```python
run = client.runs.submit(goal="Translate this contract to French.", model="qwen")
```

---

## Event Reference

Events are emitted during streaming. Each event exposes a `type` string and a raw `data` dict, plus typed accessor properties for the fields relevant to that event type. Accessors return `None` when the field is not present in the event payload.

| Event type | Relevant accessors | Description |
|---|---|---|
| `"step"` | `step_number`, `action_type`, `focus`, `reward` | The agent completed one reasoning or action step |
| `"completed"` | `conclusion`, `artifact_id`, `title`, `preview` | Run finished successfully |
| `"failed"` | `error` | Run ended in a failure state |
| `"cancelled"` | — | Run was cancelled before completion |
| `"stream_end"` | — | The SSE stream has closed; no further events will arrive |

### Accessor reference

| Property | Type | Present on |
|---|---|---|
| `event.type` | `str` | all events |
| `event.data` | `dict` | all events (raw payload) |
| `event.step_number` | `int \| None` | `"step"` |
| `event.action_type` | `str \| None` | `"step"` |
| `event.focus` | `str \| None` | `"step"` |
| `event.reward` | `float \| None` | `"step"` |
| `event.artifact_id` | `str \| None` | `"completed"` |
| `event.title` | `str \| None` | `"completed"` |
| `event.preview` | `str \| None` | `"completed"` |
| `event.conclusion` | `str \| None` | `"completed"` |
| `event.error` | `str \| None` | `"failed"` |

```python
for event in run.stream():
    if event.type == "step":
        print(event.step_number, event.action_type, event.focus)
    elif event.type == "completed":
        print(event.conclusion)
        if event.artifact_id:
            print(f"Artifact ID: {event.artifact_id}")
```

---

## Artifact Export

Artifacts are structured outputs produced by a run. Each artifact exposes its raw bytes via `artifact.data` and can be saved or converted to several file formats.

### Accessing artifacts

After a run completes you can retrieve artifacts using the artifact ID surfaced on the `"completed"` event or directly from the run object.

```python
artifact = client.runs.get_artifact(artifact_id=event.artifact_id)

print(artifact.id)
print(artifact.title)
print(artifact.content_type)
```

### Save raw bytes

```python
artifact.save("/tmp/output.bin")
```

### Export as Word document

Requires `pip install "xybernetex[docx]"`:

```python
artifact.to_docx("/tmp/report.docx")
```

### Export as PDF

Requires `pip install "xybernetex[pdf]"`:

```python
artifact.to_pdf("/tmp/report.pdf")
```

### Export as Excel spreadsheet

Requires `pip install "xybernetex[xlsx]"`:

```python
artifact.to_xlsx("/tmp/data.xlsx")
```

### Export as PowerPoint presentation

Requires `pip install "xybernetex[pptx]"`:

```python
artifact.to_pptx("/tmp/slides.pptx")
```

### Artifact model reference

| Attribute / Method | Type | Description |
|---|---|---|
| `artifact.id` | `str` | Unique artifact identifier |
| `artifact.title` | `str` | Human-readable title |
| `artifact.content_type` | `str` | MIME type of the artifact data |
| `artifact.data` | `bytes` | Raw artifact content |
| `artifact.save(path)` | `None` | Write raw bytes to `path` |
| `artifact.to_docx(path)` | `None` | Export as `.docx` (requires `[docx]`) |
| `artifact.to_pdf(path)` | `None` | Export as `.pdf` (requires `[pdf]`) |
| `artifact.to_xlsx(path)` | `None` | Export as `.xlsx` (requires `[xlsx]`) |
| `artifact.to_pptx(path)` | `None` | Export as `.pptx` (requires `[pptx]`) |

---

## Error Handling

All SDK errors inherit from `XybernetexError`. Import the exceptions you need:

```python
from xybernetex import XybernetexError, APIError, NotFoundError, RunFailedError
```

### RunFailedError — run ended in failed status

Raised by `wait()` when the agent run finishes with status `"failed"`. The original run object is attached to the exception.

```python
from xybernetex import Client, RunFailedError

client = Client(api_key=os.environ["XYBERNETEX_API_KEY"])
run = client.runs.submit(goal="Analyse the Q4 earnings report.", model="llama70b")

try:
    run = run.wait(timeout=300.0)
    print(f"Success: {run.status}")
except RunFailedError as exc:
    print(f"Run {exc.run.run_id} failed.")
    print(f"Final status: {exc.run.status}")
```

### NotFoundError — run or resource not found

Raised when a requested run ID does not exist (HTTP 404).

```python
from xybernetex import Client, NotFoundError

client = Client(api_key=os.environ["XYBERNETEX_API_KEY"])

try:
    run = client.runs.get("run_nonexistent_id")
except NotFoundError:
    print("That run does not exist.")
```

### APIError — unexpected HTTP error

Raised for any non-404 HTTP error returned by the API. Exposes `status_code` and `message`.

```python
from xybernetex import Client, APIError

client = Client(api_key=os.environ["XYBERNETEX_API_KEY"])

try:
    run = client.runs.submit(goal="Do something.", model="llama70b")
except APIError as exc:
    print(f"API error {exc.status_code}: {exc.message}")
```

### XybernetexError — catch-all

Catches any SDK error when you do not need to distinguish between types:

```python
from xybernetex import Client, XybernetexError

client = Client(api_key=os.environ["XYBERNETEX_API_KEY"])

try:
    run = client.runs.submit(goal="Research quantum computing.", model="llama70b")
    run = run.wait()
except XybernetexError as exc:
    print(f"SDK error: {exc}")
```

---

## Full Working Example

The following script demonstrates a complete sync agent run with streaming, event handling, and artifact export. Copy it, set your API key, and run it directly.

```python
import os
import sys
from xybernetex import (
    Client,
    APIError,
    NotFoundError,
    RunFailedError,
    XybernetexError,
)

GOAL = (
    "Research the five most popular Python web frameworks. "
    "For each one, list: release year, primary use case, performance "
    "characteristics, and a one-sentence opinion on when to choose it. "
    "Format the output as a structured report."
)

def main() -> None:
    api_key = os.environ.get("XYBERNETEX_API_KEY")
    if not api_key:
        print("Error: XYBERNETEX_API_KEY environment variable is not set.")
        sys.exit(1)

    client = Client(api_key=api_key)

    print("Submitting run...")
    try:
        run = client.runs.submit(goal=GOAL, model="llama70b")
    except APIError as exc:
        print(f"Failed to submit run: HTTP {exc.status_code} — {exc.message}")
        sys.exit(1)

    print(f"Run ID   : {run.run_id}")
    print(f"Goal     : {run.goal}")
    print(f"Model    : {run.model}")
    print(f"Status   : {run.status}")
    print("-" * 60)

    stream = run.stream()
    artifact_id = None

    if stream is not None:
        print("Streaming agent execution...\n")
        for event in stream:
            if event.type == "step":
                step = event.step_number if event.step_number is not None else "?"
                action = event.action_type or "unknown"
                focus = event.focus or ""
                reward_str = f" (reward: {event.reward:.3f})" if event.reward is not None else ""
                print(f"  [Step {step}] {action}{reward_str}")
                if focus:
                    print(f"           {focus}")

            elif event.type == "completed":
                print("\nRun completed.")
                if event.conclusion:
                    print(f"Conclusion: {event.conclusion}")
                if event.artifact_id:
                    artifact_id = event.artifact_id
                    print(f"Artifact ID: {artifact_id} — \"{event.title}\"")

            elif event.type == "failed":
                print(f"\nRun failed: {event.error}")
                sys.exit(1)

            elif event.type == "cancelled":
                print("\nRun was cancelled.")
                sys.exit(0)

            elif event.type == "stream_end":
                break
    else:
        print("SSE not available, polling until completion...")
        try:
            run = run.wait(poll_interval=2.0, timeout=600.0)
            print(f"Run finished with status: {run.status}")
        except RunFailedError as exc:
            print(f"Run {exc.run.run_id} failed.")
            sys.exit(1)

    if artifact_id:
        print("\nExporting artifact...")
        try:
            artifact = client.runs.get_artifact(artifact_id=artifact_id)
            out_path = f"/tmp/{artifact.title.replace(' ', '_')}.docx"
            artifact.to_docx(out_path)
            print(f"Saved Word document to: {out_path}")
        except NotFoundError:
            print(f"Artifact {artifact_id} not found.")
        except XybernetexError as exc:
            print(f"Could not export artifact: {exc}")

    print("\nDone.")

if __name__ == "__main__":
    main()
```

Run it:

```bash
export XYBERNETEX_API_KEY="xyk_your_key_here"
pip install "xybernetex[docx]"
python agent_run.py
```

---

## API Reference

### `Client`

```python
Client(api_key: str, base_url: str = "https://api.xybernetex.com")
```

| Member | Signature | Returns | Description |
|---|---|---|---|
| `client.runs.submit` | `(goal: str, model: str = "llama70b") -> Run` | `Run` | Submit a new agent run |

---

### `Run`

Returned by `Client.runs.submit()`.

| Member | Type / Signature | Description |
|---|---|---|
| `run.run_id` | `str` | Unique identifier for this run |
| `run.status` | `str` | Current status: `"pending"`, `"running"`, `"completed"`, `"failed"`, `"cancelled"` |
| `run.goal` | `str` | The goal string submitted |
| `run.model` | `str` | Model used for this run |
| `run.wait(poll_interval, timeout)` | `(float = 2.0, float \| None = None) -> Run` | Block until terminal state; raises `RunFailedError` on failure |
| `run.stream()` | `() -> Iterator[Event] \| None` | Return SSE event iterator, or `None` if unavailable |
| `run.cancel()` | `() -> None` | Request cancellation of this run |

---

### `AsyncClient`

```python
AsyncClient(api_key: str, base_url: str = "https://api.xybernetex.com")
```

| Member | Signature | Returns | Description |
|---|---|---|---|
| `await client.runs.submit` | `(goal: str, model: str = "llama70b") -> AsyncRun` | `AsyncRun` | Submit a new agent run asynchronously |

---

### `AsyncRun`

Returned by `AsyncClient.runs.submit()`.

| Member | Type / Signature | Description |
|---|---|---|
| `run.run_id` | `str` | Unique identifier for this run |
| `run.status` | `str` | Current run status |
| `run.goal` | `str` | The goal string submitted |
| `run.model` | `str` | Model used for this run |
| `await run.wait(poll_interval, timeout)` | `(float = 2.0, float \| None = None) -> AsyncRun` | Await terminal state; raises `RunFailedError` on failure |
| `run.stream(on_event, on_complete)` | `(callable \| None, callable \| None) -> _AsyncStream` | Return async stream supporting `async for` and `await` |

---

### `Event`

| Property | Type | Description |
|---|---|---|
| `event.type` | `str` | Event type string |
| `event.data` | `dict` | Raw event payload |
| `event.step_number` | `int \| None` | Step index (step events) |
| `event.action_type` | `str \| None` | Action name (step events) |
| `event.focus` | `str \| None` | Agent focus description (step events) |
| `event.reward` | `float \| None` | Reward signal (step events) |
| `event.artifact_id` | `str \| None` | Artifact ID (completed events) |
| `event.title` | `str \| None` | Artifact title (completed events) |
| `event.preview` | `str \| None` | Artifact preview text (completed events) |
| `event.conclusion` | `str \| None` | Run conclusion summary (completed events) |
| `event.error` | `str \| None` | Error message (failed events) |

---

### `Artifact`

| Member | Type / Signature | Description |
|---|---|---|
| `artifact.id` | `str` | Unique artifact identifier |
| `artifact.title` | `str` | Human-readable title |
| `artifact.content_type` | `str` | MIME type |
| `artifact.data` | `bytes` | Raw artifact bytes |
| `artifact.save(path)` | `(str) -> None` | Write raw bytes to file |
| `artifact.to_docx(path)` | `(str) -> None` | Export as Word document |
| `artifact.to_pdf(path)` | `(str) -> None` | Export as PDF |
| `artifact.to_xlsx(path)` | `(str) -> None` | Export as Excel spreadsheet |
| `artifact.to_pptx(path)` | `(str) -> None` | Export as PowerPoint presentation |

---

### Exceptions

| Class | Inherits | Constructor | Description |
|---|---|---|---|
| `XybernetexError` | `Exception` | `(message: str)` | Base class for all SDK errors |
| `APIError` | `XybernetexError` | `(status_code: int, message: str)` | HTTP error returned by the API |
| `NotFoundError` | `APIError` | — | Resource not found (HTTP 404) |
| `RunFailedError` | `XybernetexError` | `(run: Run \| AsyncRun)` | Run ended in `"failed"` status; `exc.run` holds the run object |

---

## Development / Contributing

### Clone and install in development mode

```bash
git clone https://github.com/xybernetex/xybernetex-python.git
cd xybernetex-python

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -e ".[all]"
pip install -r requirements-dev.txt
```

### Run the test suite

```bash
pytest
```

Run with coverage:

```bash
pytest --cov=xybernetex --cov-report=term-missing
```

Run only the async tests:

```bash
pytest -k "async"
```

### Code style

The project uses `ruff` for linting and `black` for formatting:

```bash
ruff check xybernetex/
black xybernetex/
```

### Type checking

```bash
mypy xybernetex/
```

### Project layout

```
xybernetex/
├── __init__.py         # Public exports
├── _client.py          # Client and AsyncClient
├── _run.py             # Run and AsyncRun models
├── _event.py           # Event model and typed accessors
├── _artifact.py        # Artifact model and export methods
├── _stream.py          # _AsyncStream implementation
└── _errors.py          # Exception hierarchy
tests/
├── test_client.py
├── test_run.py
├── test_event.py
├── test_artifact.py
└── test_async.py
```

### Submitting a pull request

1. Fork the repository and create a feature branch from `main`
2. Make your changes with tests covering the new behaviour
3. Ensure `pytest`, `ruff`, `black`, and `mypy` all pass
4. Open a pull request with a clear description of the change and its motivation

---

## License

MIT License. See [LICENSE](./LICENSE) for details.
