# emoji-trigger-agent

使用 Python 3.13 + uv + discord.py 的 emoji 觸發 Discord bot。

## 1) 安裝依賴

```bash
uv sync
```

## 2) 設定 Bot Token

```bash
export DISCORD_BOT_TOKEN="你的 token"
```

## 3) 啟動

```bash
uv run python -m src.app
```

## 4) Discord 必要設定

- 啟用 `MESSAGE CONTENT INTENT`
- Bot 需有讀取訊息、發送訊息、讀取歷史、reaction 權限

## 5) emoji 對應修改

在 [src/handlers.py](src/handlers.py) 的 `default_handlers()` 調整。
