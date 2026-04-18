# 部署與執行

本文件整理 `emoji-trigger-agent` 的執行方式、常用環境變數，以及 Docker Compose 相關注意事項。

## 環境需求

- Python `3.13`
- `uv`
- Discord Bot Token
- `ANTHROPIC_API_KEY` 或 `ANTHROPIC_AUTH_TOKEN`

## 安裝依賴

```bash
uv sync
```

專案已包含 `claude-agent-sdk`，不需要另外安裝系統層的 Claude CLI。

## 環境變數

先複製：

```bash
cp example.env .env
```

最少要設定：

- `DISCORD_BOT_TOKEN`
- `ANTHROPIC_API_KEY` 或 `ANTHROPIC_AUTH_TOKEN`

常用變數如下：

| 變數 | 預設值 | 說明 |
|---|---|---|
| `EMOJI_AGENT_MANIFEST` | `agents/agents.yaml` | route manifest 路徑。 |
| `CLAUDE_MODEL` | SDK 預設值 | route 沒有指定 `model` 時的預設模型。 |
| `CLAUDE_MAX_TURNS` | `4` | 單次執行允許的最大 Claude 回合數。 |
| `AGENT_OUTPUTS_ROOT` | `/app/outputs` | durable outputs 根目錄。 |
| `LOG_LEVEL` | `INFO` | 應用程式 log level。 |
| `LOG_FORMAT` | `json` | log 格式，支援 `json` 與 `text`。容器環境建議用 `json`。 |
| `DISCORD_LOG_LEVEL` | 跟 `LOG_LEVEL` 相同 | `discord.py` logger level。 |
| `ANTHROPIC_BASE_URL` | 官方 Anthropic endpoint | 自訂 Claude 相容 endpoint。 |
| `GRAFANA_ADMIN_USER` | `admin` | Grafana 管理帳號。 |
| `GRAFANA_ADMIN_PASSWORD` | `admin` | Grafana 管理密碼。 |

`issue-whisperer` 另外會用到：

| 變數 | 預設值 | 說明 |
|---|---|---|
| `GITLAB_TOKEN` | 無 | GitLab helper script 使用的 token。 |
| `GITLAB_HOST` | 從 `git remote origin` 推導 | 無法從 remote 推導時的備援 GitLab host。 |

## 本機執行

```bash
uv run python -m src.app
```

## Docker Compose 執行

第一次執行前先準備 `outputs/`：

```bash
mkdir -p outputs
chmod 777 outputs
```

啟動：

```bash
docker compose up --build -d
```

查看 bot log：

```bash
docker compose logs -f bot
```

查看服務狀態：

```bash
docker compose ps
```

## Compose 內建服務

`compose.yaml` 目前包含：

- `bot`
- `llm`
- `loki`
- `alloy`
- `grafana`

## WSL2 打包注意事項

在 WSL2 + Docker 環境下，`claude-agent-sdk` 的大 wheel 下載有機會在預設 bridge build network 下非常慢。

因此目前 `compose.yaml` 的 bot build 會使用 host build network。這是為了讓：

```bash
docker compose up --build
```

在這個環境下能穩定完成，不需要額外手動補參數。
