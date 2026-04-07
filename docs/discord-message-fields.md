# Discord Message Fields

本文件列出目前 `src/discord_context.py` 會序列化並交給 runtime queue 的 Discord message 欄位。

`agents/agents.yaml` 的 `message_fields` 是可選欄位，未設定時會把完整 `message` 交給 agent；有設定時，只會挑選下列第一層欄位中的部分欄位傳入 agent payload。

重點：

- `message_fields` 只接受第一層欄位名稱
- 若設定 `author`、`channel`、`attachments` 這類欄位，會傳整個對應物件或陣列
- SQLite queue 內保存的 `message_snapshot_json` 仍然是完整 message snapshot，不會因為 `message_fields` 被裁切

## Top-Level Fields

| Field | Type | Notes |
|---|---|---|
| `id` | `int` | Discord message ID |
| `content` | `string` | 原始訊息內容 |
| `clean_content` | `string` | Discord 清理後訊息內容 |
| `system_content` | `string` | system message 顯示內容 |
| `jump_url` | `string` | 訊息跳轉連結 |
| `created_at` | `string \| null` | ISO 8601 timestamp |
| `edited_at` | `string \| null` | ISO 8601 timestamp |
| `pinned` | `bool` | 是否已釘選 |
| `flags` | `int` | message flags 整數值 |
| `author` | `object` | 作者資訊 |
| `channel` | `object` | 頻道資訊 |
| `guild` | `object \| null` | 伺服器資訊；DM 時為 `null` |
| `attachments` | `array<object>` | 附件清單 |
| `embeds` | `array<object>` | embed 清單 |
| `mentions` | `array<object>` | 被 mention 的使用者 |
| `role_mentions` | `array<object>` | 被 mention 的角色 |
| `channel_mentions` | `array<object>` | 被 mention 的頻道 |
| `stickers` | `array<object>` | sticker 清單 |
| `reactions` | `array<object>` | message reaction 摘要 |
| `reference` | `object \| null` | reply / reference 資訊 |

## Nested Shapes

### `author`

| Field | Type |
|---|---|
| `id` | `int` |
| `name` | `string` |
| `display_name` | `string` |
| `global_name` | `string \| null` |
| `bot` | `bool` |

### `channel`

| Field | Type |
|---|---|
| `id` | `int` |
| `name` | `string \| null` |
| `type` | `string` |

### `guild`

| Field | Type |
|---|---|
| `id` | `int` |
| `name` | `string` |

### `attachments[]`

| Field | Type |
|---|---|
| `id` | `int` |
| `filename` | `string` |
| `content_type` | `string \| null` |
| `size` | `int` |
| `url` | `string` |
| `proxy_url` | `string` |

### `embeds[]`

| Field | Type |
|---|---|
| `type` | `string \| null` |
| `title` | `string \| null` |
| `description` | `string \| null` |
| `url` | `string \| null` |

### `mentions[]`

| Field | Type |
|---|---|
| `id` | `int` |
| `name` | `string` |
| `display_name` | `string` |

### `role_mentions[]`

| Field | Type |
|---|---|
| `id` | `int` |
| `name` | `string` |

### `channel_mentions[]`

| Field | Type |
|---|---|
| `id` | `int` |
| `name` | `string` |
| `type` | `string` |

### `stickers[]`

| Field | Type |
|---|---|
| `id` | `int` |
| `name` | `string` |
| `format` | `string` |

### `reactions[]`

| Field | Type |
|---|---|
| `emoji` | `string` |
| `count` | `int` |
| `me` | `bool` |

### `reference`

| Field | Type |
|---|---|
| `message_id` | `int \| null` |
| `channel_id` | `int \| null` |
| `guild_id` | `int \| null` |
| `jump_url` | `string \| null` |
