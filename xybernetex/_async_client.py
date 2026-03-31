"""
Asynchronous Xybernetex client.
"""
from __future__ import annotations

import asyncio
import inspect
import os
from typing import Any, AsyncIterator, Callable, Coroutine, List, Optional, Union

import httpx

from xybernetex._models import Artifact, Event, _artifact_from_dict
from xybernetex._sse import aiter_sse
from xybernetex._client import (
    APIError,
    NotFoundError,
    RunFailedError,
    XybernetexError,
    _TERMINAL,
    _build_run_payload,
)


# ── _AsyncStream ───────────────────────────────────────────────────────────────

class _AsyncStream:
    """
    Returned by :meth:`AsyncRun.stream`.

    Supports two usage patterns:

    **Async generator** (``async for``):

    .. code-block:: python

        async for event in run.stream():
            print(event.type)

    **Awaitable with callbacks**:

    .. code-block:: python

        await run.stream(
            on_step=lambda e: print(e.step_number),
            on_artifact=lambda e: print(e.title),
        )

    Callbacks may be plain functions or coroutines — both work.
    """

    def __init__(
        self,
        run: "AsyncRun",
        *,
        on_step: Optional[Callable] = None,
        on_artifact: Optional[Callable] = None,
        on_complete: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        on_cancelled: Optional[Callable] = None,
        on_event: Optional[Callable] = None,
    ):
        self._run = run
        self._callbacks = {
            "step": on_step,
            "artifact": on_artifact,
            "completed": on_complete,
            "failed": on_error,
            "cancelled": on_cancelled,
            "_any": on_event,
        }

    # Used by ``async for event in run.stream():``
    def __aiter__(self) -> AsyncIterator[Event]:
        return self._run._aiter_stream()

    # Used by ``await run.stream(on_step=...)``
    def __await__(self):
        return self._run_callbacks().__await__()

    async def _run_callbacks(self) -> None:
        async for event in self._run._aiter_stream():
            if cb := self._callbacks.get("_any"):
                await _call(cb, event)
            if cb := self._callbacks.get(event.type):
                await _call(cb, event)


# ── AsyncRun ───────────────────────────────────────────────────────────────────

class AsyncRun:
    """
    Async version of :class:`~xybernetex.Run`.

    All methods that touch the network are coroutines.

    Usage::

        run = await client.runs.create("Summarise the latest SEC filing for AAPL")

        async for event in run.stream():
            print(event.type)

        await run.wait()
        run.artifacts[0].to_pdf("filing_summary.pdf")
    """

    def __init__(self, data: dict, *, _client: "AsyncClient"):
        self._client = _client
        self._load(data)

    def _load(self, data: dict) -> None:
        self.run_id: str = data["run_id"]
        self.status: str = data.get("status", "queued")
        self.goal: str = data.get("goal", "")
        self.model: str = data.get("model", "llama70b")
        self.created_at: Optional[str] = data.get("created_at")
        self.started_at: Optional[str] = data.get("started_at")
        self.completed_at: Optional[str] = data.get("completed_at")
        self.step_count: int = int(data.get("step_count") or 0)
        self.artifact_count: int = int(data.get("artifact_count") or 0)
        self.tool_count: int = int(data.get("tool_count") or 0)
        self.worker: Optional[str] = data.get("worker")
        self.conclusion: Optional[str] = data.get("conclusion")
        self.report_md: Optional[str] = data.get("report_md")
        self.error: Optional[str] = data.get("error")
        self.tools: List[Any] = list(data.get("tools") or [])
        self.capability_manifest: Optional[dict[str, Any]] = data.get("capability_manifest")
        self.artifacts: List[Artifact] = [
            _artifact_from_dict(a) for a in (data.get("artifacts") or [])
        ]

    @property
    def text(self) -> str:
        """Return the most useful text output for the completed run."""
        return self.report_md or self.conclusion or ""

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def refresh(self) -> "AsyncRun":
        """Pull the latest state from the API and update this object in-place."""
        data = await self._client._request("GET", f"/runs/{self.run_id}")
        self._load(data)
        return self

    async def cancel(self) -> "AsyncRun":
        """Request cancellation. Returns the refreshed run."""
        await self._client._request("DELETE", f"/runs/{self.run_id}")
        return await self.refresh()

    async def wait(
        self,
        *,
        poll_interval: float = 5.0,
        timeout: Optional[float] = None,
        raise_on_failure: bool = True,
    ) -> "AsyncRun":
        """
        Await until the run reaches a terminal state.

        Args:
            poll_interval: Seconds between status polls.
            timeout: Maximum seconds to wait.
            raise_on_failure: Raises ``RunFailedError`` on failed runs.
        """
        deadline = (asyncio.get_running_loop().time() + timeout) if timeout else None
        while self.status not in _TERMINAL:
            if deadline and asyncio.get_running_loop().time() > deadline:
                raise TimeoutError(
                    f"Run {self.run_id} did not complete within {timeout}s"
                )
            await asyncio.sleep(poll_interval)
            await self.refresh()

        if raise_on_failure and self.status == "failed":
            raise RunFailedError(self)
        return self

    # ── Streaming ──────────────────────────────────────────────────────────────

    def stream(
        self,
        *,
        on_step: Optional[Callable] = None,
        on_artifact: Optional[Callable] = None,
        on_complete: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        on_cancelled: Optional[Callable] = None,
        on_event: Optional[Callable] = None,
    ) -> _AsyncStream:
        """
        Stream live events from the run.

        **Async generator style** (no callbacks):

        .. code-block:: python

            async for event in run.stream():
                print(event.type, event.data)

        **Callback style** (awaitable, callbacks may be sync or async):

        .. code-block:: python

            await run.stream(
                on_step=lambda e: print(e.step_number, e.action_type),
                on_artifact=lambda e: print(e.title),
                on_complete=lambda e: print(e.conclusion),
            )
        """
        return _AsyncStream(
            self,
            on_step=on_step,
            on_artifact=on_artifact,
            on_complete=on_complete,
            on_error=on_error,
            on_cancelled=on_cancelled,
            on_event=on_event,
        )

    async def _aiter_stream(self) -> AsyncIterator[Event]:
        """Internal async generator — yields Event objects from the SSE endpoint."""
        url = f"{self._client._base_url}/runs/{self.run_id}/stream"
        headers = {}
        if self._client._api_key:
            headers["X-Api-Key"] = self._client._api_key

        async with httpx.AsyncClient(timeout=None) as http:
            async with http.stream("GET", url, headers=headers) as response:
                _async_raise_for_status(response)
                async for raw in aiter_sse(response):
                    event_type = raw.get("type", "")
                    if event_type == "stream_end":
                        break
                    event = Event(
                        type=event_type,
                        run_id=raw.get("run_id", self.run_id),
                        data={
                            k: v
                            for k, v in raw.items()
                            if k not in ("type", "run_id")
                        },
                    )
                    # Keep local state in sync
                    if event_type == "completed":
                        self.status = "completed"
                        self.conclusion = event.conclusion
                    elif event_type == "failed":
                        self.status = "failed"
                        self.error = event.error
                    elif event_type == "cancelled":
                        self.status = "cancelled"
                    elif event_type == "step":
                        self.step_count = event.step_number or self.step_count
                    elif event_type == "artifact":
                        self.artifact_count += 1

                    yield event
                    if event_type in _TERMINAL:
                        break

    def __repr__(self) -> str:
        return (
            f"AsyncRun(run_id={self.run_id!r}, status={self.status!r}, "
            f"goal={self.goal[:50]!r})"
        )


# ── AsyncRunsResource ──────────────────────────────────────────────────────────

class AsyncRunsResource:
    """``client.runs`` — async CRUD operations for agent runs."""

    def __init__(self, client: "AsyncClient"):
        self._client = client

    async def create(
        self,
        goal: str,
        *,
        model: str = "cloudflare",
        tools: Optional[List[Any]] = None,
        capability_manifest: Optional[dict[str, Any]] = None,
        llm_provider:   Optional[str] = None,
        llm_api_key:    Optional[str] = None,
        llm_model:      Optional[str] = None,
        cf_account_id:  Optional[str] = None,
        cf_api_token:   Optional[str] = None,
        tavily_api_key: Optional[str] = None,
        resend_api_key: Optional[str] = None,
    ) -> AsyncRun:
        """Submit a new agent run and return an :class:`AsyncRun`."""
        stub = await self._client._request(
            "POST",
            "/runs",
            json=_build_run_payload(
                goal,
                model=model,
                tools=tools,
                capability_manifest=capability_manifest,
                llm_provider=llm_provider,
                llm_api_key=llm_api_key,
                llm_model=llm_model,
                cf_account_id=cf_account_id,
                cf_api_token=cf_api_token,
                tavily_api_key=tavily_api_key,
                resend_api_key=resend_api_key,
            ),
        )
        data = await self._client._request("GET", f"/runs/{stub['run_id']}")
        return AsyncRun(data, _client=self._client)

    async def submit(
        self,
        goal: str,
        *,
        model: str = "cloudflare",
        tools: Optional[List[Any]] = None,
        capability_manifest: Optional[dict[str, Any]] = None,
        llm_provider:   Optional[str] = None,
        llm_api_key:    Optional[str] = None,
        llm_model:      Optional[str] = None,
        cf_account_id:  Optional[str] = None,
        cf_api_token:   Optional[str] = None,
        tavily_api_key: Optional[str] = None,
        resend_api_key: Optional[str] = None,
    ) -> AsyncRun:
        """Friendly alias for :meth:`create`."""
        return await self.create(
            goal,
            model=model,
            tools=tools,
            capability_manifest=capability_manifest,
            llm_provider=llm_provider,
            llm_api_key=llm_api_key,
            llm_model=llm_model,
            cf_account_id=cf_account_id,
            cf_api_token=cf_api_token,
            tavily_api_key=tavily_api_key,
            resend_api_key=resend_api_key,
        )

    async def get(self, run_id: str) -> AsyncRun:
        """Fetch a run by ID."""
        data = await self._client._request("GET", f"/runs/{run_id}")
        return AsyncRun(data, _client=self._client)

    async def list(self) -> List[AsyncRun]:
        """List all runs, most recent first."""
        items = await self._client._request("GET", "/runs")
        return [AsyncRun(item, _client=self._client) for item in items]

    async def cancel(self, run_id: str) -> AsyncRun:
        """Cancel a run by ID."""
        await self._client._request("DELETE", f"/runs/{run_id}")
        return await self.get(run_id)


# ── AsyncClient ────────────────────────────────────────────────────────────────

class AsyncClient:
    """
    Asynchronous Xybernetex client.

    Use as a context manager to ensure the underlying HTTP connection pool is
    closed cleanly, or call :meth:`aclose` manually when done.

    .. code-block:: python

        async with xybernetex.AsyncClient(api_key="...", base_url="...") as client:
            run = await client.runs.create("Build a competitor analysis for Notion")

            async for event in run.stream():
                print(event.type)

            await run.wait()
            print(run.conclusion)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
    ):
        self._api_key = api_key or os.getenv("XYBERNETEX_API_KEY", "")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._http: Optional[httpx.AsyncClient] = None
        self.runs = AsyncRunsResource(self)

    async def run(
        self,
        goal: str,
        *,
        model: str = "cloudflare",
        tools: Optional[List[Any]] = None,
        capability_manifest: Optional[dict[str, Any]] = None,
        llm_provider:   Optional[str] = None,
        llm_api_key:    Optional[str] = None,
        llm_model:      Optional[str] = None,
        cf_account_id:  Optional[str] = None,
        cf_api_token:   Optional[str] = None,
        tavily_api_key: Optional[str] = None,
        resend_api_key: Optional[str] = None,
        wait: bool = True,
        poll_interval: float = 5.0,
        timeout: Optional[float] = None,
        raise_on_failure: bool = True,
    ) -> AsyncRun:
        """
        Submit a goal with one call.

        By default this awaits completion. Pass ``wait=False`` to get the live
        run handle immediately for streaming or manual polling.
        """
        run = await self.runs.submit(
            goal,
            model=model,
            tools=tools,
            capability_manifest=capability_manifest,
            llm_provider=llm_provider,
            llm_api_key=llm_api_key,
            llm_model=llm_model,
            cf_account_id=cf_account_id,
            cf_api_token=cf_api_token,
            tavily_api_key=tavily_api_key,
            resend_api_key=resend_api_key,
        )
        if wait:
            return await run.wait(
                poll_interval=poll_interval,
                timeout=timeout,
                raise_on_failure=raise_on_failure,
            )
        return run

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            headers = {"Accept": "application/json"}
            if self._api_key:
                headers["X-Api-Key"] = self._api_key
            self._http = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=self._timeout,
            )
        return self._http

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        http = await self._get_http()
        resp = await http.request(method, path, **kwargs)
        _async_raise_for_status(resp)
        return resp.json()

    async def health(self) -> dict:
        """Check API and Redis connectivity."""
        return await self._request("GET", "/health")

    async def aclose(self) -> None:
        """Close the underlying HTTP connection pool."""
        if self._http and not self._http.is_closed:
            await self._http.aclose()

    async def __aenter__(self) -> "AsyncClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    def __repr__(self) -> str:
        return f"AsyncClient(base_url={self._base_url!r})"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _async_raise_for_status(resp: httpx.Response) -> None:
    if resp.status_code == 404:
        raise NotFoundError(404, resp.text[:200])
    if resp.is_error:
        raise APIError(resp.status_code, resp.text[:200])


async def _call(fn: Callable, *args: Any) -> None:
    """Call a function that may be a coroutine or a plain function."""
    result = fn(*args)
    if inspect.isawaitable(result):
        await result
