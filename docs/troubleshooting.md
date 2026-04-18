# Troubleshooting

本文件收斂目前常見的執行問題與排查方向。

## Bot 有上線，但沒有產生輸出

先檢查：

- emoji 是否真的命中 `agents/agents.yaml`
- Discord bot 是否有 `View Channels`、`Read Message History`、`Add Reactions`
- `Message Content Intent` 是否已開啟
- `ANTHROPIC_API_KEY` 或 `ANTHROPIC_AUTH_TOKEN` 是否正確
- 若有設定 `ANTHROPIC_BASE_URL`，該 endpoint 是否可用
- host 端 `outputs/` 是否可寫
- 目標 agent 是否存在 `agents/<agent-id>/.claude/agents/<agent-id>.md`
- 目標 agent 是否真的把 durable output 寫進 `outputs/<agent-id>/`

## 提高 log 詳細度

```bash
LOG_LEVEL=DEBUG DISCORD_LOG_LEVEL=DEBUG docker compose up --build -d
docker compose logs -f bot
```

## Loki `http://localhost:3100/` 回 404

這是正常的。

Loki 主要提供 API，不是從根路徑提供操作介面。請改用：

- `http://localhost:3100/ready`
- `http://localhost:3100/loki/api/v1/status/buildinfo`

平常查 log 應該走 Grafana，而不是直接打 Loki root URL。

## Docker 打包很慢或像卡住

在 WSL2 + Docker 環境下，`claude-agent-sdk` wheel 下載可能在預設 build network 下非常慢。

目前 repo 已在 `compose.yaml` 中對 bot build 啟用 host build network，正常情況下直接跑：

```bash
docker compose up --build
```

就會吃到這個設定。
