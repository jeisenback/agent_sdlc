# Session Management

This document describes session lifecycle and context management for `agent_sdlc` agents.

## Session concept
- A session represents a logical interaction context for an agent run (e.g., a single pipeline execution or user interaction).
- Each session has a `session_id` (UUID), `started_at`, and optional `metadata` (user, repo, run-id).

## Context Window & State
- Store transient context in memory by default; provide optional persistence via `DBAdapter` (store/restore by `session_id`).
- Keep context size bounded; implement trimming or summarization when context approaches provider token limits.

## Lifecyle
- `start_session(metadata) -> session_id`
- `append_context(session_id, message)`
- `get_context(session_id) -> list[Message]`
- `end_session(session_id)` (optional archival)

## Concurrency
- If multiple workers access the same session, use DB-backed locks or optimistic concurrency with versioning.

## Security & Privacy
- Redact or avoid storing secrets in session context. Provide hooks for redaction before persistence.
