# SDK Product Shaping Map

## Goal

Make the existing SDK feel less like a low-level run client and more like the
Stripe-style entrypoint for autonomous work.

The right framing is:

- Stripe promise: payments in a handful of lines
- Xybernetex promise: autonomous work in a handful of lines

This document maps the current SDK surface into:

- keep as-is
- rename or simplify
- add for the "7-line" onboarding path

## Current Strengths To Keep As-Is

### 1. `Client` and `AsyncClient`

Files:

- `xybernetex/_client.py`
- `xybernetex/_async_client.py`

Why keep:

- Clear authenticated session object
- Good fit for advanced and long-lived application usage
- Familiar shape for Python developers

### 2. `Run` and `AsyncRun`

Why keep:

- Good representation of lifecycle state
- `wait()`, `refresh()`, `cancel()`, and `stream()` are the right primitives
- They are the right advanced-level objects even if they are not the beginner
  entrypoint

### 3. Streaming Model

Why keep:

- Streaming events are a differentiator
- The callback and iterator patterns are both useful
- This is the right power feature once users move beyond the 7-line path

### 4. Artifact Export

Why keep:

- This gives the SDK a strong finished-work story
- Export helpers are practical and concrete
- They make the product feel outcome-oriented rather than token-oriented

### 5. Typed Models and Errors

Why keep:

- `Event`, `Artifact`, `RunFailedError`, and API exceptions are the correct
  advanced SDK surface
- They make the package feel professional and stable

## Rename Or Simplify

### 1. Promote `submit`, de-emphasize `create`

Current issue:

- The implementation used `client.runs.create(...)`
- The README was already teaching `client.runs.submit(...)`

Recommendation:

- Keep `create()` for compatibility
- Promote `submit()` in public docs and examples

Reason:

- "Submit a goal" matches the user's mental model
- "Create a run" reflects internal mechanics rather than user intent

### 2. Promote `client.run(...)`, de-emphasize `client.runs.*` for onboarding

Current issue:

- The package taught the run-resource object first
- That is good infrastructure, but it is not the simplest onboarding experience

Recommendation:

- `client.run(...)` should be the default documented path
- `client.runs.*` should remain the advanced surface

Reason:

- New users want to delegate an outcome, not manipulate a resource tree

### 3. Add a simple text result accessor

Current issue:

- Users need to know about `conclusion` versus `report_md`

Recommendation:

- Expose `run.text` as the high-level default text result

Reason:

- This gives the beginner path a single obvious thing to print

### 4. Hide internal nouns from the first page

De-emphasize in beginner docs:

- `RunsResource`
- `AsyncRunsResource`
- raw event taxonomy
- export extras

These should still exist, but they should not be the first impression.

## Add For The 7-Line Path

### 1. Top-level `xybernetex.run(...)`

Purpose:

- The single fastest path from "I installed the SDK" to "I got work done"

Shape:

```python
import xybernetex

result = xybernetex.run(
    "Research our top competitors and email me a summary",
    api_key="...",
)
print(result.text)
```

### 2. `Client.run(...)` and `AsyncClient.run(...)`

Purpose:

- Make the session object feel outcome-oriented, not just transport-oriented

Shape:

```python
client = xybernetex.Client(api_key="...")
result = client.run("Summarize this market", timeout=300)
```

Advanced shape:

```python
run = client.run("Write a Python script", wait=False)
for event in run.stream():
    ...
```

### 3. Keep a progressive-disclosure ladder

The SDK should layer like this:

1. `xybernetex.run(...)`
2. `client.run(...)`
3. `client.runs.submit(...)`
4. `run.stream()`, `run.wait()`, `run.cancel()`
5. future persistent-agent and connector APIs

That gives both simplicity and depth without forcing every user through the
advanced path.

## Suggested Public Story

### Beginner story

"Give Xybernetex a goal and get the result."

### Intermediate story

"Submit a run, stream progress, and retrieve artifacts."

### Advanced story

"Integrate autonomous work into your application with lifecycle control,
streaming telemetry, exports, and future connectors."

## Immediate Non-Breaking Wins

These are the highest-value low-risk improvements:

1. Add `submit()` aliases to sync and async run resources
2. Add `Client.run(...)` and `AsyncClient.run(...)`
3. Add top-level `xybernetex.run(...)`
4. Add `Run.text` and `AsyncRun.text`
5. Update Quick Start docs to use the simpler path first

## Later Additions

These belong after the first-path UX is locked:

- persistent `Agent(...)` objects
- tool/connector registration
- memory configuration
- policy and approval controls
- output routing configuration
- automations

Those are important, but they should be progressive disclosure, not day-one
cognitive load.

## Bottom Line

The existing SDK should not be replaced. It already has the right foundation.

What it needs is product shaping:

- keep the run-oriented engine
- add an outcome-oriented top layer
- teach the simplest path first
- reveal the deeper surface only when users need it
