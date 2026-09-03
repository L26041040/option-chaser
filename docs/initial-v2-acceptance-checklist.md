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

**11. Butterfly 候選顯示真正的損益兩平點與獲利區間（不是只有一個
單調家族式的 breakeven）** ✅
自動化：`AnalysisReport.test.tsx`、e2e「T16（#232）：Butterfly 兩個
損益兩平點與獲利區間都在分析報告裡」。

⚠ **驗收時請注意（CLOSEOUT-004 修正後）**：損益兩平點**不一定是兩個**。
broken-wing（兩翼不等寬）組合的翼外平台若本身就高於進場成本，那一側
到期時永遠獲利、沒有由虧轉盈的價位——這種候選只有**一個**真的損益
兩平點，獲利區間顯示成「$X 以上」或「$X 以下」而不是一個範圍。
**看到只有一個點不是回歸，是正確的**；反過來，若看到「獲利區間
$X ~ $Y（區間外到期時無法獲利）」卻其實漲更高還是賺，那才是回歸。
契約樣本裡 30 個使用者可見的 Butterfly 候選中有 6 個屬於前者。
自動化：e2e「CLOSEOUT-004（Finding 1）：獲利區間在上方沒有界的
Butterfly……」。

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

---

# 附錄：OPTION-CHASER-REPAIR-001（spec #237）四組症狀驗收

Initial V2 上線後，Owner 在 Vercel preview 做真機驗收時發現四組症狀
（P1–P4），已依 spec #237（issue #237）拆成 REPAIR-01～12（issues
#238–#249）修復完畢。本附錄供你回到 Vercel preview 逐條重新驗證這四
組症狀確實消失——圖例與正文相同（✅ 自動化覆蓋／⚠ 需你親自確認）。

## P1：舊劇本編輯 422

**22. 開啟任何升版前建立的舊劇本編輯表單，Vertical Spread checkbox
正確顯示已勾選（不是空的）** ✅
自動化：`tests/test_strategy_family.py::test_get_scenario_
normalizes_a_legacy_subtype_string_to_its_family`、
`CreateForm.test.tsx` legacy round-trip 案例。

**23. 不改動任何 checkbox、直接按儲存，必定成功（不再跳出「422」
或任何錯誤）** ✅
自動化：`tests/test_strategy_family.py::test_editing_a_legacy_
scenario_with_the_value_it_reads_back_now_succeeds`、e2e「legacy
edit round trip」。真因是 `_scenario_json()`（全站唯一序列化
`strategies` 的讀取路徑）先前漏呼叫 `normalize_families()`，
REPAIR-02／#239 補上。

**24. 在舊劇本上加勾其他 family（例如同時勾 Call/Put）後儲存，也必定
成功** ✅
自動化：`tests/test_strategy_family.py::test_editing_a_legacy_
scenario_to_add_a_family_succeeds`。

## P1 附帶新需求：Strategy Family 全選

**25. 建立與編輯表單都有「全選」操作；已全選時再點一次變成「取消
全選」；沒有獨立的「全不選」按鈕；至少選一個才能送出的規則不變** ✅
自動化：`CreateForm.test.tsx`（REPAIR-06／#243），e2e「全選／取消
全選」。

## P2：刷新失敗的卡片沒有明顯反灰／鎖定

**26. 曾經至少成功分析過一次的劇本，這次刷新失敗後：卡片反灰＋
明確顯示「更新失敗，目前顯示上一次成功結果」＋仍可點入看最後一次
成功結果＋有 Retry** ✅
自動化：`scenarios.test.ts`／`ScenarioList.test.tsx`／
`CompactScenarioList.test.tsx`（REPAIR-05／#242），e2e「失敗卡片
情境 A」。

**27. 從未成功分析過的劇本（含新建劇本）第一次刷新就失敗：卡片
反灰＋明確顯示「尚無可用分析結果」＋不會點進一個不存在的詳細頁
＋有 Retry** ✅
自動化：同上，e2e「失敗卡片情境 B」。

**28. 「更新中」與「刷新失敗」兩種狀態視覺上分得清楚，不會混在一起**
✅
自動化：`cardFailureVariant()` 純函式測試（`updating` 為真時失敗
提示不顯示）。

## P3：刷新失敗比例偏高＋成功刷新後數字看起來異常

**29. 一個正常規模的劇本（三個 family 全開）刷新不再因為逾時而
整批失敗——在 Vercel preview 上連續建立、刷新幾個涵蓋多個到期日的
劇本，不應再看到大量 504／連線逾時** ⚠ 這條需要你在真實 Vercel
環境確認（沙箱無法重現 production 的網路延遲與 Vercel 60 秒平台
硬上限）。自動化只能證明「production-equivalent 規模＋真實 q≠0 下，
單一劇本三 family 全開在本機量測 ≤20 秒完成」（`tests/test_api_
performance_guard.py`，REPAIR-10／#247，本機實測 7.543 秒，
`calibrate_leg` memoization 前 154.236 秒——20.4 倍）——本機數字
不等於 production 網路延遲下的真實體感，需要你實機確認。

**30. 任一劇本刷新逾時或連線失敗，不會連坐拖累同一輪裡其他還沒
處理到的劇本——其餘劇本應該正常完成，不會一起變成失敗** ✅
自動化：`App.test.tsx`、e2e（REPAIR-04／#241：`refreshRun()`
批次呼叫本身失敗時改逐一走單一劇本端點，各自獨立判定成敗）。

**31. 劇本卡片頭條數字（跨 family 冠軍）不再因為 Long Call／
Long Put 候選到期日較晚就顯得特別誇張——如果你記得舊版某些長天期
單腿劇本的報酬率看起來高得不合理，重新整理後應該會降到與 Vertical／
Butterfly 同一個量級可信的數字** ⚠ 建議你挑一個記得舊數字的長天期
單腿劇本重新整理，肉眼對照。自動化已證明修法方向正確且範圍精準
（REPAIR-09／#246：`tests/test_selection_regression.py::test_
cross_family_champion_baseline_return_is_corrected_when_baseline_
expiry_is_after_anchor`，真實三 family 情境下 single-leg champion
從灌水值 `1.1926288317629354` 修正到 `0.9569471624266144`，
Vertical／Butterfly 兩個 family 逐位元不變），但「你記得的那個舊
數字」是個別 production 資料，自動化測試用的是合成 fixture，數字
本身無法互相對照。

## P4：新建劇本刷新一律失敗

**32. 新建一個涵蓋多個到期日、三個 family 全開的劇本，建立後緊接著
的自動刷新應該能拿到分析結果，不再是一律連線失敗** ✅（機制）／
⚠（production 網路延遲需你確認）
自動化：`tests/test_api_performance_guard.py`（REPAIR-10／#247）
證明單一劇本 production-equivalent 規模下本機 7.5 秒可完成，遠低於
Vercel 60 秒平台硬上限；`_refresh_and_save()` 內建 per-scenario
soft deadline（REPAIR-08／#245，僅作用於異常輸入，正常規模不觸發）
作為額外安全網。真實 Vercel 網路延遲下的實際體感，建議你實機建立
一個新劇本驗證。

---

**收尾狀態**：OPTION-CHASER-REPAIR-001（issues #238–#249）全數
完成或依決策閘門標記 `not_planned`（#244，FIX-03——REPAIR-10 實測
production-equivalent 規模 3 family 全開僅 7.543 秒，遠低於 20 秒
Acceptance Threshold，依 spec #237 決策邏輯明文不施工）。全套後端
（記憶體＋真實 Postgres）、前端 typecheck／Vitest／build、
Playwright（iPhone＋Desktop）連續兩輪穩定綠燈，詳見 REPAIR-12
（#249）GitHub 收尾留言的完整對照表。
