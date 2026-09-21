/**
 * SW-09（#339）全站文案掃描共用清單。AC 明文列六個詞：vendor／候選池／
 * 口徑／限流事故／規劃中／placeholder——SW-06／SW-07 之前各自的檢查
 * 只各挑幾個字、各自複製一份陣列（見 `CreateForm.test.tsx`／
 * `Settings.test.tsx`／`PrivacyPage.test.tsx`／`ScenarioDetail.test.tsx`
 * 舊版），SW-09 把六個詞收斂成同一份常數，所有「文案去術語」測試都
 * import 這一份，之後要調整禁詞只改一個地方。
 *
 * 檢查對象是 `container.textContent`——不是原始碼字面比對，所以檔案
 * 內部的中文技術註解（例如解釋為什麼要移除「候選池」這個詞）本來就
 * 不會被這份清單命中；`placeholder` 也一樣，`<input placeholder="…">`
 * 是屬性、不進 DOM 文字節點，這裡真正要抓的是「畫面文字本身寫了
 * placeholder 這幾個英文字母」這種殘留占位文案，不是合法的 input 提示。
 *
 * 刻意不掃描的範圍（既有裁示，見各票 CLAUDE.md checkpoint／commit）：
 * `SuperUserAdmin.tsx`（Super Admin 專用內部維運面板，不是一般使用者
 * 畫面）、`RawData.tsx`／`Diagnostics.tsx`（逐字顯示後端原始欄位名稱
 * 是這兩個元件存在的目的本身，不是漏改的術語）、`AnalysisReport.tsx`
 * 的「Model & Assumptions」技術揭露區塊（`q_source` 等欄位值本來就是
 * 逐字顯示的模型參數來源，同一套理由）。
 */
export const BANNED_JARGON = [
  "vendor", "Vendor",
  "候選池", "pool", "Pool",
  "口徑",
  "限流事故",
  "規劃中",
  "placeholder",
] as const;
