# S&P 500 成分股清單與股權類別代號（V2-01／#404）

機會搜尋的預設**掃描股票範圍**是 S&P 500 成分股。這份文件說明清單從哪裡來、
授權、怎麼更新、多久更新一次、差異報告長什麼樣子，以及股權類別代號在各資料
來源之間怎麼轉換。全部 US$0，不新增任何付費或執行期依賴。

## 1. 來源與授權

| 項目 | 內容 |
|---|---|
| 來源 | Wikipedia「[List of S&P 500 companies](https://en.wikipedia.org/wiki/List_of_S%26P_500_companies)」的成分股表格（`id="constituents"`） |
| 取得方式 | MediaWiki API（`action=query&prop=revisions`），一次請求取一個**固定版本**（revision id） |
| 授權 | 文字內容 CC BY-SA 4.0。repo 只收**代號與公司名稱**兩欄（事實性資料），檔頭寫明來源版本、網址與授權；該檔依同一授權提供（姓名標示：Wikipedia 貢獻者） |
| 費用 | US$0，不需要金鑰 |

**為什麼不用 ETF 發行商的持股檔**：iShares（IVV）、SPDR（SPY）、Vanguard（VOO）的
持股檔都是公開下載，但使用條款通常限制轉載與再散布，而且網址、格式常改，又含
現金與期貨列要另外過濾。Wikipedia 授權明確（允許再散布，只要標示來源並以同一
授權提供），格式是穩定的 wikitext 表格，而且 S&P 500 成分股異動時通常當天就有人
更新。代價是它不是 S&P Dow Jones Indices 的官方資料：更新工具每次都印出差異，
由人工確認後才 commit。

## 2. repo 內的清單

- 檔案：`api_app/sp500_constituents.py`（自動產生，勿手改）。用 Python 模組而不是
  JSON，確保 Vercel 的 Python 函式打包一定帶上它。
- 內容：`VERSION`（版本＝生效日期：取用的 Wikipedia 版本的編輯日期，UTC）、
  `SOURCE_REVISION`、`SOURCE_URL`（帶 `oldid` 的永久連結）、`RETRIEVED_AT`、
  `LICENSE`、`CONSTITUENTS`（`(代號, 公司名稱)`，依表格順序）。
- 目前版本：`2026-11-08`（revision 1384572480），503 檔。
- **執行期不連網**：網站掛了或改版，只是更新工具跑不動；線上系統照用 repo 裡的
  最後一版。設定頁顯示清單名稱、檔數與版本日期；機會搜尋頁的範圍卡與「資料
  狀態」顯示目前使用的範圍（S&P 500 另顯示版本日期）。

## 3. 更新方式與頻率

```bash
# 只看差異，不寫檔
SSL_CERT_FILE=/root/.ccr/ca-bundle.crt PYTHONPATH=. .venv/bin/python \
    scripts/update_sp500_constituents.py --dry-run
# 取最新版、寫檔、印差異
SSL_CERT_FILE=/root/.ccr/ca-bundle.crt PYTHONPATH=. .venv/bin/python \
    scripts/update_sp500_constituents.py
```

- 可以重跑：沒有異動時差異是「新增 0 檔／移除 0 檔」，檔案只換 `RETRIEVED_AT`
  （以及版本，如果頁面有其他編輯）。
- 安全檢查：找不到成分股表格、檔數不在 490–520、代號重複、代號不是
  canonical 格式（1–5 個大寫字母，可接 `.` 加一個字母）——任一項不過就整個停下、
  不寫檔。
- 頻率：**每季一次**，在 S&P 季度調整生效（3、6、9、12 月第三個週五之後的
  週一）後執行；另外遇到臨時成分股異動（併購、下市）時手動執行。commit 前人工
  看過差異報告（例如對照 S&P Dow Jones Indices 的公告）。
- 更新後跑 `tests/test_sp500_constituents.py`、`tests/test_search_universe.py`。
  `REFRESH_PRIORITY`（下面第 6 節）必須全是成分股，有測試守門；移除的成分股如果
  在裡面，要一起換掉。

## 4. 差異報告格式

純文字，依代號排序：

```
S&P 500 成分股：2026-11-08（rev 1384572480） → 2026-12-22（rev 1390000000）
檔數：503 → 503
新增 1 檔：
  + XYZ  Example Corp.
移除 1 檔：
  - ABC  Old Company Inc.
```

## 5. 股權類別代號

S&P 500 有幾家公司掛兩種股權類別（GOOGL／GOOG、FOXA／FOX、NWSA／NWS、BRK.B、
BF.B）。**兩種類別各自是一檔股票**，各自查分析師資料、各自查選擇權。

唯一的對照規則在 `option_chaser/symbols.py`：

| 用途 | 寫法 | 例 |
|---|---|---|
| canonical（設定、共識快取、劇本、搜尋結果、成分股清單） | 點 | `BRK.B` |
| Cboe 延遲報價 | 點（與 canonical 相同） | `BRK.B` |
| Yahoo quoteSummary／chart／v7 options、yfinance、Yahoo 配息 | 連字號 | `BRK-B` |

- 系統內部只存 canonical。使用者輸入 `BRK-B`、`brk/b` 一律正規化成 `BRK.B`
  （自訂清單、劇本建立、共識詳細頁、更新重試、搜尋的 `symbols`）。
- 只有組上游 URL 的那一刻才換寫法；回傳的資料（分析師紀錄、選擇權快照）一律
  掛回 canonical。
- 2026-11-24 實測：Yahoo `BRK.B`、`BF.B` 回 404，`BRK-B`、`BF-B` 回 200。真實
  回應錄成 `tests/fixtures/yahoo/BRK-B.*`、`BF-B.*`，測試用它們回放。
- Cboe 的 `BRK.B` 寫法沒有實測過（沙箱連 Cboe 一律被 Cloudflare 擋 403）。依
  Cboe 網站的寫法採用點；如果 Cboe 不認，降級鏈會接著用 Yahoo `BRK-B`，劇本
  照樣拿得到報價。
- V2-01 之前存下的自訂清單若有 `BRK-B`，讀取時就當成 `BRK.B`（不回寫）。
- 範圍：美國掛牌普通股。Yahoo 對非美國交易所用 `.T`、`.DE` 這類後綴，不在支援
  範圍內。

## 6. 舊設定遷移與每日更新上限

- 原「大型股樣本」（`sample-large-cap`，約 50 檔暫定清單）**退役**，不再是選項。
  - 存著 `sample-large-cap` 的舊設定：讀取時一律當成 `sp500`（不回寫）。SU/SA 的
    門檻、策略、排序、自訂清單都不受影響。
  - 舊前端送 `sample-large-cap`：接受，存成 `sp500`。
- 那 50 檔改當 `REFRESH_PRIORITY`：每日分析師資料更新**仍有 200 檔上限**
  （`DEFAULT_REFRESH_SYMBOL_CAP`，本票不改），名額依序給：
  1. `REFRESH_PRIORITY` 50 檔；
  2. SU/SA 的自訂清單（canonical、依代號排序）；
  3. 其餘成分股（清單順序）。
- 所以預設範圍的 503 檔裡，約 300 檔目前列為「超出每日更新範圍」
  （`out_of_scope`），畫面照實顯示，不算「建立中」。每日約 500 檔的排程、額度與
  輪替是 **#403** 的工作；`resolve_universe()` 已經交出完整的成分股清單，#403 只要
  調整更新母體與上限即可。
