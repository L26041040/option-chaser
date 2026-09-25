# ANTI-ABUSE-PROTOTYPE-001

Prototype／experiment，**不是正式實作**。不碰 Production、不部署、不改產品程式碼。
這個資料夾不被 `api_app` import，檔名刻意不是 `test_*.py`，CI 的 `python -m pytest`
不會收進來（已驗證 collect 數＝0）。

| 檔案 | 內容 |
|---|---|
| `checks_current_master.py` | Part A：用真正的 `create_app()`（MemoryStorage＋假 Cboe fetch）證明現況行為 |
| `sim.py` | 三層防護的離線模擬器（owner bucket／source bucket／global fuse、single-flight、TTL、tiered fuse、fair-share） |
| `workloads.py` | 正常使用者 profile 與攻擊者行為 |
| `experiments.py` | Part B–F 全部實驗，輸出 `RESULTS.md` |
| `checks_sim.py` | 把模擬結論鎖成斷言 |
| `RESULTS.md` | 實驗結果表（可重跑，固定 seed） |

```bash
# Part A（真 app，記憶體 storage）
PYTHONPATH=. .venv/bin/python -m pytest prototypes/anti_abuse/checks_current_master.py
# Part B–F
cd prototypes/anti_abuse && python3 experiments.py
../../.venv/bin/python -m pytest checks_sim.py
```

## 模型的限制（讀結果前先看）

- 正常使用者 profile 是**模擬輸入**（light 60%／typical 30%／power 10%），不是量測值。
  上線前要用 production `operational_metrics.chain_fetch_count` 的真實分布（唯讀）校正。
- 「一次刷新＝每個 distinct symbol 一次上游」直接取自 current master（ADR-0001）。
- single-flight 的效果取決於 Vercel Python function 是否在同一個 instance 內處理並發請求
  ——**UNVERIFIED**，所以同時列 `inst=1`（最佳）與 `inst=10`（保守）。
- source bucket 在 serverless 上需要共享狀態（Postgres 表或 KV）；模擬器用記憶體，不代表
  production 的實作成本。
- 攻擊者模型：單機腳本、同 IP 刪 cookie、1000 IP 輪替、地毯式掃描、預先養號。沒有模擬
  瀏覽器指紋偽造、CAPTCHA 破解服務等更高成本的手法。
