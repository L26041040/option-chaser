# PB-02（#294）Cookie 測試筆記

`_OWNER_COOKIE_NAME`（`__Host-oc_owner`）帶 `Secure` 屬性——瀏覽器與
httpx 的 cookie jar 都會在 scheme 不是 `https` 時直接拒收／拒送這顆
cookie（已用最小重現腳本實測：`http://testserver` 下 `Set-Cookie` 標頭
確實送出，但下一次請求的 `request.cookies` 讀不到它）。

**兩種測試因此分成兩條路徑**：

1. **顯式覆寫 `identity_resolver`**（既有 `test_scale06_ownership_
   expand.py`／`test_scale11_ownership_enforce.py`，以及本輪新增前
   28 個非 ownership 相關測試檔統一採用的 `identity_resolver=lambda:
   "solo"`）——`_uses_cookie_identity` 判定為 `False`，`_request_scope_
   middleware` 完全不碰 cookie／owner 表，行為與 PB-02 之前逐位元
   相同。`TestClient` 不需要（也不應該假裝需要）`https` base_url。

2. **測試 cookie 機制本身**（`tests/test_pb02_cookie_identity.py`、
   `test_scale06_ownership_expand.py` 僅有的兩條使用預設 resolver 的
   測試）——`TestClient(app, base_url="https://testserver")`，讓 httpx
   的 cookie jar 用跟正式站（Vercel，恆為 HTTPS）一致的 scheme 判斷。

production 本身不受這個測試限制影響——Vercel 一律 HTTPS，`Secure`／
`__Host-` 三個條件（`Secure`＋`Path=/`＋不設 `Domain`）自然成立。**唯一
真正受影響的是「本地手動起一個純 HTTP 的 Python 後端」這種開發情境**
（例如 `uvicorn api.index:app` 不加 TLS）——這是明確記錄的已知限制，
不是靜默降級：程式碼不會偵測「是不是 HTTPS」然後悄悄拿掉 `Secure`。
CLAUDE.md「環境」一節記載的既有開發流程（前端 `npm run dev` 全靠
Playwright route 攔截 mock `/api/*`，從不真的打進這個 Python app）本來
就不受影響。
