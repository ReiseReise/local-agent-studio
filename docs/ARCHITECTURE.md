# Architecture

## Product boundary

Local Agent Studio owns the Agent layer: model configuration, a published system prompt, knowledge ingestion/retrieval, output shaping, diagnostics and OpenAI-compatible HTTP responses. A connector such as Siver owns message reception, per-window history and final delivery.

```text
connector -> localhost API -> prompt + retrieval -> configured model -> plain-text response
browser   -> local admin UI -> configuration, publishing and diagnostics
```

The Agent never imports a WeChat automation package and never selects a chat or presses Send.

## Runtime data

Windows runtime state is rooted at `%LOCALAPPDATA%\LocalAgentStudio`:

- `data/studio.db`: configuration, version and metadata database;
- `data/uploads`: private source documents;
- `indexes`: rebuildable retrieval data;
- `logs`: metadata-only rotating logs;
- `backups`: explicit update backups;
- `secrets`: DPAPI-protected application material when a file envelope is required.

None of these directories belongs in Git or a synced project workspace.

## Request path

1. Verify loopback client and Bearer token.
2. Load the one active chat model and published prompt.
3. Remove connector-provided system prompts; preserve user/assistant history.
4. Retrieve enabled knowledge snippets, marking them as untrusted reference content.
5. Call the configured OpenAI-compatible provider with a bounded timeout and semaphore.
6. Return one plain-text response capped at 300 characters.
7. Persist only metadata such as request ID, status, latency and output length.

## Compatibility boundary

`/v1/chat/completions` implements the conventional message and choice envelope used by connector SDKs. `/v1/responses` implements the text subset needed as a fallback. Tool calls, audio, images, files, hosted state and background responses are intentionally unsupported.

Optional connector headers are accepted for trace correlation. When no stable conversation identifier is provided, Local Agent Studio remains stateless between requests and relies on the connector-provided message history.

Model calls do not inherit ambient operating-system proxy variables. This keeps loopback endpoints deterministic and avoids silently sending provider destinations through an unrelated local proxy. Explicit proxy profiles can be added in a later version if required.
