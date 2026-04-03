# emoji-trigger-agent

使用 Python 3.13 + uv + discord.py 的 emoji 觸發 Discord bot。

此版本使用單一設定檔 `agents/agents.yaml` 管理 emoji 到 runtime agent 的對應。每個被觸發的 agent 都有自己的工作目錄 `agents/<agent-id>/`，並且只載入該目錄下的 Claude project `.claude` 設定，避免與專案開發時使用的全域或 repo-level agent 設定互相干擾。

## 1) 安裝依賴

```bash
uv sync
```

專案已內建 claude-agent-sdk 依賴，Claude Code CLI 由套件內建，不需額外安裝系統 CLI。

## 2) 設定環境變數

至少提供一種 Claude 驗證方式：

- `ANTHROPIC_API_KEY`: 官方 Anthropic API / Claude Agent SDK 標準設定，會走 `X-Api-Key`
- `ANTHROPIC_AUTH_TOKEN`: Claude Code 的替代設定，會走 `Authorization: Bearer ...`，適合 proxy / gateway

直連 Anthropic 官方 API：

```bash
export DISCORD_BOT_TOKEN="你的 token"
export ANTHROPIC_API_KEY="你的 anthropic key"
```

如果是走需要 bearer token 的 proxy / gateway，請改用：

```bash
export DISCORD_BOT_TOKEN="你的 token"
export ANTHROPIC_AUTH_TOKEN="你的 gateway bearer token"
export ANTHROPIC_BASE_URL="https://your-gateway.example.com"
```

如果不是直接連 Anthropic，而是走本機 LLM endpoint 或相容 proxy，可設定：

```bash
export ANTHROPIC_API_KEY="sk-temp"
export ANTHROPIC_BASE_URL="http://localhost:8080"
```

只要 `ANTHROPIC_BASE_URL` 指向自訂 endpoint，`ANTHROPIC_API_KEY` 或 `ANTHROPIC_AUTH_TOKEN` 擇一提供即可，實際要用哪個取決於該 endpoint 期待哪種 header。

可選：指定預設模型 ID（所有 route 共用，若 route 有設定 model 會覆蓋）

```bash
export CLAUDE_MODEL="claude-sonnet-4-5"
```

可選：覆蓋 manifest 路徑

```bash
export EMOJI_AGENT_MANIFEST="agents/agents.yaml"
```

## 3) 啟動

```bash
uv run python -m src.app
```

## 3-1) Docker 啟動（uv 兩階段打包）

先建立 .env：

```bash
DISCORD_BOT_TOKEN=你的 token
ANTHROPIC_API_KEY=sk-temp
ANTHROPIC_BASE_URL=http://llm:8080
CLAUDE_MODEL=gemma-4-26b-a4b
```

若要直連 Anthropic，則把 `ANTHROPIC_BASE_URL` 拿掉，並將 `ANTHROPIC_API_KEY` 換成真實金鑰。

若要接需要 bearer token 的 gateway，則可改成：

```bash
DISCORD_BOT_TOKEN=你的 token
ANTHROPIC_AUTH_TOKEN=你的 gateway bearer token
ANTHROPIC_BASE_URL=https://your-gateway.example.com
CLAUDE_MODEL=你的模型名稱
```

建置映像：

```bash
docker build -f Dockerfile -t emoji-trigger-agent:latest .
```

使用 compose 啟動：

```bash
docker compose up --build -d
```

查看 log：

```bash
docker compose logs -f bot
```

## 4) Discord 必要設定

- 啟用 MESSAGE CONTENT INTENT
- Bot 需有讀取訊息、讀取歷史、reaction 權限

## 5) 固定目錄規約

- AGENTS.md: 專案層級協作與規約說明
- agents/agents.yaml: 唯一執行期 emoji route 設定
- agents/{agent-id}/: 單一 runtime agent 的專屬工作目錄，Claude SDK 執行時會將 `cwd` 指向這裡
- agents/{agent-id}/.claude/agents/{agent-id}.md: Claude Code filesystem-based agent 定義
- agents/{agent-id}/.claude/skills/{skill-id}/SKILL.md: 該 agent 專屬或共置的 skills
- agents/{agent-id}/.mcp.json: 該 agent 專屬 MCP 設定（若需要）

說明：

- 專案根目錄不使用 repo-level `.claude/` 來存放這些被 emoji 觸發的 runtime agent 設定
- 執行時會將 Claude SDK 的 `cwd` 指向 `agents/{agent-id}/`
- 並且只載入該 agent 目錄的 project 設定，確保不同 agent 間的 skills、MCP 與 agent 定義彼此隔離

## 6) 建立新的 emoji agent

1. 在 `agents/agents.yaml` 加入新的 route：

```yaml
routes:
  - emoji: "📝"
    agent_id: "memo-agent"
    params:
      output_file: "claude/runtime/memo.txt"
```

2. 建立對應的 agent 工作目錄：

```text
agents/
  memo-agent/
    .claude/
      agents/
        memo-agent.md
      skills/
        memo-write/
          SKILL.md
    .mcp.json   # optional
```

3. 在 `agents/<agent-id>/.claude/agents/<agent-id>.md` 中建立 Claude Code agent 定義。

注意：

- `agent_id` 會同時用在 manifest、目錄名稱，以及 agent markdown frontmatter 的 `name`
- Claude Code subagent 的 `name` 需使用小寫加連字號，例如 `memo-agent`
- 若要讓 agent 使用 project skills，skill 需放在該 agent 工作目錄底下的 `.claude/skills/`
- 若要讓 agent 使用 project MCP，自訂 MCP 設定請放在該 agent 工作目錄底下的 `.mcp.json`

## 7) memo 範例

預設已提供 📝 對應 `memo-agent`：

- 觸發方式：訊息包含 📝，或對訊息加上 📝 reaction
- 行為：`memo-agent` 會在 `agents/memo-agent/` 作為 `cwd` 執行，並依照其 `.claude` 內容與 skill 寫入 `claude/runtime/memo.txt`
- 回覆：bot 不會自動回傳完成訊息到頻道

注意：Bot 不會對任意 emoji 觸發，只有 `agents/agents.yaml` 內有設定的 emoji 才會觸發。

## 8) Troubleshooting 與 Debug Log

若 Bot 已上線但沒有觸發，先確認：

- 送出的 emoji 是否與 `agents/agents.yaml` 完全一致（預設只有 📝）
- Bot 在該頻道是否具備 View Channels、Read Message History、Add Reactions
- Developer Portal 的 Message Content Intent 是否已開啟
- 環境中是否正確提供 `ANTHROPIC_API_KEY` 或 `ANTHROPIC_AUTH_TOKEN`
- 若有設定 `ANTHROPIC_BASE_URL`，該 endpoint 是否真的接受你選的驗證 header
- 對應的 agent 目錄下是否存在 `agents/{agent-id}/.claude/agents/{agent-id}.md`

可透過環境變數提高 log 詳細度：

```bash
LOG_LEVEL=DEBUG DISCORD_LOG_LEVEL=DEBUG docker compose up --build -d
docker compose logs -f bot
```

如果使用 .env，可加入：

```ini
LOG_LEVEL=DEBUG
DISCORD_LOG_LEVEL=DEBUG
```
