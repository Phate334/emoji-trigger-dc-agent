# 可觀測性與 Log 查詢

本文件整理目前 repo 內建的 Loki / Grafana / Alloy log pipeline。

## Log Pipeline

目前 bot log 的流向是：

```text
bot stdout/stderr -> Docker container logs -> Grafana Alloy -> Loki -> Grafana
```

設計重點：

- 應用程式 log 預設輸出為單行 JSON
- `discord.py` log 和應用程式 log 會分開
- Claude workflow lifecycle log 會歸在 `claude_sdk` subsystem
- Alloy 只收 `bot` 服務，不會把整個 Compose 專案全部送進 Loki

## 內建 Label 與切分方式

目前常用 label 包含：

- `app="emoji-trigger-agent"`
- `service="bot"`
- `subsystem`
- `event`

其中 `subsystem` 主要會看到：

- `app`
- `discord_py`
- `claude_sdk`

## Grafana

網址：

- `http://localhost:3000`

帳密來自：

- `GRAFANA_ADMIN_USER`
- `GRAFANA_ADMIN_PASSWORD`

目前已內建一個 dashboard：

- `Emoji Trigger Agent Logs`

## 常用 Loki 查詢

查全部 bot log：

```logql
{app="emoji-trigger-agent", service="bot"}
```

只看 Claude workflow 過程：

```logql
{app="emoji-trigger-agent", service="bot", subsystem="claude_sdk"} | json
```

只看 `discord.py`：

```logql
{app="emoji-trigger-agent", service="bot", subsystem="discord_py"} | json
```

查 queue failure：

```logql
{app="emoji-trigger-agent", service="bot"} | json | event="queue.target.failed"
```

## Loki API 狀態

`http://localhost:3100/` 回 `404` 是正常的，因為 Loki 不是用根路徑提供 GUI。

可以用下面兩個 endpoint 確認服務狀態：

- `http://localhost:3100/ready`
- `http://localhost:3100/loki/api/v1/status/buildinfo`
