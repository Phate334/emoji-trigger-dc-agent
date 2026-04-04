# emoji-trigger-agent

使用 Python 3.13、`discord.py` 與 `claude-agent-sdk` 的 Discord emoji 觸發 bot。

這個專案刻意把「平台邏輯」和「agent 行為」拆成兩層：

- `src/`：負責 Discord 事件處理、設定、路由載入、程序內去重、Claude 執行與輸出驗證
- `agents/`：負責每個 runtime Claude agent 的 Claude Code project 設定，例如 `AGENTS.md`、prompt、skills、scripts 與 MCP

這樣新增或調整某個 agent 時，通常只需要改 `agents/`，不必把 agent-specific 行為寫死進應用程式。

## 1) 架構總覽

### 目錄責任

| 目錄 | 角色 |
|---|---|
| `src/` | 應用程式 runtime 平台層。負責 Discord 事件 intake、manifest 載入、程序內去重、Claude 執行、成功條件驗證。 |
| `agents/` | 宣告式 agent 層。每個 agent 都是獨立的 Claude Code project，具備自己的 `AGENTS.md`、agent markdown、skills、scripts、可選 MCP。 |
| `outputs/` | durable runtime outputs。host 端會 bind mount 到容器內 `/app/outputs`。 |

### `src/` 負責什麼

- 讀取環境變數與應用設定
- 從 `agents/agents.yaml` 載入 emoji route
- 接收 Discord 訊息與 reaction 事件
- 擷取完整 Discord message context 並轉成 JSON 交給 Claude agent
- 以 `message_id + emoji` 做程序內成功去重
- 驗證 agent 執行後，`/app/outputs/<agent-id>/` 底下是否真的有新檔案或檔案變更
- 只有在驗證通過後，才把成功 trigger 記錄輸出到 debug log

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
2. `src/agent_manifest.py` 從 `agents/agents.yaml` 找到對應 route
3. `src/bot.py` 檢查這個 `message_id + emoji` 是否已成功處理過
4. `src/executor.py` 建立完整 JSON context，並在 `agents/<agent-id>/` 作為 Claude `cwd` 執行 agent
5. agent 依自己的 `.claude/agents/*.md`、skills、scripts 決定並執行後續動作
6. `src/executor.py` 驗證 `/app/outputs/<agent-id>/` 是否真的有檔案變更
7. 驗證成功後才輸出成功 trigger 的 debug log

## 2) 安裝依賴

```bash
uv sync
```

專案已包含 `claude-agent-sdk` 依賴；Claude Code CLI 由套件內建，不需要另外安裝系統 CLI。

## 3) 設定環境變數

至少提供一種 Claude 驗證方式：

- `ANTHROPIC_API_KEY`
- `ANTHROPIC_AUTH_TOKEN`

直連 Anthropic：

```bash
export DISCORD_BOT_TOKEN="你的 token"
export ANTHROPIC_API_KEY="你的 anthropic key"
```

走 bearer token 的 proxy / gateway：

```bash
export DISCORD_BOT_TOKEN="你的 token"
export ANTHROPIC_AUTH_TOKEN="你的 gateway bearer token"
export ANTHROPIC_BASE_URL="https://your-gateway.example.com"
```

走本機相容 endpoint：

```bash
export ANTHROPIC_API_KEY="sk-temp"
export ANTHROPIC_BASE_URL="http://localhost:8080"
```

可選設定：

```bash
export CLAUDE_MODEL="claude-sonnet-4-5"
export CLAUDE_MAX_TURNS="4"
export AGENT_OUTPUTS_ROOT="/app/outputs"
export EMOJI_AGENT_MANIFEST="agents/agents.yaml"
```

## 4) 啟動

### 本機啟動

```bash
uv run python -m src.app
```

### Docker / Compose 啟動

先準備 `.env`：

```ini
DISCORD_BOT_TOKEN=你的 token
ANTHROPIC_API_KEY=sk-temp
ANTHROPIC_BASE_URL=http://llm:8080
CLAUDE_MODEL=gemma-4-26b-a4b
CLAUDE_MAX_TURNS=4
AGENT_OUTPUTS_ROOT=/app/outputs
```

建置映像：

```bash
docker build -f Dockerfile -t emoji-trigger-agent:latest .
```

首次啟動前先準備 outputs 目錄：

```bash
mkdir -p outputs
chmod 777 outputs
```

啟動：

```bash
docker compose up --build -d
```

查看 log：

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
  bot.py                # Discord 事件 intake 與程序內去重
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
- 去重規則：同一則訊息的同一個 emoji 在同一次 bot 執行期間只會成功觸發一次
- 行為：`src/` 會把完整 Discord message context 交給 `memo-agent`
- `memo-agent` 會先讀取目標 markdown 的 heading index，判斷要寫入哪個 `##` 主題段落
- 如果該主題段落已存在，`memo-agent` 會保留原章節內容，並把新的作者與原始訊息整理進同一章節
- 輸出會寫到 `/app/outputs/memo-agent/<channel-name>.md`

## 10) Outputs

`outputs/` 目前只放 agent 的 durable outputs：

- `outputs/<agent-id>/`：agent 的 durable outputs，例如 `memo-agent` 寫出的 markdown

注意：

- app 不再把去重狀態寫入磁碟
- 成功 trigger 只會在 debug log 中留下紀錄
- 如果 Claude 只回了一句成功，但沒有實際檔案變更，現在會被視為失敗
- bot 重啟後，程序內的成功去重狀態會清空

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
