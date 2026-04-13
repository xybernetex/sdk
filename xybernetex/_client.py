"""
Synchronous Xybernetex client.
"""
from __future__ import annotations

import os
import time
from typing import Any, Callable, Iterator, List, Optional

import requests

from xybernetex._models import Artifact, Event, _artifact_from_dict
from xybernetex._sse import iter_sse


# ── Exceptions ─────────────────────────────────────────────────────────────────

class XybernetexError(Exception):
    """Base exception for all SDK errors."""


class APIError(XybernetexError):
    """An HTTP error response from the Xybernetex API."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}: {message}")


class NotFoundError(APIError):
    """The requested run_id does not exist."""


class RunFailedError(XybernetexError):
    """Raised by ``run.wait()`` when the run ends in a failed state."""

    def __init__(self, run: "Run"):
        self.run = run
        super().__init__(f"Run {run.run_id} failed: {run.error}")


# ── Run ────────────────────────────────────────────────────────────────────────

_TERMINAL = frozenset({"completed", "failed", "cancelled"})


class Run:
    """
    Represents a single agent run.

    Returned by ``client.runs.create()`` and ``client.runs.get()``.
    All fields reflect the last known state; call ``run.refresh()`` to
    pull the latest from the API.
    """

    def __init__(self, data: dict, *, _client: "Client"):
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

    def refresh(self) -> "Run":
        """Pull the latest state from the API and update this object in-place."""
        data = self._client._request("GET", f"/runs/{self.run_id}")
        self._load(data)
        return self

    def cancel(self) -> "Run":
        """Request cancellation. Returns the refreshed run."""
        self._client._request("DELETE", f"/runs/{self.run_id}")
        return self.refresh()

    def wait(
        self,
        *,
        poll_interval: float = 5.0,
        timeout: Optional[float] = None,
        raise_on_failure: bool = True,
    ) -> "Run":
        """
        Block until the run reaches a terminal state (completed / failed / cancelled).

        Args:
            poll_interval: Seconds between status polls.
            timeout: Maximum seconds to wait. Raises ``TimeoutError`` if exceeded.
            raise_on_failure: If ``True`` (default), raises ``RunFailedError``
                              when the run ends in a failed state.
        """
        deadline = (time.monotonic() + timeout) if timeout else None
        while self.status not in _TERMINAL:
            if deadline and time.monotonic() > deadline:
                raise TimeoutError(
                    f"Run {self.run_id} did not complete within {timeout}s"
                )
            time.sleep(poll_interval)
            self.refresh()

        if raise_on_failure and self.status == "failed":
            raise RunFailedError(self)
        return self

    # ── Streaming ──────────────────────────────────────────────────────────────

    def stream(
        self,
        *,
        on_step: Optional[Callable[[Event], None]] = None,
        on_artifact: Optional[Callable[[Event], None]] = None,
        on_complete: Optional[Callable[[Event], None]] = None,
        on_error: Optional[Callable[[Event], None]] = None,
        on_cancelled: Optional[Callable[[Event], None]] = None,
        on_event: Optional[Callable[[Event], None]] = None,
    ) -> Optional[Iterator[Event]]:
        """
        Stream live events from the run.

        **Generator style** (no callbacks):

        .. code-block:: python

            for event in run.stream():
                print(event.type, event.data)

        **Callback style** (blocks until the stream closes):

        .. code-block:: python

            run.stream(
                on_step=lambda e: print(e.step_number, e.action_type),
                on_artifact=lambda e: print(e.title),
                on_complete=lambda e: print(e.conclusion),
            )

        When callbacks are supplied the method runs the stream internally and
        returns ``None``.  When no callbacks are supplied it returns an
        ``Iterator[Event]`` for you to consume.
        """
        has_callbacks = any(
            [on_step, on_artifact, on_complete, on_error, on_cancelled, on_event]
        )
        gen = self._iter_stream()
        if not has_callbacks:
            return gen

        for event in gen:
            if on_event:
                on_event(event)
            if event.type == "step" and on_step:
                on_step(event)
            elif event.type == "artifact" and on_artifact:
                on_artifact(event)
            elif event.type == "completed" and on_complete:
                on_complete(event)
            elif event.type == "failed" and on_error:
                on_error(event)
            elif event.type == "cancelled" and on_cancelled:
                on_cancelled(event)
        return None

    def _iter_stream(self) -> Iterator[Event]:
        """Internal generator — yields Event objects from the SSE endpoint."""
        response = self._client._stream_request(f"/runs/{self.run_id}/stream")
        for raw in iter_sse(response):
            event_type = raw.get("type", "")
            if event_type == "stream_end":
                break
            event = Event(
                type=event_type,
                run_id=raw.get("run_id", self.run_id),
                data={k: v for k, v in raw.items() if k not in ("type", "run_id")},
            )
            # Keep local state in sync without an extra HTTP call
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
                # Build a live Artifact object so run.artifacts is populated
                # during streaming without needing a refresh() call.
                if event.data.get("content"):
                    self.artifacts.append(_artifact_from_dict(event.data))

            yield event
            if event_type in _TERMINAL:
                break

    # ── Repr ──────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"Run(run_id={self.run_id!r}, status={self.status!r}, "
            f"goal={self.goal[:50]!r})"
        )


# ── RunsResource ───────────────────────────────────────────────────────────────

class RunsResource:
    """``client.runs`` — CRUD operations for agent runs."""

    def __init__(self, client: "Client"):
        self._client = client

    def create(
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
    ) -> Run:
        """
        Submit a new agent run.

        Args:
            goal:  The task description for the agent.
            model: LLM provider — ``"cloudflare"`` (default), ``"openai"``,
                   ``"anthropic"``, ``"gemini"``, or ``"mistral"``.
            tools: Optional tool names or tool descriptor dicts allowed for this run.
            capability_manifest: Optional full per-run capability manifest.
            llm_provider:   Override provider (same values as model).
            llm_api_key:    API key for the chosen LLM provider.
            llm_model:      Override the default model ID for the provider.
            cf_account_id:  Cloudflare account ID (cloudflare provider only).
            cf_api_token:   Cloudflare API token (cloudflare provider only).
            tavily_api_key: Tavily web search API key.
            resend_api_key: Resend email API key.

        Returns:
            A :class:`Run` object with ``status="queued"``.
        """
        stub = self._client._request(
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
        # Fetch full metadata (the POST response only returns run_id + status)
        data = self._client._request("GET", f"/runs/{stub['run_id']}")
        return Run(data, _client=self._client)

    def submit(
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
    ) -> Run:
        """Friendly alias for :meth:`create`."""
        return self.create(
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

    def get(self, run_id: str) -> Run:
        """Fetch a run by ID."""
        data = self._client._request("GET", f"/runs/{run_id}")
        return Run(data, _client=self._client)

    def list(self) -> List[Run]:
        """List all runs, most recent first."""
        items = self._client._request("GET", "/runs")
        return [Run(item, _client=self._client) for item in items]

    def cancel(self, run_id: str) -> Run:
        """Cancel a run by ID."""
        self._client._request("DELETE", f"/runs/{run_id}")
        return self.get(run_id)


# ── Client ─────────────────────────────────────────────────────────────────────

class Client:
    """
    Synchronous Xybernetex client.

    .. code-block:: python

        import xybernetex

        client = xybernetex.Client(api_key="...", base_url="https://your-server")

        run = client.runs.create("Analyse the fundraising readiness of Company X")

        for event in run.stream():
            print(event.type, event.data)

        run.wait()
        print(run.conclusion)
        run.artifacts[0].to_docx("report.docx")
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

        self._session = requests.Session()
        if self._api_key:
            self._session.headers["X-Api-Key"] = self._api_key
        self._session.headers["Accept"] = "application/json"

        self.runs = RunsResource(self)

    def run(
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
    ) -> Run:
        """
        Submit a goal with one call.

        By default this blocks until completion. Pass ``wait=False`` to get
        the live run handle immediately for streaming or manual polling.
        """
        run = self.runs.submit(
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
            return run.wait(
                poll_interval=poll_interval,
                timeout=timeout,
                raise_on_failure=raise_on_failure,
            )
        return run

    # ── Internal HTTP helpers ──────────────────────────────────────────────────

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self._base_url}{path}"
        resp = self._session.request(method, url, timeout=self._timeout, **kwargs)
        _raise_for_status(resp)
        return resp.json()

    def _stream_request(self, path: str) -> requests.Response:
        url = f"{self._base_url}{path}"
        resp = self._session.get(url, stream=True, timeout=None)
        _raise_for_status(resp)
        return resp

    # ── Top-level endpoints ────────────────────────────────────────────────────

    def health(self) -> dict:
        """Check API and Redis connectivity."""
        return self._request("GET", "/health")

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._session.close()

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"Client(base_url={self._base_url!r})"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _raise_for_status(resp: requests.Response) -> None:
    if resp.status_code == 404:
        raise NotFoundError(404, resp.text[:200])
    if not resp.ok:
        raise APIError(resp.status_code, resp.text[:200])


def _build_run_payload(
    goal: str,
    *,
    model: str,
    tools: Optional[List[Any]] = None,
    capability_manifest: Optional[dict[str, Any]] = None,
    llm_provider:   Optional[str] = None,
    llm_api_key:    Optional[str] = None,
    llm_model:      Optional[str] = None,
    cf_account_id:  Optional[str] = None,
    cf_api_token:   Optional[str] = None,
    tavily_api_key: Optional[str] = None,
    resend_api_key: Optional[str] = None,
) -> dict[str, Any]:
    if tools is not None and capability_manifest is not None:
        raise ValueError("Provide either tools or capability_manifest, not both.")
    payload: dict[str, Any] = {"goal": goal, "model": model}
    if tools is not None:
        payload["tools"] = tools
    if capability_manifest is not None:
        payload["capability_manifest"] = capability_manifest
    # Only include credential fields if provided — avoids sending empty strings
    for key, val in [
        ("llm_provider",   llm_provider),
        ("llm_api_key",    llm_api_key),
        ("llm_model",      llm_model),
        ("cf_account_id",  cf_account_id),
        ("cf_api_token",   cf_api_token),
        ("tavily_api_key", tavily_api_key),
        ("resend_api_key", resend_api_key),
    ]:
        if val:
            payload[key] = val
    return payload
