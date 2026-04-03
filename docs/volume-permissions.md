# Volume 權限修復方案

## 問題

容器內運行的應用 (nonroot 用戶, UID 999) 無法寫入從主機掛入的 `codex/runtime` volume，導致 `PermissionError: [Errno 13] Permission denied` 錯誤。

## 根本原因

當使用 Docker volume bind mount 時，容器內的文件權限由主機端的文件系統決定。如果主機上的 `codex/runtime` 目錄由其他用戶擁有 (例如 root 或 UID 1000)，容器內的 nonroot 用戶 (UID 999) 無法寫入。

## 解決方案

### 1. Dockerfile 修改

在 Dockerfile 的 runtime stage 中，確保 `/app/codex/runtime` 目錄在容器構建時被創建並設置 777 權限：

```dockerfile
RUN mkdir -p /app/codex/runtime && \
    chmod 777 /app/codex/runtime
```

**為什麼是 777？**
- 777 權限(drwxrwxrwx)允許任何用戶讀、寫、執行，確保與不同主機持有者的 volume 兼容
- 此目錄用於臨時運行時數據，安全風險可接受

### 2. Docker Compose 配置

在 `compose.yaml` 中明確指定容器用戶：

```yaml
services:
  bot:
    # ... other config ...
    user: "999:999"  # 明確運行為 nonroot user (UID 999)
    volumes:
      - ./codex/runtime:/app/codex/runtime
```

**為什麼明確指定 user？**
- 確保容器始終以 nonroot 身份運行 (安全最佳實踐)
- 使部署行為可預測且跨環境一致

### 3. 主機端準備 (部署時)

在首次部署或重新部署時，確保主機上的 runtime 目錄具有正確的權限：

```bash
chmod 777 ./codex/runtime
```

## 跨環境部署最佳實踐

1. **本地開發環境**
   ```bash
   chmod 777 codex/runtime
   docker compose up --build
   ```

2. **CI/CD 環境**
   - 在 runner 中執行 `chmod 777 codex/runtime`
   - 或在 docker compose 執行前添加初始化步驟

3. **生產環境 (Kubernetes)**
   - 使用 `initContainer` 設置權限，或
   - 使用 `securityContext` 調整容器用戶映射
   - 創建専用的 PersistentVolume 並預先配置權限

4. **其他編排工具 (Docker Swarm 等)**
   - 確保 volume driver 支援正確的權限傳播
   - 使用 `volume mount options` 進行 UID/GID 映射 (如果支援)

## 驗證修復

測試容器是否能成功寫入 volume：

```bash
# 檢查容器內的目錄權限
docker compose exec bot stat /app/codex/runtime

# 應該看到：Access: (0777/drwxrwxrwx)
```

使用 📝 emoji 反應觸發 memo_append 操作，驗證應用可以成功寫入文件。

## 相關配置文件

- `Dockerfile`: 容器構建配置
- `compose.yaml`: 本地開發環境配置
- `codex/runtime/`: 應用運行時數據目錄
