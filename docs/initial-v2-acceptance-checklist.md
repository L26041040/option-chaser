# Initial V2（spec #217）全站驗收清單——給需求方真機走一遍

依專案規則，視覺驗收（好不好看、版面順不順眼）不做截圖比對，由需求方
自己在畫面上判斷；這份清單只負責告訴你「每一條該去哪裡看、看什麼」，
以及哪些是自動化測試已經守住、哪些必須你親自確認。

**圖例**：✅ 已完成，自動化測試覆蓋（後端 pytest／前端 Vitest／
Playwright e2e）｜ ⚠ 已完成但需你親自確認的主觀或環境狀態

---

## 三個 Strategy Family 的建立與瀏覽

**1. 建立劇本時可以勾選 Call / Put、Vertical Spread、Butterfly 三個
family（複選）** ✅
去劇本庫按「建立劇本」，標的／目標價／目標年月三欄之外，應該看到三個
可勾選的 family checkbox，預設全部不勾（無預設值，T10／#227）。一個都
不勾送出會被前端擋下並說明原因。自動化：`CreateForm.test.tsx`、
`e2e/smoke.spec.ts`／`desktop.spec.ts`「一個 family 都沒勾就送出」。

**2. 編輯既有劇本可以增減 family，儲存後套用新的勾選集合** ✅
自動化：`EditScenario.test.tsx`、e2e「編輯可以增減 family」。

**3. 詳細頁每個啟用的 family 各一個 tab，切換 tab 只換排名內容、不
影響頭條數字** ✅
自動化：`FamilyTabs.test.tsx`、e2e「多 family 並存」。

**4. 不可選的 family 在畫面上看得到、並說明原因（例如「看漲劇本裡
Put 不可選」）——不是消失，是灰掉＋文字說明** ✅
自動化：e2e「顯示不可選的 family 與原因」。

**5. 畫面上任何地方都不出現「推薦」「較適合」這類評語** ✅
自動化：`family.test.ts`／`FamilyTabs.test.tsx` 禁詞掃描、e2e「不做
推薦／不推薦」。

**6. 看漲劇本（目標價 > 現價）三個 family 都可選；Put 相關候選不
出現** ✅ **看跌劇本對稱成立** ✅
自動化：`tests/test_family_selection.py`（後端 eligibility 規則）。

---

## 持平劇本（目標價 = 現價）

**7. 建立目標價恰好等於現價的劇本，不會被拒絕** ✅
自動化：`tests/test_family_selection.py`、e2e「T17（#234）：建立持平
劇本」。

**8. 持平劇本只有 Butterfly 可選，Call/Put 與 Vertical Spread 顯示
「持平」原因且不可選** ✅
自動化：同上，e2e 逐一斷言兩個不可選分頁的文案。

**9. 持平劇本的 Butterfly 候選數字看起來正常（不是所有情境都擠在同一
個價位、韌性指標不是一條死值）** ⚠ 建議你實機看一眼詳細頁的完成度
曲線／七情境數字，確認視覺上有變化，不是一條平線。自動化只驗證了
「產生非退化的多個相異值」這個抽象性質（`tests/test_scenarios.py`），
數字實際看起來是否合理需要你的直覺判斷。

---

## Butterfly 三腿與獲利區間

**10. Butterfly 候選完整顯示三隻腿（低／中／高履約價），中腿口數
標示為 2×** ✅
自動化：`ExpiryStructure.test.tsx`、e2e「T16（#232）：Butterfly 三隻
腿完整顯示，中腿口數看得出來」。

**11. Butterfly 候選顯示兩個損益兩平點與獲利區間（不是只有一個
breakeven）** ✅
自動化：`AnalysisReport.test.tsx`、e2e「T16（#232）：Butterfly 兩個
損益兩平點與獲利區間都在分析報告裡」。

**12. Butterfly 詳細頁不出現「IV 相對位置」區塊（結構上只認得單腿
與兩腿）** ✅
自動化：e2e「Butterfly 詳細頁不出現『IV 相對位置』」，且斷言零 IV
請求。

**13. Butterfly 候選也有淨成本走勢圖** ✅
自動化：e2e「Butterfly 候選有淨成本走勢圖」。

---

## 熱力圖展開

**14. 每個候選都能展開看到自己的熱力圖，展開時畫面不轉圈、不等待**
✅
自動化：`e2e/smoke.spec.ts`／`desktop.spec.ts`「展開...零額外網路
請求」，涵蓋 Butterfly 候選與一般 Vertical Spread 候選兩種（T18 補件）。

**15. 熱力圖維持既有的價格軸、日期軸與右側漲跌幅標示，Butterfly 候選
的熱力圖看起來跟其他 family 一致** ⚠ 建議你實機展開一個 Butterfly
候選看一眼版面，確認跟 Vertical Spread 候選的熱力圖版式一致（自動化
驗證的是資料正確性，版式一致性建議你肉眼確認一次）。

---

## 舊劇本相容性

**16. 升版前建立的舊劇本打開後，卡片數字、候選、排名與升版前完全
一致** ✅
自動化：`tests/test_selection_regression.py` 的 bitwise 基準測試
（`test_bull_call_spread_numbers_are_bitwise_frozen` 等）、
`tests/test_strategy_family.py`（legacy subtype 字串映射回 family）。
若你手上有升版前建立的真實劇本，建議實機打開一次，確認數字沒有變。

**17. 舊劇本不會自動多出你當初沒有勾選的 family** ✅
自動化：`tests/test_strategy_family.py::test_a_legacy_scenario_with_
a_bare_subtype_still_refreshes_as_before`。想用新 family 時，編輯劇本
勾起來就有。

---

## 桌面與手機版面

**18. 桌面（≥1100px）維持左庫右工作區的 master/detail 版面，family
tab 切換不破壞既有版面比例** ✅
自動化：`e2e/desktop.spec.ts` 全套（含左右比例、批次操作、垃圾桶等
既有案例，Initial V2 施工期間持續全綠）。

**19. 手機版面（compact row、返回還原捲動位置、垃圾桶、批次操作）
維持既有行為不變** ✅
自動化：`e2e/smoke.spec.ts` 全套。

**20. 一輪刷新（開站／手動／建立新劇本）仍是一次或少數幾次批次
請求，不會因為 family 變多而變成大量零碎請求；刷新中的卡片維持
「舊資料＋更新中徽章」，不整段鎖死** ✅
自動化：`tests/test_api_refresh.py`、`App.test.tsx`（PC-05／#202
鎖定卡片維持灰化不可點入，Refresh Run 批次語意不變）。

---

## 綜合

**21. 整體操作起來，這次擴充「感覺像原本產品的延伸」而不是「貼了
一塊新東西上去」** ⚠ 主觀判斷，建議你花幾分鐘隨意逛逛三個 family、
建幾個不同方向（看漲／看跌／持平）的劇本，憑直覺感受介面是否一致。

---

## 自動化把關現況（供參考，不需要你逐條驗證）

- 後端 pytest（記憶體假體＋真實 Postgres 雙後端）：全套綠燈。
- 前端 typecheck／Vitest／production build：全套綠燈。
- Playwright e2e（iPhone＋Desktop 兩個 project）：111 條，連續兩輪
  穩定無 flake。
- CLI golden fixtures：既有四策略維持 byte-locked（僅 T04 friction
  退場、T05 過濾統計新增一行兩次合理重產，逐一核對過內容差異僅限
  預期範圍）。
- Initial V2 spec #217 明列的 12 條硬回歸紅線：逐條核對皆有測試把關
  （紅線 8／12 在 T18 稽核時發現覆蓋缺口並已補齊）。
