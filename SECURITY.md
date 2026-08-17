# Security policy

## Supported versions

Only the latest tagged `0.x` release receives security fixes while the project is pre-1.0.

## Report a vulnerability

Do not place API keys, private prompts, knowledge documents, chat content or exploit details in a public issue. Use GitHub private vulnerability reporting after the public repository enables it.

## Security boundary

- The production server binds only to `127.0.0.1`.
- Windows production secrets use DPAPI. Encryption failure stops startup or the affected operation.
- Request and response bodies are excluded from application logs.
- Uploaded files are allowlisted and size-limited.
- The first release has no tools, browsing, shell, payment, ordering or autonomous external actions.
- Siver, wxautox4 and WeChat are external to this repository and retain their own risks and terms.
