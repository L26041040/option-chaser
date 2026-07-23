# ui_reference/ — 原始 Artifact 匯出（未整合、未重建）

## 來源

- Artifact 連結：https://claude.ai/code/artifact/bca2c75f-453c-40f0-9c56-d726b17b3d69
- 標題：`Option Chaser v5 — 即時資料驗證快照`
- 擁有者：你本人的 claude.ai 帳號（owned by you）
- 匯出方式：透過 WebFetch 直接取得該 URL 的完整原始回應（非「轉 markdown 摘要」路徑——
  claude.ai/code/artifact/{uuid} 這類連結會回傳未經摘要處理的原始 HTML），存成本機檔案後
  以 `sha256sum` 核對，逐位元組複製進本目錄，**未手動編輯任何一個字元**。
- 匯出時間：本次對話當下（2026-07-23）。
- 檔案：`index.html`（56,616 bytes，sha256
  `f7c696c70a3a499d77d630eea790f3085b9ee4b693179853e189f04642082f77`）。

## 這份 Artifact 實際的技術構成（誠實記錄，不是我的猜測）

用 `grep` 對 `index.html` 掃描過所有 `<link>`、`<script src=...>`、`<img src=...>`、
`url(...)`、`@font-face`、任何 `http(s)://` 參照，結果：

- **沒有任何外部資源**——沒有 CDN script、沒有外部 CSS、沒有外部字型、沒有圖片。
- 唯二出現的網址是 `https://claude.ai` 與 `https://preview.claude.ai`，且只出現在內嵌
  `<script>` 裡的一個 JS 陣列字面值（postMessage 的允許來源白名單），不是資源載入。

也就是說，這份「Artifact」**本身就是單一一份自包含的靜態 HTML 檔**：

```
index.html
├── <head><style>...</style></head>   ← 全部 CSS 內嵌，:root CSS 變數 token 見下方
└── <body>
    ├── <script>...</script>          ← claude.ai 平台的 iframe 沙盒/訊息橋接注入碼
    │                                    （下方「重要說明」有解釋，非本 app 的程式碼）
    └── 純 HTML：header/window/table/details 等靜態標記 + 少量 <style> 定義的
        互動樣式（<details>/<summary> 折疊區塊，屬瀏覽器原生行為，非 JS）
```

**沒有 `package.json`、沒有 lockfile、沒有 `components/` 目錄、沒有建置流程、沒有前端框架
（不是 React／Vue／Svelte）**——不是我省略沒匯出，是這份 Artifact 打從一開始就不是用那種
方式做的。你要的「components、styles、assets、package.json 與 lockfile」在這份 Artifact
裡除了 styles（內嵌在 `<style>` 裡）之外，其餘都不存在，因此無法匯出不存在的東西。若你原本
預期這是一個有元件化前端專案結構的 Artifact，可能記錯了是哪一份，或者這份本來就只是純
HTML mockup（用途是「即時資料驗證快照」——把三個真實劇本的計算結果貼進去人工核對數字，
不是要交付的產品前端）。

## 重要說明：`<script>` 區塊是什麼

`index.html` 開頭那大段被壓縮（minified）的 `<script>`，是 **claude.ai Artifact 平台自己
注入的 iframe 沙盒／訊息橋接執行期**（scroll 還原、RTC 鎖定、`postMessage` 能力代理等），
掛在 `window.__FRAME_PREAMBLE` 上——每一份 claude.ai Artifact 被渲染時都會被包這一層，
與這份 Artifact「作者」（也就是我，先前的對話）寫的內容無關，是平台基礎設施，不是
Option Chaser 的程式碼。**原樣保留**（未刪除、未修改），因為你要求「原樣匯出」；但如實
標註以免誤判成這份 mockup 本身用了什麼複雜前端執行期。

## 如何獨立啟動

不需要任何建置步驟、不需要 npm/node、不需要伺服器——就是一份靜態 HTML：

**方法一：直接用瀏覽器開檔**
```
直接雙擊 ui_reference/index.html，或在瀏覽器網址列輸入
file:///<repo 絕對路徑>/ui_reference/index.html
```

**方法二：用任意靜態伺服器（若要避免 file:// 的部分瀏覽器限制）**
```bash
cd ui_reference
python -m http.server 8899
# 瀏覽器開 http://localhost:8899/
```

已用隔離的 headless Chromium（gstack browse，非你的真實瀏覽器）以 `file://` 直接開啟
本目錄下的 `index.html` 實測一次，1280×2000 viewport，全頁正常渲染（見下方截圖），
沒有因為 iframe 沙盒腳本跑在非 iframe 環境下而報錯或白屏。

## 目錄樹

```
ui_reference/
├── README.md    ← 本檔
└── index.html   ← 原始 Artifact 全文，逐位元組複製，sha256 見上方
```

## 未整合聲明

本目錄**未與 `webapp/` 現有 Streamlit 程式碼做任何連接**，純粹作為視覺對照的原始真相
（ground truth）保留在 repo 中，供後續人工比對用。
