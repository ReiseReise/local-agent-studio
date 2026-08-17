# OpenAI-compatible API

All inference endpoints require `Authorization: Bearer <local connector token>`. The token is generated after first setup and shown only in the authenticated local admin UI.

## Chat Completions

`POST /v1/chat/completions` accepts a text-only message list and optional `stream`. The public connector model name is always `local-agent-studio`; provider-specific model settings remain private to the admin configuration.

```json
{
  "model": "local-agent-studio",
  "messages": [{"role": "user", "content": "你好"}],
  "stream": false
}
```

Streaming uses Server-Sent Events and terminates with `data: [DONE]`.

## Responses

`POST /v1/responses` implements a minimal text-only compatibility subset. String input and role/content items are accepted. Hosted state, tools, files, images, audio, background execution and function calls are unsupported.

## Connector metadata

The following optional headers are hashed before metadata storage and never used as a cross-contact memory store:

- `X-Connector-ID`
- `X-Conversation-ID`
- `X-Message-ID`
- `X-Turn-ID`

Without a stable conversation ID, the service uses only the message history supplied in the current request. It does not infer or persist a contact identity.

## Errors

Errors never contain a fabricated assistant reply:

```json
{"error": {"code": "upstream_timeout"}}
```

`GET /healthz` means only that the process is alive. `GET /readyz` additionally checks setup, Agent state, active chat model, published prompt and enabled knowledge indexing state.
