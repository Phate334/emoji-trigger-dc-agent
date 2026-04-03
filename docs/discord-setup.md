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

### 4-3. 保持 Bot 私有（Private）

若你希望 Bot 僅供自己或管理團隊使用，可在 Developer Portal 進行以下設定：

1. 前往左側選單 **Bot**。
2. 在 Bot 設定區塊找到 **Public Bot**，將其關閉（unchecked）。

依據 Discord 官方 OAuth2 文件，當 **Public Bot** 關閉時，只有應用程式擁有者可將 Bot 加入伺服器；若開啟，任何擁有邀請連結且具備權限的使用者都可安裝該 Bot。

進一步建議（可選）：

1. 前往左側選單 **Installation**。
2. 在 **Install Link** 類型中，視需求選擇：
   - **None**：隱藏 App 頁面的 **Add App** 按鈕。
   - **Discord Provided Link** 或 **Custom URL**：保留安裝入口，但仍建議不要公開散佈連結。
3. 在 **Installation Contexts** 中，若只需要伺服器安裝，維持僅啟用 **Guild Install**（可關閉 **User Install**）。

> ℹ️ 「私有」主要限制的是誰可以新增安裝。關閉 **Public Bot** 不會自動移除 Bot 在既有伺服器中的安裝狀態。

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
- [OAuth2 Bot Users（Public Bot 行為說明）](https://docs.discord.com/developers/topics/oauth2#bot-users)
- [Application Resource（`bot_public` 欄位定義）](https://docs.discord.com/developers/resources/application)
- [Application Resource Install Links（Install Link 類型與設定）](https://docs.discord.com/developers/resources/application#install-links)
