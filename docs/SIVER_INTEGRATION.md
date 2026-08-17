# Siver integration

Local Agent Studio is the Agent endpoint; Siver remains the external message connector. This repository does not install, activate, automate, or redistribute Siver or wxautox4.

## Interface-only test

After Local Agent Studio shows ready, open its “接入配置” page and copy:

- Base URL: `http://127.0.0.1:8765/v1`
- Model: `local-agent-studio`
- API Key: the local connector token

In Siver, keep only a short instruction saying that the model endpoint owns the persona. Clear any “API failure fixed reply” field. Run Siver's model/interface test first. A passing interface test proves only HTTP compatibility; it does not prove that a WeChat message was received, routed to the correct window, or sent once.

## Do not enable automatic reply yet

The first live chat trial is a separate private-project gate. It starts with one explicitly chosen contact, human review, and a stop condition for any duplicate, wrong recipient, platform warning, validation dialog, or fixed fallback. No live-send instruction belongs in this public repository.
