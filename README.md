# emoji-trigger-agent

使用 Python 3.13 + uv + discord.py 的 emoji 觸發 Discord bot。

此版本使用單一設定檔 `codex/agents/agents.yaml` 管理 emoji 到 sub-agent 的對應。

## 1) 安裝依賴

```bash
uv sync
```

若要啟用 `mode: codex_turn`，需另外安裝 Codex Python SDK（目前官方示例為從 Codex repo 的 `sdk/python` 以 editable 方式安裝）。

## 2) 設定 Bot Token

```bash
export DISCORD_BOT_TOKEN="你的 token"
```

可選：覆蓋 manifest 路徑

```bash
export EMOJI_AGENT_MANIFEST="codex/agents/agents.yaml"
```

## 3) 啟動

```bash
uv run python -m src.app
```

## 3-1) Docker 啟動（uv 兩階段打包）

先建立 `.env` 並放入 Token：

```bash
DISCORD_BOT_TOKEN=你的 token
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

- 啟用 `MESSAGE CONTENT INTENT`
- Bot 需有讀取訊息、發送訊息、讀取歷史、reaction 權限

## 5) 固定目錄規約

- `AGENTS.md`: 專案層級協作與規約說明
- `codex/agents/agents.yaml`: 唯一執行期路由與 agent 註冊設定
- `codex/agents/<agent-id>/AGENTS.md`: sub-agent instructions
- `codex/skills/<skill-id>/SKILL.md`: 可重用 skills
- `codex/mcp/<profile-id>.toml`: MCP profiles

## 6) memo 範例

預設已提供 `📝` 對應 `memo-agent`：

- 觸發方式：訊息包含 `📝`，或對訊息加上 `📝` reaction
- 行為：把原始訊息內容 append 到 `runtime/memo.txt`
- 回覆：`Memo saved.`

注意：Bot 不會對「任意 emoji」觸發，只有 `codex/agents/agents.yaml` 內有設定的 emoji 才會觸發。

## 8) Troubleshooting 與 Debug Log

若 Bot 已上線但沒有觸發，先確認：

- 送出的 emoji 是否與 `codex/agents/agents.yaml` 完全一致（預設只有 `📝`）
- Bot 在該頻道是否具備 `View Channels`、`Send Messages`、`Read Message History`、`Add Reactions`
- Developer Portal 的 `Message Content Intent` 是否已開啟

可透過環境變數提高 log 詳細度：

```bash
LOG_LEVEL=DEBUG DISCORD_LOG_LEVEL=DEBUG docker compose up --build -d
docker compose logs -f bot
```

如果使用 `.env`，可加入：

```ini
LOG_LEVEL=DEBUG
DISCORD_LOG_LEVEL=DEBUG
```

範例 `codex/agents/agents.yaml`：

```yaml
version: 1
routes:
	- emoji: "📝"
		agent_id: "memo-agent"
		instructions_path: "agents/memo-agent/AGENTS.md"
		mode: "memo_append"
		output_file: "runtime/memo.txt"
		response_text: "Memo saved."
```

## 7) 新增一個 sub-agent

1. 新增 `codex/agents/<agent-id>/AGENTS.md`
2. 在 `codex/agents/agents.yaml` 增加一條 route
3. 如果需要，新增 `codex/skills/<skill-id>/SKILL.md`
4. 如果需要，新增 `codex/mcp/<profile-id>.toml`
