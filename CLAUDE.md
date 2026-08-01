# Option Chaser

## 規則

**每做完一張 ticket，就更新下面的「專案紀錄區」**——把該票移到已完成、標出下一張。

**全部 ticket 做完才開 PR、merge 回 master**，中途不要主動開。

只有這兩條。

## 專案紀錄區

### 已完成

- **Step 0** — Heatmap 價格範圍 1.10 → 1.15/0.85（commit `5e6b1bb`）
- **T1** [#15] — 年月與到期日選取純函式模組 `option_chaser/timeframe.py`（commit `4aaf0a0`）
- **T2** [#16] — target_month 全線縱切（輸入、持久化、選取、過濾解耦）
- **T3** [#17] — 排名估值改為各 Spread 自身到期日的內在價值（commit `8d52acf`）
- **T12** [#26] — 估值輸入層：期限對齊利率曲線＋worst 成本口徑
  （commits `c2f7ec2`/`8be24b9`/`d1881fc`；parity 測試點腳本
  `scripts/opc_parity_points.py`，OPC 人工驗證 A13.5 待需求方執行）
- **T4** [#18] — 建立表單簡化為三欄輸入（commits `cd8e0cc`/`a524f1d`）
- **T5** [#19] — 桌面 20/80 版面、緊湊劇本卡片、清單移除工具（commit `1dc010f`；
  A10.5 窄 viewport 驗收待需求方執行）
- **T6** [#20] — 劇本級狀態燈號與失敗分層（commit `26306ab`；附錄 A12「零」
  分層判讀一併納入。已知限制：關鍵失敗旗標只活在 `st.session_state`，
  跨分頁／重啟不保留，留給 T7 一併評估是否需要落地事件）

### 待辦（依序，← 為下一張）

- **T7** [#21] — 自動／手動刷新與原子快照　← 下一張
- **T8** [#22] — 劇本清單依最新收益率排序
- **T9** [#23] — 每到期日 Top 10 與全候選快照序列化
- **T10** [#24] — 詳細頁兩層結構（各期摘要 → 單期 Top 10）
- **T11** [#25] — Spread 歷史時間序列查詢
- **D1** [#14] — Long Call 追平比較（deferred，不得混入 T2–T11）

### 施工依據

- 需求與決策紀錄：`docs/modifyRequestV1.md`（附錄 A1–A12）
- 路線圖與依賴地圖：`docs/modify-route-map-v1.md`
- 每張票的施工細節以 GitHub issue 為準（`L26041040/option-chaser`）

## 環境

- 跑測試：`PYTHONPATH=. .venv/bin/python -m pytest`
  （`pyproject.toml` 的 `packages.find` 只收 `option_chaser*`，`webapp` 不在裡面）
- 建 venv：`uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -e ".[gui]" pytest`
- 全套測試現為全綠（舊紀錄提到的 5 個 streamlit 版本漂移失敗已隨 T2 改寫消失）。
