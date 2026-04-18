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

## 3) 環境變數

先把 [`example.env`](example.env) 複製成 `.env`。

必填：

- `DISCORD_BOT_TOKEN`
- `ANTHROPIC_API_KEY` 或 `ANTHROPIC_AUTH_TOKEN` 二選一

常用選填變數：

| 變數 | 必填 | 預設值 | 說明 |
|---|---|---|---|
| `EMOJI_AGENT_MANIFEST` | 否 | `agents/agents.yaml` | emoji 路由清單路徑。 |
| `ANTHROPIC_BASE_URL` | 否 | 官方 Anthropic 端點 | 自訂 Claude 相容端點。 |
| `CLAUDE_MODEL` | 否 | SDK 預設值 | 所有路由的預設模型；若 `agents/agents.yaml` 有路由層級的 `model`，以路由設定為主。 |
| `CLAUDE_MAX_TURNS` | 否 | `4` | 每次 queue 執行允許的最大 Claude 回合數，至少要是 `1`。 |
| `AGENT_OUTPUTS_ROOT` | 否 | `/app/outputs` | agent 輸出根目錄。 |
| `LOG_LEVEL` | 否 | `INFO` | 應用程式記錄等級。 |
| `LOG_FORMAT` | 否 | `json` | Application log format. Supported values: `json` and `text`. Keep `json` in containers so Loki can parse logs reliably. |
| `DISCORD_LOG_LEVEL` | 否 | 與 `LOG_LEVEL` 相同 | `discord.py` 記錄器的記錄等級。 |
| `GRAFANA_ADMIN_USER` | 否 | `admin` | Grafana admin username for the bundled Docker Compose stack. |
| `GRAFANA_ADMIN_PASSWORD` | 否 | `admin` | Grafana admin password for the bundled Docker Compose stack. |

僅 `issue-whisperer` 會用到：

| 變數 | 必填 | 預設值 | 說明 |
|---|---|---|---|
| `GITLAB_TOKEN` | 否 | 無 | `issue-whisperer` 的 GitLab 唯讀 helper 會讀這個 token。 |
| `GITLAB_HOST` | 否 | 由 `git remote origin` 推導 | 當 repo remote 不存在，或不是 GitLab remote 時使用的備援 host。 |

## 4) 執行方式

### 本機執行

```bash
uv run python -m src.app
```

### 使用 Docker Compose 執行

先準備 `.env`：

```bash
cp example.env .env
```

接著編輯 `.env`，至少填入：

- `DISCORD_BOT_TOKEN`
- 你選擇的 Claude 驗證變數

如果要搭配 `compose.yaml` 內建的 `llm` 服務，一併設定：

- `ANTHROPIC_BASE_URL=http://llm:8080`
- `CLAUDE_MODEL=gemma-4-e4b`

其他設定通常維持預設值即可。

建立映像檔：

```bash
docker build -f Dockerfile -t emoji-trigger-agent:latest .
```

第一次執行前，先準備 `outputs/` 目錄：

```bash
mkdir -p outputs
chmod 777 outputs
```

啟動服務：

```bash
docker compose up --build -d
```

View bot container logs:

```bash
docker compose logs -f bot
```

Open Grafana:

- URL: `http://localhost:3000`
- Credentials: `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD`

Compose also starts:

- `loki`: stores container logs
- `alloy`: tails `bot` container logs from the Docker daemon and forwards them to Loki
- `grafana`: queries and visualizes Loki logs

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
  config.py             # 環境變數與設定
  agent_manifest.py     # agents.yaml 結構與驗證
  bot.py                # Discord 事件接收與 queue 寫入
  trigger_queue.py      # SQLite queue 儲存、claim/retry、背景 worker
  executor.py           # Claude 執行、prompt payload、輸出驗證

agents/
  agents.yaml           # 唯一的路由清單
  <agent-id>/
    AGENTS.md           # 該 agent 專屬的 Claude Code 專案說明
    .claude/
      agents/
        <agent-id>.md   # Claude agent 定義
      skills/
        <skill-id>/
          SKILL.md
          scripts/      # 預寫腳本 / 輔助檔案
    .mcp.json           # 選用

outputs/
  <agent-id>/
    ...agent 輸出...
```

## 7) 路由清單

路由清單由 `agents/agents.yaml` 統一管理。範例：

```yaml
version: 1
routes:
  - emoji: "📝"
    agent_id: "memo-agent"
```

`src/agent_manifest.py` 目前支援的欄位有：

- `emoji`
- `agent_id`
- `params`
- `model`
- `reasoning_effort`

原則：

- 路由要維持 declarative。
- 不要把 emoji 路由寫死在 `src/`。
- 如果多個 emoji 指向同一個 `agent_id`，它們的 `params`、`model`、`reasoning_effort` 必須一致，因為 queue 會把它們合併成同一個 execution target。
- 工具權限應該定義在 agent 專案設定，而不是路由清單。

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

## 11) Logs with Loki

The bundled Compose log pipeline is:

```text
bot stdout/stderr -> Docker container logs -> Grafana Alloy -> Loki -> Grafana
```

Design principles:

- Application logs default to one-line JSON so Loki and Grafana can query them cleanly
- The bot does not call the Loki API directly, which keeps application code decoupled from the log backend
- Alloy only collects logs from the `bot` service instead of forwarding every container in the Compose project
- The default `discord.py` logging handler is disabled to avoid duplicate output alongside the application's root logger

Common Grafana Explore query:

```logql
{app="emoji-trigger-agent", service="bot"}
```

To filter by JSON fields:

```logql
{app="emoji-trigger-agent", service="bot"} | json | event="queue.target.failed"
```

## 12) Troubleshooting

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
