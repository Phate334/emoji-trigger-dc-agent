# Discord Bot 串接申請流程

本文件說明如何在 Discord Developer Portal 建立 Bot Application，並取得 Token 以串接此 emoji-trigger-agent。

---

## 1. 建立 Discord Application

1. 前往 [Discord Developer Portal](https://discord.com/developers/applications)，並以你的 Discord 帳號登入。
2. 點擊右上角 **New Application**。
3. 輸入應用程式名稱（例如 `emoji-trigger-agent`），點擊 **Create**。

---

## 2. 建立 Bot 使用者

1. 在左側選單點擊 **Bot**。
2. 點擊 **Add Bot**，確認後即建立 Bot 使用者。
3. 在 **Token** 欄位點擊 **Reset Token** 取得 Bot Token。

> ⚠️ Token 只會顯示一次，請立即複製並妥善保存（建議使用密碼管理器），**切勿提交至版本控制系統**。

---

## 3. 啟用必要的 Privileged Intents

此 Bot 使用以下 [Privileged Gateway Intents](https://docs.discord.com/developers/events/gateway#privileged-intents)，**必須手動在 Developer Portal 啟用**：

| Intent | 用途 |
|---|---|
| **Message Content Intent** | 讀取訊息內容以偵測 emoji 觸發字 |

啟用步驟：

1. 前往 Bot 設定頁（左側選單 **Bot**）。
2. 往下捲動至 **Privileged Gateway Intents** 區塊。
3. 開啟 **Message Content Intent** 的開關。
4. 點擊 **Save Changes**。

![Privileged Gateway Intents 設定畫面](https://discordpy.readthedocs.io/en/stable/_images/discord_privileged_intents.png)

> ℹ️ Bot 加入超過 100 個伺服器後，需通過 [Discord Bot 驗證](https://support-dev.discord.com/hc/en-us/articles/23926564536471) 才能繼續使用 Privileged Intents。

---

## 4. 設定 Bot 權限並邀請至伺服器

### 4-1. 產生邀請連結（OAuth2 URL）

1. 在左側選單點擊 **Installation**。
2. 在 **Default Install Settings** → **Guild Install** 下，加入以下 scope 與 permission：

   | 類型 | 值 |
   |---|---|
   | **Scopes** | `bot` |
   | **Bot Permissions** | `Send Messages`、`Read Message History`、`Add Reactions`、`Read Messages/View Channels` |

3. 複製頁面上方的 **Install Link**。

### 4-2. 邀請 Bot 加入伺服器

1. 在瀏覽器開啟複製的邀請連結。
2. 選擇目標伺服器，點擊 **Authorize**。

---

## 5. 設定環境變數

將 Bot Token 設定為環境變數：

```bash
export DISCORD_BOT_TOKEN="你的 Bot Token"
```

或建立 `.env` 檔案（Docker 模式）：

```ini
DISCORD_BOT_TOKEN=你的 Bot Token
```

> ⚠️ 請確保 `.env` 已加入 `.gitignore`，避免 Token 外洩。

---

## 6. 啟動 Bot

```bash
uv run python -m src.app
```

Bot 上線後終端機會顯示：

```
Logged in as <bot name> (<bot id>)
```

---

## 參考連結

- [Discord Developer Portal](https://discord.com/developers/applications)
- [Discord 官方快速入門教學](https://docs.discord.com/developers/quick-start/getting-started)
- [Gateway Intents 說明文件](https://docs.discord.com/developers/events/gateway#privileged-intents)
- [discord.py Intents 入門指南](https://discordpy.readthedocs.io/en/stable/intents.html)
- [Bot 驗證申請流程](https://support-dev.discord.com/hc/en-us/articles/23926564536471)
