# emoji-trigger-agent

使用 Python 3.13、`discord.py` 與 `claude-agent-sdk` 的 Discord emoji 觸發 bot。

這個專案刻意把「平台邏輯」和「agent 行為」拆成兩層：

- `src/`：負責 Discord 事件處理、設定、路由載入、SQLite queue、背景 worker、Claude 執行與輸出驗證
- `agents/`：負責每個 runtime Claude agent 的 Claude Code project 設定，例如 `AGENTS.md`、prompt、skills、scripts 與 MCP

這樣新增或調整某個 agent 時，通常只需要改 `agents/`，不必把 agent-specific 行為寫死進應用程式。

## 1) 架構總覽

### 目錄責任

| 目錄 | 角色 |
|---|---|
| `src/` | 應用程式 runtime 平台層。負責 Discord 事件 intake、manifest 載入、SQLite queue、背景 worker、Claude 執行、成功條件驗證。 |
| `agents/` | 宣告式 agent 層。每個 agent 都是獨立的 Claude Code project，具備自己的 `AGENTS.md`、agent markdown、skills、scripts、可選 MCP。 |
| `outputs/` | durable runtime outputs 與 queue database。host 端會 bind mount 到容器內 `/app/outputs`。 |

### `src/` 負責什麼

- 讀取環境變數與應用設定
- 從 `agents/agents.yaml` 載入 emoji route
- 接收 Discord 訊息與 reaction 事件，並先寫入 SQLite queue
- 以 `message_id + agent_id` 合併同一訊息上的多個 emoji trigger
- 由背景 worker 從 queue claim 工作後，再擷取已儲存的 Discord message context JSON 交給 Claude agent
- 驗證 agent 執行後，`/app/outputs/<agent-id>/` 底下是否真的有新檔案或檔案變更
- 只有在驗證通過後，才把成功 queue target 記錄輸出到 log

### `agents/` 負責什麼

- 宣告某個 emoji 要交給哪個 agent
- 讓每個 `agents/<agent-id>/` 都作為獨立 Claude Code project 維護
- 透過 agent-local `AGENTS.md` 說明這個 agent 的目標、限制、成功條件與 skill 佈局
- 定義 agent 的 system prompt / 行為目標
- 定義可重用的 skills
- 提供預寫好的 scripts，讓 agent 直接執行明確程式碼，而不是臨時生成腳本
- 定義 agent 專屬 MCP 設定（如果需要）

### 單次 trigger 流程

1. Discord 訊息或 reaction 事件進入 `src/bot.py`
2. `src/agent_manifest.py` 從 `agents/agents.yaml` 找到對應 route，並寫入 `/app/outputs/trigger_queue.sqlite3`
3. `src/trigger_queue.py` 依 `message_id + agent_id` 合併 target，保留完整 trigger audit events
4. 背景 worker claim 一個 pending target，組出合併後的 queue payload
5. `src/executor.py` 在 `agents/<agent-id>/` 作為 Claude `cwd` 執行 agent
6. agent 依自己的 `.claude/agents/*.md`、skills、scripts 決定並執行後續動作
7. `src/executor.py` 驗證 `/app/outputs/<agent-id>/` 是否真的有檔案變更
8. 驗證成功後才把 target 標記完成；失敗則依 retry 設定回到 pending 或 error

## 2) 安裝依賴

```bash
uv sync
```

專案已包含 `claude-agent-sdk` 依賴；Claude Code CLI 由套件內建，不需要另外安裝系統 CLI。

## 3) Environment Variables

`src.config.Settings` loads values from the process environment and from `.env` automatically.
For a complete template, start from [`example.env`](example.env).

Minimum required configuration:

- `DISCORD_BOT_TOKEN`
- one of `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN`

Available variables:

| Variable | Required | Default | Notes |
|---|---|---|---|
| `DISCORD_BOT_TOKEN` | Yes | none | Discord bot token from the Developer Portal. |
| `EMOJI_AGENT_MANIFEST` | No | `agents/agents.yaml` | Path to the runtime emoji routing manifest. |
| `ANTHROPIC_API_KEY` | Conditional | none | Standard Claude SDK API key. Use a real key for the official Anthropic API. Placeholder values such as `sk-temp` are only accepted when `ANTHROPIC_BASE_URL` points to a non-official endpoint. |
| `ANTHROPIC_AUTH_TOKEN` | Conditional | none | Bearer token for proxies or gateways that expect `Authorization: Bearer ...`. |
| `ANTHROPIC_BASE_URL` | No | official Anthropic endpoint | Optional custom Claude-compatible endpoint. Leave unset when talking directly to Anthropic. |
| `CLAUDE_MODEL` | No | SDK default | Default model for all routes. A route-level `model` in `agents/agents.yaml` still takes precedence. |
| `CLAUDE_MAX_TURNS` | No | `4` | Maximum Claude turns per queued execution. Must be at least `1`. |
| `AGENT_OUTPUTS_ROOT` | No | `/app/outputs` | Root directory for durable agent outputs. |
| `TRIGGER_QUEUE_DB_PATH` | No | `<AGENT_OUTPUTS_ROOT>/trigger_queue.sqlite3` | Optional explicit SQLite queue path. If unset, the app derives it from `AGENT_OUTPUTS_ROOT`. |
| `TRIGGER_QUEUE_WORKER_CONCURRENCY` | No | `1` | Number of background queue workers. Must be at least `1`. |
| `TRIGGER_QUEUE_POLL_INTERVAL_SECONDS` | No | `1.0` | Queue polling interval in seconds. Must be greater than `0`. |
| `TRIGGER_QUEUE_RETRY_COUNT` | No | `3` | Retry count after the first failed execution. Must be at least `1`. |
| `TRIGGER_QUEUE_RETRY_DELAY_SECONDS` | No | `30` | Delay between retries in seconds. Must be at least `1`. |
| `TRIGGER_QUEUE_CLAIM_TIMEOUT_SECONDS` | No | `900` | Lease timeout for recovering stuck `processing` jobs. Must be at least `1`. |
| `LOG_LEVEL` | No | `INFO` | Application log level. |
| `DISCORD_LOG_LEVEL` | No | same as `LOG_LEVEL` | Separate log level for the `discord.py` logger. |

Common setups:

Direct Anthropic API:

```bash
export DISCORD_BOT_TOKEN="your-discord-token"
export ANTHROPIC_API_KEY="your-real-anthropic-key"
```

Bearer-auth proxy or gateway:

```bash
export DISCORD_BOT_TOKEN="your-discord-token"
export ANTHROPIC_AUTH_TOKEN="your-gateway-bearer-token"
export ANTHROPIC_BASE_URL="https://your-gateway.example.com"
```

Local or self-hosted compatible endpoint:

```bash
export DISCORD_BOT_TOKEN="your-discord-token"
export ANTHROPIC_API_KEY="sk-temp"
export ANTHROPIC_BASE_URL="http://localhost:8080"
```

## 4) Run

### Run locally

```bash
uv run python -m src.app
```

### Run with Docker Compose

Prepare `.env` first:

```ini
DISCORD_BOT_TOKEN=your-discord-token
ANTHROPIC_API_KEY=sk-temp
ANTHROPIC_BASE_URL=http://llm:8080
CLAUDE_MODEL=gemma-4-e4b
CLAUDE_MAX_TURNS=4
AGENT_OUTPUTS_ROOT=/app/outputs
LOG_LEVEL=INFO
```

`TRIGGER_QUEUE_DB_PATH` usually does not need to be set explicitly because the app derives it as `/app/outputs/trigger_queue.sqlite3`.

Build the image:

```bash
docker build -f Dockerfile -t emoji-trigger-agent:latest .
```

Before the first run, prepare the `outputs/` directory:

```bash
mkdir -p outputs
chmod 777 outputs
```

Start the stack:

```bash
docker compose up --build -d
```

Follow the logs:

```bash
docker compose logs -f bot
```

## 5) Discord 必要設定

- 啟用 `MESSAGE CONTENT INTENT`
- Bot 需有 `Read Message History`
- Bot 需有 `Add Reactions`
- Bot 需有 `Read Messages/View Channels`

完整申請流程可參考 [docs/discord-setup.md](/home/phate/emoji-trigger-agent/docs/discord-setup.md)。

## 6) 專案固定結構

```text
src/
  app.py                # 啟動入口
  config.py             # env / settings
  agent_manifest.py     # agents.yaml schema 與驗證
  bot.py                # Discord 事件 intake 與 queue enqueue
  trigger_queue.py      # SQLite queue store、claim/retry、背景 worker
  executor.py           # Claude 執行、prompt payload、輸出驗證

agents/
  agents.yaml           # 唯一 runtime route manifest
  <agent-id>/
    AGENTS.md           # 該 agent 專屬的 Claude Code project 說明
    .claude/
      agents/
        <agent-id>.md   # Claude agent 定義
      skills/
        <skill-id>/
          SKILL.md
          scripts/      # 預寫 scripts / supporting files
    .mcp.json           # optional

outputs/
  <agent-id>/
    ...agent outputs...
```

## 7) Route Manifest

runtime routing 統一由 `agents/agents.yaml` 控制。基本範例：

```yaml
version: 1
routes:
  - emoji: "📝"
    agent_id: "memo-agent"
    allowed_tools:
      - "Read"
      - "Bash(bash .claude/skills/memo-headings/scripts/list_markdown_headings.sh *)"
      - "Bash(python3 .claude/skills/memo-write/scripts/write_channel_memo.py *)"
    disallowed_tools:
      - "Skill"
```

支援的欄位由 `src/agent_manifest.py` 解析，包含：

- `emoji`
- `agent_id`
- `params`
- `model`
- `reasoning_effort`
- `allowed_tools`
- `disallowed_tools`

原則：

- route 要保持 declarative
- 不要把 emoji routing 寫死在 `src/`
- 若某個 agent 需要限制 Claude 可用工具，放在 manifest，而不是寫死在 app code
- 若多個 emoji 指向同一個 `agent_id`，它們的 `params`、`model`、`reasoning_effort`、`allowed_tools`、`disallowed_tools` 必須一致，因為 queue 會把它們合併成同一個 execution target
- 對有 side effect 的 agent，優先把 `allowed_tools` 收斂到預寫 script 的固定 Bash 前綴，必要時連固定旗標一起限制

## 8) 建立新的 Agent

1. 在 `agents/agents.yaml` 加入 route
2. 建立 `agents/<agent-id>/`
3. 建立 `agents/<agent-id>/AGENTS.md`，把這個 agent 當成單一 Claude Code project 來描述目標、限制與 skill 佈局
4. 建立 `agents/<agent-id>/.claude/agents/<agent-id>.md`
5. 若需要 skill，建立 `agents/<agent-id>/.claude/skills/<skill-id>/SKILL.md`
6. 若需要 side effect script，放在 `agents/<agent-id>/.claude/skills/<skill-id>/scripts/`
7. 讓 agent 直接執行預寫 script，不要在 runtime 動態生成腳本
8. 讓 agent 的 durable output 落在 `/app/outputs/<agent-id>/`

建議判斷方式：

- 如果是所有 agent 都共用的能力，改 `src/`
- 如果只是某個 agent 的行為或輸出格式，改 `agents/`
- 如果某個規則只屬於單一 agent project，優先寫在該 agent 的 `AGENTS.md`

## 9) Memo Agent 範例

預設已提供 `📝 -> memo-agent`：

- 觸發方式：訊息內容包含 `📝`，或對訊息加上 `📝` reaction
- queue 規則：同一則訊息會以 `message_id + agent_id` 合併，同 emoji 重複 reaction 只留下 audit event，不會新增新的 target
- 行為：`src/` 會先把完整 Discord message context 存進 SQLite queue，再由 worker 把 queue payload 交給 `memo-agent`
- `memo-agent` 會先讀取目標 markdown 的 heading index，判斷要寫入哪個 `##` 主題段落
- 如果該主題段落已存在，`memo-agent` 會保留原章節內容，並把新的作者與原始訊息整理進同一章節
- 輸出會寫到 `/app/outputs/memo-agent/<channel-name>.md`

## 10) Outputs

`outputs/` 目前只放 agent 的 durable outputs：

- `outputs/<agent-id>/`：agent 的 durable outputs，例如 `memo-agent` 寫出的 markdown
- `outputs/trigger_queue.sqlite3`：SQLite trigger queue database

注意：

- queue 與 trigger audit event 會持久化到 SQLite
- 成功 target 會在 log 中留下紀錄
- 如果 Claude 只回了一句成功，但沒有實際檔案變更，現在會被視為失敗
- bot 重啟後，未完成或 lease 過期的 processing target 會回到 pending 繼續執行

## 11) Troubleshooting

若 Bot 已上線但沒有產生輸出，先檢查：

- emoji 是否與 `agents/agents.yaml` 完全一致
- Bot 是否有 `View Channels`、`Read Message History`、`Add Reactions`
- Developer Portal 的 `Message Content Intent` 是否已啟用
- `ANTHROPIC_API_KEY` 或 `ANTHROPIC_AUTH_TOKEN` 是否正確
- 若有設定 `ANTHROPIC_BASE_URL`，該 endpoint 是否接受你提供的 header
- host 端 `outputs/` 是否可寫
- `agents/<agent-id>/.claude/agents/<agent-id>.md` 是否存在
- `agents/<agent-id>/.claude/skills/...` 是否存在
- 若 bot 剛重啟過，要注意程序內去重狀態已清空

可提高 log 詳細度：

```bash
LOG_LEVEL=DEBUG DISCORD_LOG_LEVEL=DEBUG docker compose up --build -d
docker compose logs -f bot
```

如果你看到 log 顯示成功，但沒有 `outputs/<agent-id>/` 檔案，代表 app 的成功判定有 bug，這種情況不應再發生。

## 12) 補充文件

- [AGENTS.md](/home/phate/emoji-trigger-agent/AGENTS.md): 專案協作與目錄邊界
- [docs/discord-setup.md](/home/phate/emoji-trigger-agent/docs/discord-setup.md): Discord Bot 建立流程
