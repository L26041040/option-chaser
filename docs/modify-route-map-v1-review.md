# modify-route-map-v1 獨立覆核報告

覆核日期：2026-07-30
覆核對象：`docs/modify-route-map-v1.md`（commit `85af90f` 版本）
需求來源：`docs/modifyRequestV1.md`
> ⚠️ 2026-07-30 後續更新：本報告 §2.2 問題 2 與 §三 建議事項中，關於
> 「跨到期日全域 Top 10」與「年月映射建議取月底」的結論**已被需求方作廢**。
> 現行有效模型見 `docs/modifyRequestV1.md` §三/§五/§六/§七/§八與附錄A：
> 排名為**每個到期日各自 Top 10**（摘要層每期第 1 名、詳細層預設 baseline
> 的 Top 10）；年月**不映射單一日期**。本報告其餘逐項核對結果仍有效。

方法：不預設路線圖正確，對其引用的每一處檔案/行號/函式實際開檔核對，
並回查 `service.py`／`ranking.py`／`store.py`／`workspace.py`／
`valuation.py`／`matrix.py`／`webapp/app.py`／`webapp/pages/0_劇本工作區.py`
／`tests/test_matrix.py` 與 git 歷史。非全 repository 掃描。

---

## 一、覆核結論

**可以進入施工（YES）**，前提是採用本次已修正後的路線圖版本。

原路線圖的主體判斷（TARGETED_REFACTOR）與絕大多數證據引用經核對屬實，
但有 1 處過時、1 處證據錯誤、1 處需求遺漏，均已直接修正於
`docs/modify-route-map-v1.md`。

## 二、逐項驗證結果

### 2.1 核對屬實的關鍵主張（抽樣）

| 路線圖主張 | 核對結果 |
|---|---|
| `valuation.py:81-89` `scenario_leg_value()` 對 `at < expiry` 走 BS+美式下限，`at >= expiry` 才用 intrinsic | ✅ 屬實 |
| `valuation.py:195-202` `spread_scenario_value()` 兩腳合併並鉗制 `[0, width]` | ✅ 屬實 |
| `matrix.py:60-68` `matrix_grid()` 逐格呼叫 `value_fn`，非到期 payoff 硬套 | ✅ 屬實 |
| 排名公式 `ranking.py:110-111` `spread_baseline_return` | ✅ 屬實 |
| `candidate_key()`（`service.py:258-263`）= strategy+兩腳履約價+到期日 | ✅ 屬實 |
| `_sample_expiries()`（`service.py:278-293`）上限 4、僅供顯示取樣 | ✅ 屬實 |
| 年月合併輸入/正規化函式不存在（全 repo grep） | ✅ 屬實（`0_劇本工作區.py:94` 用 `st.date_input` 精確到日） |
| 建立表單多要求方向（L81）與策略勾選（L92-93） | ✅ 屬實 |
| 無 20/80 版面、無 `st.columns([0.2, 0.8])` | ✅ 屬實 |
| 資料狀態燈號不存在，只有生命週期 badge（`0_劇本工作區.py:20-21`） | ✅ 屬實 |
| 無開站自動更新迴圈，分析僅由按鈕觸發（L163-167、250-253） | ✅ 屬實 |
| `save_result()` 逐次快照（`store.py:378-383`）、`_candidate()` 無「當時排名」欄位（`store.py:256-307`） | ✅ 屬實 |
| 快照只含 top-3 candidates + expiry_best，掉榜 Spread 該次無資料點 | ✅ 屬實（`serialize_result()` 僅序列化這些） |
| Long Call 追平可重用 `valuation.py:127` 的 `l3 = baseline_value / (1 + p.min_return)` 公式形狀 | ✅ 屬實 |
| 計算層與 UI 分離、`_pareto_frontier` 為唯一幾何例外（`render.py:288`） | ✅ 屬實 |

### 2.2 發現的問題（已修正）

**問題 1（過時）：Step 0 已完成，路線圖仍列為「實作錯誤／待施工」。**
commit `5e6b1bb`（2026-07-30 06:22，晚於路線圖 commit `85af90f` 06:06）已把
`matrix.py:23` overshoot 從 1.10/0.90 改為 1.15/0.85，並同步更新
`tests/test_matrix.py:36,47,68,76` 斷言與四份 golden fixtures。本次覆核實跑
`pytest tests/test_matrix.py tests/test_spread_valuation.py
tests/test_matrix_grid.py tests/test_golden_v2.py` 全綠。
→ 已將路線圖 §1、§2（四）、§3、Step 0 標記為完成。

**問題 2（證據錯誤，影響 Step 6 施工方式）** ⚠️ 2026-07-30：本項的**證據
部分仍成立**（`ranked_spreads` 確實被截斷至 `p.top` 且未序列化），但其
**結論部分已作廢**——需求方確認不採用「跨到期日全域 Top 10」，改為每個
到期日各自 Top 10。因此正確做法是把 `all_ranked` **依到期日分組後各自取
前 10**，而非取全域前 10。詳見 route map Step 6（已改寫）。**

原文：
原文稱「`ranked_spreads` 本身雖是全域排序（service.py:445）」。實際上
`rank_spreads()`（`ranking.py:120-122`）在回傳前即截斷至 `p.top`
（`models.py:51` 預設 3），故 `StrategyResult.ranked_spreads` 只含 3 筆；
且 `store.serialize_result()`（`store.py:310-375`）完全沒有序列化此欄位，
結果 JSON 中不存在任何可切出 Top10 的資料。真正的全域完整排序是
`_spread_result()` 內的區域變數 `all_ranked`（`service.py:455-456`）。
若照原文施工，實作者可能誤以為「只缺 UI 攤平」，做到一半才發現 service 與
store 都要動。
→ 已修正 §2（三）證據描述，並在 Step 6 明確寫入正確做法
（`all_ranked[:10]` 外露為新欄位 + `serialize_result()` 新增序列化）。

**問題 3（需求遺漏）：需求七.8「依最新收益率重新排列劇本卡片」無對應步驟。**
`workspace.list_scenarios()` 固定以 `(symbol, target_date, id)` 排序
（`workspace.py:99`），原路線圖 Step 0-7 沒有任何一步涵蓋此需求。
→ 已併入 Step 5（在 UI 層排序，不動 `list_scenarios` 回傳順序，因其順序
是否被對帳/群組邏輯依賴未查證，改 UI 層風險最低）。

### 2.3 覆核後仍成立的判斷

- 總結論 TARGETED_REFACTOR：維持。核心估值/排名/保存架構經核對確實達標，
  缺口集中在輸入層、呈現層聚合與一個小型新計算，均可在既有模組邊界內完成。
- Step 1-7 的順序與依賴關係：合理，維持。Step 4（燈號函式）先於 Step 5
  （自動更新）可行——燈號函式以「該次分析成功/失敗 + Expired 狀態」為輸入
  參數即可，不依賴自動更新先存在。
- 可延後項目（Long Call 追平、Agent API）：分離正確，維持。
- §6 待調查清單（手機版實測、年月→具體日期映射慣例、IV 假設與
  optionsprofitcalculator 比對、效能量測）：均屬實且未被本次覆核解消，維持。

## 三、對使用者的三項回答

1. **是否可以進入施工：YES**（以修正後的路線圖為準）。
2. **阻塞點：無**（原本最大的隱患——Step 6 的 ranked_spreads 證據錯誤——
   已在路線圖中修正）。
3. **建議下一步：執行 Step 1（年月合併輸入與正規化）。**
   ⚠️ 2026-07-30 更新：本項原建議「年月 → `target_date` 預設取當月月底」
   **已作廢**。需求方確認年月**不映射成任何單一日期**；Step 1 產出 (年, 月)
   二元組＋日曆錨點（該月第三個星期五）函式，其後 Step 1-1（到期日選取
   六點規則）、Step 1-2（排名估值時點修正）、Step 2、3 依序推進。
   詳見 `modifyRequestV1.md` 附錄A2。
