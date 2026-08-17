# Local Agent Studio Project Agent

## 使命与范围

- 交付一个可在 Windows 本机部署的单 Agent 服务，提供模型、提示词、知识库、调试台和 OpenAI 兼容接口。
- 本仓库是可公开代码真源；微信、Siver、wxautox4、联系人、聊天正文和激活信息不属于本仓库。
- 首版只做被动文字回答，不做商品推荐、工具调用、群发、支付、下单或主动营销。

## 当前真源

1. `README.md`：当前能力、安装方法、可用性和下一动作。
2. `docs/ARCHITECTURE.md`：数据边界、接口和运行结构。
3. Git、测试与 GitHub Actions：代码和验证证据。

## 特殊边界

- 生产仅允许绑定 `127.0.0.1`；不得默认开放局域网或公网。
- Windows 生产密钥只允许 DPAPI；失败不得回退到明文。
- 请求正文、知识正文、联系人和密钥不得写入日志、Git 或公开样例。
- 任何微信发送、第三方授权、外部发布和 GitHub 公开操作都需要 Reise 当次确认。
- 不引入、打包或分发 Siver、wxautox4 及其授权材料。

## 构建与验收

- 安装开发依赖：`python -m pip install -e .[dev]`
- 测试：`python -m pytest -q`
- 静态检查：`python scripts/check_public_repo.py`
- 本地启动：`python -m local_agent_studio serve --env development`
- 完成声明必须包含 Windows `install.ps1` 真机结果和浏览器关键旅程，不以 Mac 测试代替。

## 数据与交付

- Windows 运行数据固定进入 `%LOCALAPPDATA%\LocalAgentStudio`。
- 测试数据进入临时目录；仓库只保留虚构样例。
- 卸载默认保留数据；删除运行数据必须是单独、显式、可确认动作。
