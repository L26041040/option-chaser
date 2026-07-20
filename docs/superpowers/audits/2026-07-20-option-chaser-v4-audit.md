# Option Chaser v4 — Codex Independent Audit (DC→AC→SL)

日期：2026-07-20
對象：master 3385953（v4 merge）
權威文件：`docs/superpowers/specs/2026-07-20-option-chaser-v4-design.md`（含附錄A）
計劃：`docs/superpowers/plans/2026-07-20-option-chaser-v4.md`
覆蓋契約：spec §7A（設計期凍結，codex 於 spec 審核時核可）

## 覆蓋契約（自 spec §7A 轉錄）

- **DC**：乾淨安裝；scenarios.py/glossary.py import；說明頁檔案存在；3.11/3.13 corner。
- **AC**：全套件 codex 親自跑；七情境 marching walk（每情境一項獨立重算比對）；保本門檻獨立驗證（codex 以自寫掃描重算 k* 並核後綴條件）≥2 案例；分組抽樣規則重現；標章判定矩陣；新 golden 逐位元；紅線掃描（機率語彙+GUI零公式+無分數函數）；縮圖降採樣索引驗證。（附錄A：非單調價差案例由合成接縫測試＋四策略後綴測試取代。）
- **SL**：真實 TLT GUI 路徑（含 expiry_groups 非空、標章存在、主視圖預設無⚠）；同快照 CLI 重跑韌性向量數字一致；Docker compose up + 容器內同快照分析一致。無法執行處依 skill 處方模式，不得豁免。

## 閘門紀錄

### DC — PASS（round 4 判定）
- codex 沙盒無 Python（AppData 隔離）→ 改用 Program Files 之 3.13.9；pgAdmin Python 無 venv、沙盒無網路 → 處方模式：控制器逐字執行 codex 腳本。
- prefix 模式 editable 安裝 `.[gui]`+pytest 成功；`.audit-py` 嵌入式直譯器（自製 `_pth`）；compileall 乾淨；scenarios/glossary import ok；CLI --help ok；JSON fixtures 全 parse；3.13 corner 實測。
- 首輪 pytest 收集失敗判定為 audit 環境 bootstrap 產物（子行程不繼承 prefix path），非產品分歧；修訂腳本後收斂。

### AC — PASS（round 4 判定）
- 全套件 177 tests 於 codex 處方之 3.13 嵌入式直譯器全數通過（transcript 點陣 177、零 F/E）。
- codex 親自執行（自己沙盒內、CLI/引擎直呼）：七情境 marching walk（LC 90/2026-11-20 與 BCS 110/130/2026-10-16，S1-S7 全吻合）；保本門檻自寫掃描重算（LC (0.012, 100.24)、BCS (0.445, 108.90)，後綴性質驗證）；分組抽樣/注入/全警示 fallback 重現吻合；四份 golden 逐位元＋決定性雙跑；紅線掃描（禁詞/GUI零公式/無分數函數）乾淨；縮圖索引 [10,7,4,1]×[0,1,3,5,6] 驗證。
- 附錄A 替代鎖定（合成接縫測試＋四策略後綴測試）依修訂契約驗收。

### SL — PASS（round 9 判定）
- Round 5 首跑（盤前 08:19 ET）：LEAPS 全數被報價異常濾除 → guard path 正確觸發；codex 裁定非產品分歧（市場時段資料條件）。Round 7（開盤後 5 分鐘 09:35 ET）同況——對照週日快照（182/186 檔 LEAPS 有報價）證實為開盤初期造市報價未鋪滿。
- Round 8-9 依 codex 處方之 bounded retry（23:00 台北＝11:00 ET 首試即過）：
  - (a) 真實 TLT 線上路徑：3 個到期組（2028-01-21/06-16/12-15）、標章齊備、default = BCS 100/130 2028-06-16 無⚠。
  - (b) 同快照 CLI 韌性向量 parity：腳本內逐策略斷言通過。
  - (c) Docker 容器內同快照 parity：結構完全一致（default/6列/代號零差）；42 個數值 22 個有跨平台漂移、全部 <1e-12（max 9.5e-13）；使用者可見 1 位小數呈現零差異。codex 裁定 PASS。
- 控制器提出之 harness 修正兩項被 codex 採納：tuple/list JSON round-trip 假性失敗（round 4）；診斷腳本免斷言 dump（round 8）。

## 最終判定（round 9）

**CONFORMANT** — DC PASS / AC PASS / SL PASS。

紀錄事項（codex 原文）：
- Cross-platform Docker parity is accepted at structural identity plus user-visible numeric precision. Exact raw float identity is not required across MSVC/glibc libm.
- Exact same-platform CLI/golden determinism remains covered by AC.

獨立性紀錄：codex 沙盒無 Python/網路，DC 安裝與 AC 全套件、SL 全部走處方模式（codex 逐字開藥、控制器逐字執行、raw transcript+hash 回判）；AC 之七情境重算、保本門檻自寫掃描、分組/標章/golden/紅線/縮圖驗證由 codex 於自己沙盒內親自執行。降低之獨立性僅及於處方項的「執行」，判讀與重算全程 codex。

<!-- codex-audit: status=PASS gates=DC:PASS,AC:PASS,SL:PASS date=2026-07-20T15:04:14Z rounds=9 appeals=0 arbitrations=0 -->
