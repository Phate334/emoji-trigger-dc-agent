# TODO

- [ ] 加入清除過舊 Claude session 的機制
  目標：避免 `claude-agent-sdk` / Claude Code 在 `~/.claude/projects/...` 持續累積不必要的 session 檔。
  方向：評估用 `list_sessions()` 搭配 `delete_session()`，依時間、數量上限或專案範圍做清理。

- [ ] 清除過舊的 db 紀錄

- [ ] 規畫建立 emoji agent 的 skill 範本與建立流程
  目標：讓新增 `agents/<agent-id>/` 時，能一致地建立 `.claude/agents/`、`.claude/skills/` 與可選 `.mcp.json`。
  方向：設計一份最小可用的 agent/skill scaffold，並補上 README 範例與命名規範。
