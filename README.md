# emoji-trigger-agent

`emoji-trigger-agent` 是一個 Discord bot，會把訊息內容或 reaction 轉成排隊執行的 Claude workflow。

這個專案刻意把責任拆成三層：

- `src/`：共用 runtime，負責 Discord intake、queue、worker、Claude 執行與結果驗證
- `agents/`：各個 agent 的宣告式設定、prompt、skills、scripts
- `outputs/`：durable outputs 與 SQLite queue 狀態

系統只會在 agent 真的改動 `outputs/` 底下檔案時，才把這次 trigger 視為成功。

## 快速開始

安裝依賴：

```bash
uv sync
```

建立環境變數：

```bash
cp example.env .env
```

至少要設定：

- `DISCORD_BOT_TOKEN`
- `ANTHROPIC_API_KEY` 或 `ANTHROPIC_AUTH_TOKEN`

本機執行：

```bash
uv run python -m src.app
```

用 Docker Compose 啟動整套服務：

```bash
mkdir -p outputs
chmod 777 outputs
docker compose up --build -d
```

常用指令：

```bash
docker compose logs -f bot
docker compose ps
```

Grafana 預設位置：

- `http://localhost:3000`

## 目前內建服務

`compose.yaml` 目前會啟動：

- `bot`
- `llm`
- `loki`
- `alloy`
- `grafana`

其中 `bot` 的 log 會經過 `alloy -> loki -> grafana` 這條管線。

## 你會先想知道的事

- 路由清單只看 `agents/agents.yaml`
- queue 狀態存放在 `outputs/trigger_queue.sqlite3`
- durable outputs 會寫到 `outputs/<agent-id>/`
- 在 WSL2 環境下，bot image build 會使用 host build network，避免大 wheel 下載卡住

## 文件導覽

- [docs/deployment.md](docs/deployment.md)
  說明環境變數、本機執行、Docker Compose 與部署注意事項。

- [docs/architecture.md](docs/architecture.md)
  說明系統分層、trigger 流程、route 規則，以及如何新增 agent。

- [docs/observability.md](docs/observability.md)
  說明 Loki / Grafana / Alloy 的 log pipeline、常用查詢與 dashboard。

- [docs/troubleshooting.md](docs/troubleshooting.md)
  收斂常見故障排查，包含沒有輸出、權限不足、Loki `404` 等情況。

- [docs/discord-setup.md](docs/discord-setup.md)
  Discord Bot Application 建立與權限設定流程。

- [AGENTS.md](AGENTS.md)
  專案協作規範與目錄邊界。
