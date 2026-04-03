# emoji-trigger-agent

使用 Python 3.13 + uv + discord.py 的 emoji 觸發 Discord bot。

此版本使用單一設定檔 claude/agents/agents.yaml 管理 emoji 到 sub-agent 的對應，並且所有 route 一律透過 Claude Code SDK agent 執行（不再使用 mode 欄位）。

## 1) 安裝依賴

```bash
uv sync
```

專案已內建 claude-agent-sdk 依賴，Claude Code CLI 由套件內建，不需額外安裝系統 CLI。

## 2) 設定環境變數

```bash
export DISCORD_BOT_TOKEN="你的 token"
export ANTHROPIC_API_KEY="你的 anthropic key"
```

可選：指定預設模型 ID（所有 route 共用，若 route 有設定 model 會覆蓋）

```bash
export CLAUDE_MODEL="claude-sonnet-4-5"
```

可選：覆蓋 manifest 路徑

```bash
export EMOJI_AGENT_MANIFEST="claude/agents/agents.yaml"
```

## 3) 啟動

```bash
uv run python -m src.app
```

## 3-1) Docker 啟動（uv 兩階段打包）

先建立 .env：

```bash
DISCORD_BOT_TOKEN=你的 token
ANTHROPIC_API_KEY=你的 anthropic key
CLAUDE_MODEL=claude-sonnet-4-5
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
- claude/agents/agents.yaml: 唯一執行期路由與 agent 註冊設定
- claude/agents/{agent-id}/AGENTS.md: sub-agent instructions
- claude/skills/{skill-id}/SKILL.md: 可重用 skills
- claude/mcp/{profile-id}.toml: MCP profiles

## 6) memo 範例

預設已提供 📝 對應 memo-agent：

- 觸發方式：訊息包含 📝，或對訊息加上 📝 reaction
- 行為：memo-agent 依照 AGENTS.md + skill 寫入 runtime/memo.txt
- 回覆：bot 不會自動回傳完成訊息到頻道

注意：Bot 不會對任意 emoji 觸發，只有 claude/agents/agents.yaml 內有設定的 emoji 才會觸發。

## 7) Troubleshooting 與 Debug Log

若 Bot 已上線但沒有觸發，先確認：

- 送出的 emoji 是否與 claude/agents/agents.yaml 完全一致（預設只有 📝）
- Bot 在該頻道是否具備 View Channels、Read Message History、Add Reactions
- Developer Portal 的 Message Content Intent 是否已開啟
- 環境中是否正確提供 ANTHROPIC_API_KEY

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
