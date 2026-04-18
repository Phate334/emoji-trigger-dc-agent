# 系統架構與 Agent 開發

本文件說明專案的分層、trigger 處理流程、route 規則，以及新增 agent 的方式。

## 分層原則

- `src/`：共用 runtime
- `agents/`：各個 agent 自己的 Claude project
- `outputs/`：durable outputs 與 queue database

原則上：

- 所有 workflow 都共用的能力，放在 `src/`
- 只屬於某個 agent 的行為，放在 `agents/<agent-id>/`

## Trigger 流程

1. Discord 訊息內容或 reaction 命中 `agents/agents.yaml`
2. `src/bot.py` 先把 trigger 寫進 SQLite queue
3. queue 以 `message_id + agent_id` 合併同一則訊息上的 trigger
4. `src/trigger_queue.py` 的背景 worker claim target
5. `src/executor.py` 在 `agents/<agent-id>/` 目錄下執行 Claude agent
6. runtime 驗證 `outputs/<agent-id>/` 是否真的有檔案異動
7. 驗證通過才標記成功，否則依 retry 規則重試或標成失敗

## 專案結構

```text
src/
  app.py
  bot.py
  config.py
  agent_manifest.py
  trigger_queue.py
  executor.py

agents/
  agents.yaml
  <agent-id>/
    AGENTS.md
    .claude/
      agents/
      skills/

outputs/
  <agent-id>/
  trigger_queue.sqlite3
```

## Route Manifest

runtime 只看 `agents/agents.yaml`。

最小範例：

```yaml
version: 1
routes:
  - emoji: "📝"
    agent_id: "memo-agent"
```

目前支援欄位：

- `emoji`
- `agent_id`
- `params`
- `model`
- `reasoning_effort`

## Route 規則

- route 要維持 declarative，不要把 emoji 判斷寫死在 `src/`
- 如果多個 emoji 指向同一個 `agent_id`，它們的 execution 設定必須一致
- queue 會把同一個 `message_id + agent_id` 合併成單一 target

## 新增 Agent 的基本流程

1. 在 `agents/agents.yaml` 加 route
2. 建立 `agents/<agent-id>/`
3. 建立 `agents/<agent-id>/AGENTS.md`
4. 建立 `agents/<agent-id>/.claude/agents/<agent-id>.md`
5. 需要 skills 時，放在 `agents/<agent-id>/.claude/skills/`
6. durable outputs 寫到 `/app/outputs/<agent-id>/`

## memo-agent 範例

repo 目前內建 `📝 -> memo-agent`，可以拿來當最小參考實作。

它示範了：

- 訊息內容與 reaction 兩種 trigger
- queue merge
- 獨立 agent project 執行
- durable markdown output 寫入 `outputs/memo-agent/`
