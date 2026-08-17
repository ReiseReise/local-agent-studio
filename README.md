# Local Agent Studio

一个运行在 Windows 本机的可配置 AI Agent：在浏览器里管理模型、提示词和知识库，并通过 OpenAI 兼容接口连接 Siver 或其他聊天接入层。

> 当前状态：`0.1.0-alpha`。Windows 11 虚拟机中的核心安装、启停和基础 Agent 功能已经跑通；Siver 接口和真实联系人试运行仍必须分别验收。

## 当前阶段

| 里程碑 | 状态 | 证据边界 |
|---|---|---|
| M0 独立项目 | 已完成 | 独立源码、Apache-2.0、项目登记和发布边界已建立 |
| M1 基础服务 | Windows 已部署，基础功能已跑通 | 数据库迁移、模型配置、密钥保护和健康检查已自动测试，用户已确认基础 Agent 功能可用 |
| M2 提示词与知识库 | 开发验证通过 | 发布/回滚、增量索引、中文检索和浏览器关键旅程已验证 |
| M3 标准接口 | 开发验证通过 | Chat Completions、Responses、SSE、鉴权和 10 路并发测试通过 |
| M4 Windows 部署 | 核心流程已验证 | Windows 11 VM 已完成安装、DPAPI 初始化、启动、重复启动防护、停止和重启；更新与卸载留到发布候选验收 |
| M5 微信试运行 | 未开始 | 属于私人 I12 项目，开始前再次确认，不在本仓库执行 |
| M6 GitHub 发布 | 源码已公开 | [ReiseReise/local-agent-studio](https://github.com/ReiseReise/local-agent-studio) 已建立并推送 `main`；正式 Release、SBOM 和全新物理 Windows 验收尚未进行 |

## 它解决什么

```text
聊天接入层（例如 Siver）
          ↓  OpenAI-compatible API
Local Agent Studio
          ├─ 已发布提示词
          ├─ 本地知识库
          └─ 你配置的模型 API
```

Local Agent Studio 不控制微信，也不包含、安装或分发 Siver、wxautox4。它只提供独立 Agent 服务。

## 第一版能力

- 浏览器本地后台：状态、模型、提示词、知识库、调试台、接入配置、系统诊断；
- 多个 OpenAI 兼容模型配置，一个主聊天模型和一个可选 Embedding 模型；
- 提示词草稿、发布、版本和回滚；
- Markdown、TXT、PDF、DOCX 与在线文本知识；
- SQLite FTS5 检索，可选 Embedding 语义重排；
- `POST /v1/chat/completions`、`POST /v1/responses`；
- Windows DPAPI 密钥保护、只监听本机、正文不进日志。

## Windows 快速开始

前置条件：Windows 11、Python 3.12 x64。

```powershell
git clone https://github.com/ReiseReise/local-agent-studio.git
cd local-agent-studio
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

然后访问 <http://127.0.0.1:8765/admin/setup> 完成首次设置。

运行数据位于 `%LOCALAPPDATA%\LocalAgentStudio`，不会写进仓库。卸载默认保留这些数据。

## 现在怎么用

1. 在 Windows 浏览器打开 <http://127.0.0.1:8765/admin/setup>，由你本人设置至少 12 位的后台密码；
2. 在“模型”中新增一个 OpenAI 兼容模型，先点连接测试，再设为当前模型；
3. 在“提示词”中编辑人设，测试满意后发布；草稿不会影响对外回答；
4. 在“知识库”中上传或新建资料，等待状态变成可检索；
5. 先在“调试台”连续检查回答和召回来源；
6. 最后才在“接入配置”复制 URL、模型名和本机 Token 给 Siver。

不要在聊天中发送后台密码、模型 API Key 或本机 Token。首次设置未完成时，`/readyz` 返回 503 是正常的安全状态。

## 2026-08-17 Windows 验证证据

- Windows 11、Python 3.12 x64：`install.ps1` 退出码 0；
- 运行数据写入当前 Windows 用户的 `%LOCALAPPDATA%\LocalAgentStudio`，DPAPI 会话密钥初始化成功；
- `healthz` 返回 200，未设置模型和已发布提示词时 `readyz` 按设计返回 503；
- 仅监听 `127.0.0.1:8765`；重复执行启动脚本不会产生第二个服务进程；
- `stop.ps1` 正常释放端口，随后重新启动成功；
- 同一候选源码在 Windows 上通过 Ruff、11 项自动测试和公开仓库扫描；后台会把未设当前模型、API Key 无效、余额不足、限流和超时等常见故障直接显示为中文操作提示；
- Windows 当前配置的 Agent、聊天模型、已发布提示词和知识库健康检查均已就绪；用户已确认基础功能跑通。本轮仍未把 Siver 调用或微信真实发送计入完成证据。

本轮没有验证真实模型密钥、Siver 调用、微信发送、更新脚本、卸载脚本或物理 Windows 主机。Parallels 暂停虚拟机时，本机 API 也会暂停；常驻使用前应关闭虚拟机的自动暂停策略。

## Siver 配置

完成后台首次设置后，在“接入配置”页面复制：

- URL：`http://127.0.0.1:8765/v1`
- Model：`local-agent-studio`
- API Key：后台生成的本机 Token

正式使用前必须在 Siver 中清空“接口错误固定回复”，并先使用它的接口测试，不直接打开微信自动回复。

## 开发

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/python -m local_agent_studio serve --env development
```

生产默认拒绝在非 Windows 系统启动；开发模式需要显式设置本地开发密钥。

## 隐私与安全

- 默认绑定 `127.0.0.1`，不开放局域网和公网；
- Windows 生产密钥仅使用 DPAPI；
- 不记录聊天正文、知识正文或 API Key；
- 不提供工具调用、支付、下单、群发、主动营销；
- 不包含任何微信自动化框架、激活码或私人聊天样例。

详见 [架构与边界](docs/ARCHITECTURE.md) 和 [安全策略](SECURITY.md)。

进一步阅读：[Windows 部署](docs/WINDOWS_DEPLOYMENT.md) · [Siver 接入](docs/SIVER_INTEGRATION.md) · [公开发布检查表](docs/RELEASE_CHECKLIST.md)

## English quick start

Local Agent Studio is a Windows-local, configurable RAG agent with an OpenAI-compatible API. It owns prompts, knowledge retrieval, model configuration and a local admin UI; chat connectors remain separate. Install with `scripts/install.ps1`, start with `scripts/start.ps1`, then open `http://127.0.0.1:8765/admin/setup`.

## License

Apache-2.0. Third-party components keep their own licenses; see `THIRD_PARTY_NOTICES.md`.
