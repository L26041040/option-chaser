"""ScenarioResult 契約（spec §3）：`AnalysisResult` → View dict 的序列化層。

純函式、零 wall-clock（時間由呼叫端傳入）。持久化本身（把 View 寫進
Storage）是 `api_app/storage/` 的職責，這裡只負責形狀轉換。
"""
from __future__ import annotations

import dataclasses
from datetime import date
from typing import Iterable

from . import __version__
from .models import (AnalysisParams, ChainSnapshot, FAMILIES, STRATEGY_FAMILY,
                     derive_direction, family_eligibility)
from .ranking import baseline_return, butterfly_baseline_return, spread_baseline_return
from .report import disclaimer_text
from .scenarios import natural_cost
from .service import AnalysisResult, CandidateView, candidate_key, valuation_key
from .valuation import (ButterflyValuation, ContractValuation, SpreadValuation,
                        butterfly_guidance_judgments, guidance_judgments,
                        spread_guidance_judgments)


SCENARIO_SCHEMA_VERSION = 2   # v2: target_date（YYYY-MM-DD）→ target_month（YYYY-MM）

# SCALE-01（#252，Scaling Foundation Stage 1-0）：凍結「candidate-specific
# historical membership replay」語意的版本號——不是 `view["schema_version"]`
# （那個描述 view *形狀*）也不是 `engine_version`（描述引擎程式碼版本），
# 是描述「這一列歷史 fact 的 eligibility／filter／pair-validity 語意」。
# 目前唯一的消費者是尚未建立的 SCALE-09 candidate-specific resolver：
# 未來若 eligibility 規則改變（例如過濾門檻、pair validity 判準），
# resolver 必須依這個版本號決定怎麼重放舊資料，不得對所有既有列直接
# 套用新規則重新解讀（那會讓「當時到底發生了什麼」這個歷史事實跟著
# 現在的程式碼改變）。今天只有版本 1；SCALE-01 把它寫進每一列
# （新寫入與 backfill 皆同），版本本身尚未被任何邏輯讀取或分派。
HISTORY_REPLAY_VERSION = 1


def _candidate_of(view: dict, row: dict) -> dict | None:
    """T09（#191）：`expiry_groups[].rows[]` 現在存 `candidate_key`（新
    schema，`view["candidate_pool"]` 解出完整內容），不再直接內嵌完整
    候選字典。`representative_candidate()` 只在**剛做完**一次
    `serialize_result()` 的新鮮 view 上呼叫（never 讀舊存的 view——見
    `api_app/main.py` 唯一呼叫點緊接在 `_analyze()` 之後），所以理論上
    只會走新 schema 這條路；仍保留舊形狀（`row["candidate"]` 直接內嵌）
    的相容分支，供直接手造 view fixture 的既有測試與任何未來仍傳入舊
    形狀 view 的呼叫端使用，不因為結構改變而整組炸掉。"""
    if "candidate_key" in row:
        return (view.get("candidate_pool") or {}).get(row["candidate_key"])
    return row.get("candidate")


# ---------- ScenarioResult 契約（spec §3） ----------

def representative_candidate(view: dict | None) -> dict | None:
    """劇本清單卡片要的「代表候選」完整身分（MVP-v2／#77、#78）：策略、
    各腿履約價與權別、實際到期日、報酬率。

    候選來源與 `best_return()` 逐字相同、同一次走訪：baseline 期（最接近
    目標年月的到期日）在 `expiry_groups` 裡那一組的 `rows`，取
    `baseline_return` 最高者（QA1-03／#30 修好的那條規則）。

    刻意**不讀** `comparison`／`results`／`expiry_top10`：`comparison` 每筆
    是該策略在**全部到期日**裡的全域最佳（`_comparison()`），拿它當來源會
    讓「baseline 期」這個限定詞失效，等於讓 QA1-03 的舊 bug 在這一層重演。
    這裡只在 baseline 期那組 `rows` 內取最大值，不做任何金融計算、不牽動
    哪些策略／候選進得了排名——排名結果早由 `expiry_groups` 決定好了。

    baseline 期不在 `expiry_groups`、該期零合格候選、或 view 本身為
    `None`（無快照）→ `None`（附錄 A10.2／A12：綠燈＋「—」，不是一組
    假的候選）。

    腿的順序沿用序列化層既有慣例：`[0]=long`（買腿），`[1]=short`（賣腿，
    僅價差策略才有）；只回顯示要用的履約價與權別，不重複整份 `_leg()`
    （報價／IV／量能等欄位留在詳細頁的完整 view，這裡只是清單卡片用）。
    """
    if view is None:
        return None
    group = _baseline_group(view)
    if group is None or not group["rows"]:
        return None
    best_row = max(group["rows"],
                   key=lambda row: _candidate_of(view, row)["baseline_return"])
    return _project_representative_row(view, group, best_row)


def _baseline_group(view: dict) -> dict | None:
    """`representative_candidate()`／`representative_candidates_by_
    family()` 共用的同一次走訪起點——baseline 期（最接近目標年月的
    到期日）在 `expiry_groups` 裡的那一組。抽出來是 T07（#224）新增
    per-family 版本時發現的重複，不是新規則：兩個函式必須看到完全
    相同的候選池，才能保證「per-family map 取最大值後等於 scalar
    冠軍」這條一致性。"""
    return next((g for g in view["expiry_groups"]
                if g["expiry"] == view.get("baseline_expiry")), None)


def _project_representative_row(view: dict, group: dict, row: dict) -> dict:
    """把 baseline 期一列 row 投影成清單卡片要的輕量代表候選形狀——
    `representative_candidate()`／`representative_candidates_by_
    family()` 共用同一份投影邏輯，只是挑選 row 的分組粒度不同。

    OPTION-CHASER-CLOSEOUT-001（劇本庫卡片 champion 顯示一致性）：
    新增 `quantity` 投影——前端 `formatRepresentativeLegs()` 過去只用
    `findLeg()` 各抓一隻 buy／sell 腿畫成兩腿價差字串，對 Butterfly
    （三腿：買／賣 2 口／買）會靜默丟掉第二隻 buy 腿，讓三腿 champion
    在卡片上被顯示成看起來像舊 Vertical Spread 的兩腿組合——這正是
    「strategy 名稱正確、legs／strikes 卻對不上」的根因，不是兩個資料
    來源不同步。修法是前端改為逐腿列出（同一支 `rep` 物件、同一份
    `legs[]`），這裡補上 `quantity` 讓中腿的「2×」標示能與詳細頁
    `candidateTitle()` 同一套慣例。`leg.get("quantity", 1)` 對已存的
    舊 View（schema_version < 4，序列化當下還沒有這個欄位）回退預設
    值 1——既有已儲存的 View 不做資料遷移，讀取端維持相容（沿用
    T09／#191 當時定下的同一條規則，`side` 欄位已是同一種寫法）。"""
    candidate = _candidate_of(view, row)
    return {
        "strategy": row["strategy"],
        # T12（#228，Initial V2）：`side` 一併投影進這個輕量代表候選——
        # 前端 `formatRepresentativeLegs()` 過去靠陣列位置（[0]=買、
        # [1]=賣）猜方向，現在改讀這個顯式欄位。`leg.get("side", ...)`
        # 對已存的舊 View（schema_version < 4，序列化當下還沒有這個
        # 欄位）用位置回推當備援——既有已儲存的 View 不做資料遷移，
        # 讀取端維持相容（沿用 T09／#191 當時定下的同一條規則）。
        "legs": [{"strike": leg["strike"], "option_type": leg["option_type"],
                 "side": leg.get("side", "buy" if i == 0 else "sell"),
                 "quantity": leg.get("quantity", 1)}
                for i, leg in enumerate(candidate["legs"])],
        "expiry": group["expiry"],
        "baseline_return": candidate["baseline_return"],
    }


def representative_candidates_by_family(view: dict | None) -> dict:
    """T07（#224，Initial V2 spec #217）：Owner 裁示的「B 儲存＋A 顯示」
    ——顯示面本輪維持單一個跨 family 冠軍（`representative_candidate()`，
    T11 消費），但儲存面額外把每個 family 各自的代表候選與最高報酬也
    落盤，日後若要改成逐 family 顯示，不必回頭重新分析所有歷史結果。

    與 `representative_candidate()` **同一次走訪、同一個候選池**
    （`_baseline_group()`），只是改成先依 family（`STRATEGY_FAMILY`
    對照表，`row["strategy"]` 已經是具體 subtype 代碼）分組，各組
    各自取 `baseline_return` 最高者——不是另一套排名規則，純粹是
    分組粒度不同。

    一致性保證（AC 明文要求）：這份 map 裡的最高報酬取 `max()` 後，
    等於 `representative_candidate()` 的報酬——因為兩者是同一個候選
    池、同一個排序鍵，只是分組粒度不同：全池的最大值必然等於「各
    family 子池最大值」的最大值，這是 `max()` 對分割後子集合取最大值
    再取最大值的代數性質，不是需要另外維護的規則。

    baseline 期不在 `expiry_groups`、該期零合格候選、或 view 本身為
    `None` → 空 dict（與 `representative_candidate()` 回 `None` 同一種
    「沒有東西可顯示」，這裡回空 map 而非 `None`——呼叫端不必為了
    「完全沒有任何 family」多判斷一次 `None`，`{}` 本身已經自然表達
    「這裡什麼都沒有」）。"""
    if view is None:
        return {}
    group = _baseline_group(view)
    if group is None or not group["rows"]:
        return {}
    by_family: dict[str, list[dict]] = {}
    for row in group["rows"]:
        family = STRATEGY_FAMILY.get(row["strategy"], row["strategy"])
        by_family.setdefault(family, []).append(row)
    return {
        family: _project_representative_row(
            view, group,
            max(rows, key=lambda row: _candidate_of(view, row)["baseline_return"]))
        for family, rows in by_family.items()
    }


def best_return(view: dict | None) -> float | None:
    """baseline 期（最接近目標年月的到期日）本身的最高收益率——與 Step 2
    主圖同一口徑（QA1-03／#30：先前誤取全部到期日的全域最大值，較早到期日
    剛好報酬更高時卡片數字就會跟主圖對不上）。

    由 `representative_candidate()` 導出而非各走各的一次走訪
    （MVP-v2／#77、#78）：兩者必須在結構上不可能對不上，卡片上的報酬率
    才會永遠是它旁邊那組履約價真正算出來的數字。這是跨層一致性的
    canonical 規則——`api_app/main.py` 為了不重複走訪 `representative_
    candidate()` 而在呼叫端內聯同一條算式，不代表這個公開純函式本身
    是死碼（多處測試把它當獨立於呼叫端的真相來源做交叉驗證）。
    """
    rep = representative_candidate(view)
    return rep["baseline_return"] if rep is not None else None


def spot(view: dict | None) -> float | None:
    """這次分析當下的標的現價（`view["meta"]["spot"]`）。

    QA 修正：劇本庫卡片要顯示現價，才看得出「目標價／最高／最低離現在
    多遠」——沒有它，清單上一排目標價等於沒有比較基準。與 `best_return()`
    同一種角色：清單只要這一個數字，卻不該為它把整份 view 撈回來，所以
    落盤成獨立欄位；規則仍只有這一份純函式。

    view 為 `None`（從未成功分析過）或形狀不含 meta.spot（理論上不會，
    防禦性）時回 `None`——卡片據此顯示「—」，不是 0。
    """
    if not view:
        return None
    value = (view.get("meta") or {}).get("spot")
    return value if isinstance(value, (int, float)) else None


def _history_entry(sv: SpreadValuation | ContractValuation | ButterflyValuation,
                   expiry: str, rank_in_expiry: int) -> dict:
    """T9（#23，附錄A7）：全部有效候選的歷史五欄位之三（成本／收益率／期內
    名次）；另外兩欄（更新時間、標的價）不逐候選重複，共用父層 `analyzed_at`／
    `meta.spot`（既有設計，`_candidate()` 對完整 CandidateView 同樣不重複）。
    不建 CandidateView：這裡只需要輕量欄位，沒有 Heatmap 矩陣（附錄A10.3）。

    T09（#222）：單腿路徑的 `expiry_ranked` 過去恆空，本函式只被 Spread
    呼叫過——`baseline_return` 因此原本直接寫死 `spread_baseline_return`。
    單腿路徑補上 `expiry_ranked` 後同一個函式要能吃 `ContractValuation`，
    改用既有的 `ranking.baseline_return`（單腿口徑：`(baseline_value -
    ask) / ask`，附錄 A14.2），`natural_cost`／`valuation_key` 本來就是
    對兩種型別皆已定義的既有多型函式，不必跟著改。

    T15（#230，Initial V2）：Butterfly 的 `expiry_ranked` 從第一天就會
    非空（AC「歷史身份列從第一天就落盤」）——這裡加第三個分支即可，
    `natural_cost`／`valuation_key` 早已支援 `ButterflyValuation`。"""
    if isinstance(sv, SpreadValuation):
        ret = spread_baseline_return(sv)
    elif isinstance(sv, ButterflyValuation):
        ret = butterfly_baseline_return(sv)
    else:
        ret = baseline_return(sv)
    return {
        "candidate_key": valuation_key(sv),
        "expiry": expiry,
        # T12（附錄A14.2）：成本口徑統一走 natural_cost（＝最差成交假設），
        # 與 `_candidate()` 的 `natural_cost`／`cap_per` 同一條路徑，不直接
        # 讀 `sv.net_worst`（spread 之下數值恆等，但少一層轉譯依賴）。
        "cost": natural_cost(sv),
        "baseline_return": ret,
        "rank_in_expiry": rank_in_expiry,
    }


def _leg(c, side: str, quantity: int = 1) -> dict:
    """T12（#228）：`side`（"buy"／"sell"）與 `quantity`（口數）現在是
    每一腿自己攜帶的顯式欄位，取代「腿在陣列裡的位置＝買賣方向」這個
    只對兩腿策略成立的隱性慣例——呼叫端（`_candidate()`）本來就知道
    每條腿的方向與口數，這裡只是把它序列化出來。既有兩腿策略維持
    `quantity=1`（既有預設值），數值本身完全不變。"""
    return {"contract_symbol": c.contract_symbol, "option_type": c.option_type,
            "strike": c.strike, "expiry": c.expiry, "bid": c.bid,
            "ask": c.ask, "iv": c.implied_volatility, "volume": c.volume,
            "open_interest": c.open_interest, "side": side, "quantity": quantity}


def _validate_leg_count(legs: list) -> None:
    """T12（#228）：candidate 契約的容量邊界——`1 <= len(legs) <= 4`。

    這是共用骨架明訂的 canonical boundary，不是留在註解裡的一句提醒：
    `len(legs) > 4` 或 `len(legs) == 0` 一律 validation fail。4 腿只是
    contract／data-shape 容量，Initial V2 本輪不啟用任何四腿 strategy
    （Iron 系列等一律 out of scope，#217），今天實際只會產生 1 或 2 腿；
    這個函式獨立成型別好讓「邊界會不會真的擋下不合法輸入」可以脫離引擎
    直接測試——引擎今天結構上不會產生 0 或 5+ 腿，所以這條邊界靠的是
    這個函式本身被直接呼叫測試，不是靠引擎湊出一個真實的違規案例。"""
    if not (1 <= len(legs) <= 4):
        raise ValueError(
            f"候選腿數必須介於 1 到 4 之間（contract 容量上限），"
            f"實際 {len(legs)}")


def spread_cost_history(views: Iterable[dict], candidate_key: str) -> list[dict]:
    """V9（#57）：跨一個劇本的全部歷史快照（序列化 view dict），依 Spread
    身份鍵（`candidate_key`，已含策略／買賣履約價／到期日，見
    `service.valuation_key`）聚合出時間序列。

    與 Streamlit 版 `workspace.spread_history()`（T11／#25）同一套語意，
    只是輸入從「讀檔案路徑」換成「呼叫端已經備妥的 view dict 序列」——
    新架構（`api_app`）的 `Storage.result_history()` 回傳的是
    `ResultRecord`（`.view` 已經是這個形狀），沒有檔案路徑可讀；
    `workspace.spread_history()` 改為委派本函式，兩邊共用同一份邏輯。

    唯讀聚合：只讀 view dict，不寫入、不改變任何計算或保存範圍。某次
    快照的 `all_candidates` 找不到這個鍵（該候選當次不是有效候選，例如
    缺報價被過濾）→ 該筆仍然入列，但 cost／baseline_return／
    rank_in_expiry 皆為 None：如實呈現斷點，不插值、不跳過、不報錯；
    `analyzed_at`／`spot` 仍取自那次成功更新本身。範圍限定 Spread 路徑
    （`all_candidates` 只有 spread 策略填入，T9 附錄A13 既有 MVP 範圍）。
    """
    out = []
    for view in views:
        entry = next((e for r in view["results"]
                     for e in r.get("all_candidates", [])
                     if e["candidate_key"] == candidate_key), None)
        out.append({
            "analyzed_at": view["analyzed_at"],
            "spot": view["meta"]["spot"],
            "cost": entry["cost"] if entry else None,
            "baseline_return": entry["baseline_return"] if entry else None,
            "rank_in_expiry": entry["rank_in_expiry"] if entry else None,
        })
    return out


def raw_snapshot_json(snap: ChainSnapshot) -> dict:
    """V8（#56）：原始資料（當次快照）——「免得你亂掰我卻查不到證據」
    （QA1-10／#37 原話，延續同一設計目標）。刻意不重用 `_leg()`：那個
    子集是候選腿專用的顯示欄位（省略 `last`），這裡要的是**逐筆合約的
    完整原樣**，跟 CSV 下載（`data.snapshot.snapshot_to_csv`）給的是同一
    份資料、同一組欄位，兩者不該對不上。"""
    return {
        "meta": {"symbol": snap.symbol, "spot": snap.spot,
                 "fetched_at": snap.fetched_at, "source": snap.source,
                 "contract_count": len(snap.contracts)},
        "contracts": [dataclasses.asdict(c) for c in snap.contracts],
    }


# T14（#233，Initial V2，研究 #216 定案的「組合一」）：格值捨入的小數
# 位數。畫面顯示（`formatCell()`）只到整數百分點（fraction 粒度
# 0.01），這裡捨入到 0.0001——比顯示精度細 100 倍，純粹省 JSON 文字
# 位元組，不會造成任何看得到的格值差異。
#
# ⚠ CLOSEOUT-004（PR #250 review Finding 2）更正：這裡原本還寫著
# 「`crossoverEdges()` 這類逐格比較的前端純函式容忍度（多個百分點
# 量級）也遠粗於這個捨入誤差」——**那句是錯的**。`crossoverEdges()`
# 沒有容忍度，它做的是精確的正負號比較，捨入誤差因此足以改變它的
# 答案（實測 6/6 候選的邊界集合都變了）。comparator 那一側的序列化
# 因此改走 `_comparator_matrix_to_dict()`，見該函式 docstring。
MATRIX_CELL_DECIMALS = 4


def _matrix_to_dict(mv, axis_of) -> dict:
    """`MatrixView`／`ComparatorView.matrix` 共用的序列化形狀——#115 前
    只有 `CandidateView.matrix` 用得到，抽成小函式避免 comparator 的
    matrix 另外複製一份同樣的三行。

    T14（#233）：座標軸（`prices`／`dates`）不再逐候選內嵌，改由呼叫端
    傳入的 `axis_of(mv)` 去重後回傳索引（見 `serialize_result()` 裡的
    `axis_pool`／`axis_sets`）——同一個 scenario 內大量候選共用同一組
    座標（150 候選實測僅 10 組相異軸，見研究 #216），這是壓縮的主要
    來源。`cells` 攤平成一維陣列並捨入，恢復成二維要靠 `axis_sets
    [axis_index].dates` 的長度切分，前端 `resolveMatrix()` 負責這一步
    （純解碼，不是計算）。"""
    return {"axis_index": axis_of(mv),
           "cells": [round(v, MATRIX_CELL_DECIMALS)
                    for row in mv.cells for v in row]}


# 捨入網格的一格（1e-4）。`_comparator_matrix_to_dict()` 用它把符號被
# 捨掉的格子推回正確的一側。
_MATRIX_CELL_STEP = 10.0 ** -MATRIX_CELL_DECIMALS


def _sign(x: float) -> int:
    return (x > 0.0) - (x < 0.0)


def _comparator_matrix_to_dict(mv, base_mv, axis_of) -> dict:
    """Comparator matrix 的序列化——與 `_matrix_to_dict()` 同形狀，但額外
    保證一條不變量：

        逐格 `sign(序列化候選值 − 序列化 comparator 值)`
             == `sign(引擎精確候選值 − 引擎精確 comparator 值)`

    OPTION-CHASER-CLOSEOUT-004（PR #250 review Finding 2）：兩個矩陣
    先各自獨立捨入到 `MATRIX_CELL_DECIMALS`，前端 `crossoverEdges()`／
    `crossoverFavoredSide()`／`crossoverSides()` 再對捨入後的值做**精確
    的正負號**判斷——`|a−b|` 小於捨入誤差（≤1e-4）時，兩個真的不相等的
    值會被捨成相同的數字，`sign()` 因此變成 0，跟兩側的非零符號都不同，
    憑空製造出一條 crossover 邊界；反過來也可能把真的邊界抹掉。實測
    （`xyz_v4_six_expiries` bull-call-spread、`xyz_v5_put_ladder`
    bear-put-spread 兩份 fixture）**6/6 有 comparator 的候選 edge 集合
    都改變**：例如 bull-call-spread 精確 17 條、捨入後 20 條（抹掉 2 條
    真的、生出 5 條假的），成因逐格核對是真差 4.4e-05／1.9e-05／1.3e-06
    這類被捨成 0 的格子。

    修法刻意選最小的一種：**不取消 matrix 壓縮、不改契約形狀、不改前端**
    ——crossover 三個消費端全都只讀「差值的正負號」（`comparator` 的格值
    本身從不顯示在畫面上，`Heatmap.tsx` 只顯示候選自己的 matrix 與
    comparator 的標籤／成本），所以只要序列化時保住那個正負號就夠了。
    符號被捨錯的那些格子，把 comparator 值改成候選值的正負一格
    （±1e-4），偏離真值最多 ~1.5e-4——而這個數字結構上不會被顯示，
    顯示精度（整數百分點）比它粗兩個數量級。

    副作用（已知、可接受）：推動後的值可能微幅落在物理可達範圍之外
    （例如報酬率 -1.0 被推成 -1.0001，「賠超過 100%」）。之所以可
    接受，正是因為這個欄位唯一的用途就是跟同一格的候選值比大小——
    它不是拿來給人看的數字，它是一個比較的參照點。
    """
    # 形狀不符時 `zip()` 會靜靜截短，序列化出一個比較短的 `cells`，
    # 前端 `resolveMatrix()` 依日期數切回二維時會整個錯位——寧可在這裡
    # 大聲失敗。#116 既有保證兩者同一組 price×date 座標，這條斷言是
    # 那個保證真的壞掉時的哨兵，不是預期會發生的情況。
    assert [len(r) for r in base_mv.cells] == [len(r) for r in mv.cells], (
        "候選與 comparator 的 matrix 形狀不一致（#116 保證應為同一組座標）")
    cells: list[float] = []
    for base_row, cmp_row in zip(base_mv.cells, mv.cells):
        for a, b in zip(base_row, cmp_row):
            ra = round(a, MATRIX_CELL_DECIMALS)
            rb = round(b, MATRIX_CELL_DECIMALS)
            want = _sign(a - b)
            if _sign(ra - rb) != want:
                rb = (ra if want == 0
                     else round(ra - want * _MATRIX_CELL_STEP,
                                MATRIX_CELL_DECIMALS))
            cells.append(rb)
    return {"axis_index": axis_of(mv), "cells": cells}


def _candidate(cv: CandidateView, strategy: str, capital: float | None,
               today: date, anchor: date, p: AnalysisParams, axis_of) -> dict:
    v = cv.valuation
    # T15（#230，Initial V2）：Butterfly 的 `max_loss_per_contract` 可能
    # 不等於進場成本（broken-wing 組合，見 `ButterflyValuation.max_loss`
    # 欄位註解）——`max_loss_override` 非 None 時取代下面 `cap_per` 當
    # `max_loss_per_contract` 的值；既有兩個型別維持 `None`（該欄位
    # 恆等於 `cap_per`，既有不變量不變）。
    max_loss_override = None
    if isinstance(v, SpreadValuation):
        # T12（#228，Initial V2）：`side` 現在顯式標在每一腿上（見
        # `_leg()`），不再只靠陣列位置暗示——position [0]=long/buy、
        # [1]=short/sell 這個既有慣例本身不變，只是現在同時也寫進資料裡。
        legs = [_leg(v.long_leg, "buy"), _leg(v.short_leg, "sell")]
        mid_cost, expiry = v.net_mid, v.long_leg.expiry
        max_profit, net_delta = v.max_profit, v.net_delta
        guidance_warnings = spread_guidance_judgments(v, p)
        breakeven_points = [v.breakeven]
        breakeven_scalar = v.breakeven
    elif isinstance(v, ButterflyValuation):
        # T15（#230）：買 1／賣 2／買 1，`_leg()` 的 `quantity` 參數把
        # 中腿的口數顯式標出來——取代既有「陣列位置＝方向」慣例（T12）
        # 的延伸：陣列位置現在還多了「中間那個是賣兩口」這件事。
        legs = [_leg(v.low_leg, "buy"), _leg(v.mid_leg, "sell", quantity=2),
               _leg(v.high_leg, "buy")]
        mid_cost, expiry = v.net_mid, v.low_leg.expiry
        max_profit, net_delta = v.max_profit, v.net_delta
        guidance_warnings = butterfly_guidance_judgments(v, p)
        breakeven_points = list(v.breakeven_points)
        max_loss_override = v.max_loss
        # 既有純量 `breakeven` 欄位（前端 `AnalysisReport.tsx` 仍讀它）
        # 沒有對應到 Butterfly 的單一自然定義——用較低的那個損益兩平點
        # 當代表值（與 `service._comparison()` 的 `ComparisonRow.
        # breakeven` 同一個選擇），沒有損益兩平點（到期時任何價位都
        # 無法獲利）時誠實給 `None`，不假造一個數字。
        breakeven_scalar = breakeven_points[0] if breakeven_points else None
    else:
        legs = [_leg(v.contract, "buy")]
        mid_cost, expiry = v.mid, v.contract.expiry
        # 與 service._comparison 相同定義（long-call 無上限 → None）
        max_profit = (None if strategy == "long-call"
                      else v.contract.strike - v.contract.ask)
        net_delta = v.delta
        guidance_warnings = guidance_judgments(v, p)
        breakeven_points = [v.breakeven]
        breakeven_scalar = v.breakeven
    _validate_leg_count(legs)
    # T12（附錄 A14.2，MVP-v2 舊票，非本輪 #228）：資本／最大虧損以
    # 最差成交成本計（natural_cost 即買 Ask／賣 Bid 口徑）；mid_cost
    # 保留為次要顯示欄位。
    cap_per = natural_cost(v) * 100
    max_loss_per_contract = (max_loss_override * 100
                             if max_loss_override is not None else cap_per)
    return {
        "candidate_key": candidate_key(cv),
        "strategy": strategy,
        # T12（#228，Initial V2）：AC「每個候選帶著它實際的 subtype 代碼」
        # ——`strategy` 這個既有欄位本來就已經是具體 subtype 字串（例如
        # "bull-call-spread"，不是 family 代碼；family→subtype 展開在
        # T06／#221 的 `api_app/main.py` 那一層就完成了，`AnalysisRequest.
        # strategies` 與這裡的 `strategy` 參數從頭到尾只認識 subtype）。
        # 不新增一個名字不同、值卻恆等的 `subtype` 欄位——那是無意義的
        # 重複概念，用測試鎖住這個事實即可（見
        # tests/test_candidate_leg_skeleton.py）。
        "legs": legs,
        "mid_cost": mid_cost,
        "natural_cost": natural_cost(v),
        "baseline_pnl": cv.baseline_pnl,
        "baseline_return": cv.baseline_return,
        "scenario_vector": {"entries": [list(e) for e in cv.scenario.entries],
                            "worst_code": cv.scenario.worst_code,
                            "worst_return": cv.scenario.worst_return},
        "completion_curve": [list(e) for e in cv.completion_curve],
        "completion_prices": list(cv.completion_prices),
        "completion_threshold": cv.completion_threshold,
        "breakeven_at_target": cv.breakeven_at_target,
        # T15（#230，Initial V2）：非單調結構（Butterfly）的獲利區間——
        # 兩個邊界價，或 `None`（單調家族恆為 `None`；Butterfly 峰值
        # 都賺不回成本時也是 `None`，不是「沒算」）。與
        # `completion_threshold`／`breakeven_at_target`（單調家族的
        # 保本掃描單一數字）互斥出現，見 `service.CandidateView.
        # profit_region` 欄位註解。純加法。
        "profit_region": (list(cv.profit_region)
                          if cv.profit_region is not None else None),
        "retention": cv.retention,
        "buffer_days": cv.buffer_days,
        # MVP V3（#104，spec #102 決策 F）：`quote_warning`（選取閘門用的
        # 複合旗標）不對外序列化——只有 `wide_spread_warning`（僅
        # is_spread_wide）進契約，前端 UI 一律改接這個顯示旗標。
        "wide_spread_warning": cv.wide_spread_warning,
        # FB5-03（#64）：獨立欄位，不併進 wide_spread_warning——見 service.py
        # 的 CandidateView.monotonicity_warning 欄位註解。
        "monotonicity_warning": cv.monotonicity_warning,
        # #113（spec #117 contracts 表）：這組候選的估值是否經過 carry
        # 校準。False 時前端必須說得出「這組估值未經 carry 校準」。
        "carry_calibrated": cv.carry_calibrated,
        "theta_day_rate": cv.theta_day_rate,
        "vega_per_pt": cv.vega_per_pt,
        "decay_30d_return": cv.decay_30d_return,
        # MVP V3（#112，spec #102 決策 H）：這組候選實際用於估值的利率與
        # 年期——Analysis Report → Model & Assumptions 的 Rate used／
        # Tenor 兩項，取代原本只顯示「用了某條曲線」的模糊呈現。
        "rate_used": cv.rate_used,
        "rate_tenor_years": cv.rate_tenor_years,
        "net_delta": net_delta,
        "breakeven": breakeven_scalar,
        # T12（#228，Initial V2）：損益兩平的**傳輸格式**——共用骨架要
        # 能裝得下 1～2 個點。既有四策略一律是單點（純量 `breakeven`
        # 包成一元素陣列，數值逐位元不變，前端 `AnalysisReport.tsx`
        # 仍讀純量 `breakeven`，這是新增的傳輸容量，不是既有欄位的
        # 替代品）；T15（#230）Butterfly 用真正的損益兩平點填滿這個
        # 容量——這正是 T12 當初預留這個形狀時說的「產生第二個點的
        # 邏輯是 T15 的範圍」。CLOSEOUT-004（Finding 1）：Butterfly
        # 是 0～2 點——broken-wing 的翼外平台若本身就高於進場成本，
        # 那一側沒有由虧轉盈的價位，就只有一個真的損益兩平點（見
        # `valuation.ButterflyProfitRegion`）。
        "breakeven_points": breakeven_points,
        "max_profit": max_profit,
        "effective_leverage": v.effective_leverage,
        # V8（#56，spec R1 §4.2 A2）：買價指引天花板 L2/L3——純文字報告
        # 早就在印，只是沒進契約。單腿另有 L1（＝ `floor_value`，保守
        # 底線），本票依票上 A2 表只列的兩項不補 L1（v.l1 對單腿等於
        # `floor_value`，價差沒有 L1）。
        "l2": v.l2, "l3": v.l3,
        # V8：買 Ask 超過哪些天花板的警示文字（`valuation.guidance_
        # judgments`／`spread_guidance_judgments`，同一組門檻早就用來
        # 決定純文字報告的「- 警示: ...」行，這裡只是把回傳值序列化）。
        "guidance_warnings": guidance_warnings,
        # V8：評語「代價」（cons）——「優點」pros 依 R1 §4.2 C 裁示不補
        # 序列化（與關鍵指標表重複，見 CLAUDE.md V8 記錄）。
        "cons": list(cv.cons),
        # D1（#14）：Long Call 追平價格——None＝不適用（單腳）或無法計算
        # （同履約價 Call 報價缺失），render 層負責區分並顯示。
        "catchup_price": cv.catchup_price,
        # 檢視回饋：這個生成式的迴圈變數原本借用 `p`，跟本函式自己的
        # `p: AnalysisParams` 參數同名，在同一個函式體裡容易讓人誤讀成
        # 同一個東西（雖然 Python 3 生成式有獨立作用域，實際不會互相
        # 污染）。改用 `pt`（price point）避免這個混淆。
        "matrix": _matrix_to_dict(cv.matrix, axis_of),
        # #115（spec #117 §4）：Crossover 對照——None＝單腿候選（無意義）
        # 或買腿報價缺失（結構上不該發生的防禦性 case）。matrix 用同一個
        # `_matrix_to_dict` 序列化，跟主 matrix 同形狀。T14（#233）：
        # comparator 的 matrix 與候選自己的 matrix 是同一組 price×date
        # 座標（#116 既有保證），`axis_of()` 因此自然把兩者去重成同一個
        # `axis_index`，不需要另外處理。CLOSEOUT-004（Finding 2）：
        # comparator 的格值改走 `_comparator_matrix_to_dict()`——捨入
        # 必須保住逐格 `sign(候選 − comparator)`，否則前端的 crossover
        # 邊界會被捨入誤差改掉（見該函式 docstring 的實測數字）。
        "comparator": ({"option_type": cv.comparator.option_type,
                       "strike": cv.comparator.strike,
                       "expiry": cv.comparator.expiry,
                       "cost": cv.comparator.cost,
                       "matrix": _comparator_matrix_to_dict(
                           cv.comparator.matrix, cv.matrix, axis_of)}
                      if cv.comparator is not None else None),
        # spec §3 新增四組（乘除法與日期差，非估值邏輯）
        "capital_per_contract": cap_per,
        # V7（#55）：劇本區間三價位對照。兩端都沒設時是空陣列，呈現層據此
        # 不畫這一區（不是畫一個只有一格的表）。
        "price_ladder": [{"label": pt.label, "price": pt.price, "return": pt.ret}
                         for pt in cv.price_ladder],
        # 既有四策略：debit 恆等於成本（`cap_per`）。T15（#230）
        # Butterfly：不假設這條不變量成立——broken-wing 組合到期時可能
        # 損失超過已付權利金，`max_loss_override` 帶著這個結構自己
        # 算出的真實最壞損失（見上方 `ButterflyValuation.max_loss`
        # 欄位註解）。
        "max_loss_per_contract": max_loss_per_contract,
        "pct_of_capital": (cap_per / capital) if capital else None,
        # 參考日＝日曆錨點（附錄 A9）；年月本身不映射成任何一天。
        "days_to_target": (anchor - today).days,
        "days_to_expiry": (date.fromisoformat(expiry) - today).days,
    }


def _family_eligibility_map(target_price: float, spot: float) -> dict:
    """T08（#225，Initial V2）：全部 `FAMILIES` 各自的可選／不可選
    verdict，鍵是 family 代碼——`serialize_result()` 與（未來 T10 若
    需要）任何其他呼叫端共用同一份計算，不各自重算方向一次。

    `/code-review` Standards 軸提醒的隱性前提：呼叫端傳入的 `spot`
    必須是**這次分析當下**用的現價，與 `service._analyze()` 自己算
    `direction` 時用的 `snap.spot` 是同一個數字——今天恆成立
    （`AnalysisResult.meta.spot` 就是 `SnapshotMeta(spot=snap.spot,
    ...)`，見 `service.py`），但這是兩個模組各自獨立呼叫
    `derive_direction()` 才會浮現的跨模組前提，值得留一句話而不是
    讓它隱形。"""
    direction = derive_direction(target_price, spot)
    return {fam: dataclasses.asdict(family_eligibility(fam, direction))
           for fam in FAMILIES}


def serialize_result(result: AnalysisResult, scenario_id: str,
                     capital: float | None) -> dict:
    base = result.request.base_params
    today = result.today

    # T09（#191）：同一個 Candidate 過去在 `candidates`／`expiry_best`／
    # `expiry_top10`／`expiry_groups[].rows[]` 四個容器裡各自完整序列化
    # 一份（同一組合約在多個容器重疊出現時，最多重複 4 次）。現在集中
    # 存進 `candidate_pool`（單一頂層字典，鍵＝`candidate_key`，跨策略
    # 共用一份——`candidate_key` 本身已含策略前綴，天生跨策略不衝突），
    # 其餘四個位置一律只存 key 引用。`_candidate()` 的輸出對於同一個
    # `candidate_key` 是 container-invariant（不讀入選它的是哪個容器、
    # 第幾名、跟誰比較——`idx`／`n_pairs` 這類容器相依資訊只餵給
    # `CandidateView.pros`，而 `pros` 從不序列化進 View，見
    # `_candidate()` 逐欄核對），因此「由哪個容器第一個把它放進池子」
    # 不影響輸出內容，去重可以安全地只看 key。
    pool: dict[str, dict] = {}

    # T14（#233，Initial V2）：座標軸去重——與上面 `pool` 同一種模式
    # （見 `cand_key()`），鍵是 `(prices 的 tuple, dates 的 tuple)`，
    # 第一次遇到某組座標才序列化進 `axis_sets`，其餘候選改存索引引用。
    axis_pool: dict[tuple, int] = {}
    axis_sets: list[dict] = []

    def axis_of(mv) -> int:
        key = (tuple(mv.prices), tuple(mv.dates))
        idx = axis_pool.get(key)
        if idx is None:
            idx = len(axis_sets)
            axis_pool[key] = idx
            axis_sets.append({"prices": [list(pt) for pt in mv.prices],
                              "dates": [list(d) for d in mv.dates]})
        return idx

    def cand_key(cv, strategy) -> str:
        key = candidate_key(cv)
        if key not in pool:
            # V8（#56，spec R1 §4.2 A2）：`_candidate()` 現在還要算買價
            # 指引警示（`guidance_judgments`／`spread_guidance_judgments`），
            # 兩者只讀 `p.iv_shifts`，不讀 `p.strategy`——`base` 不必為
            # 每個 `r` 各自替換 strategy 也正確，跟既有 `base.anchor`
            # 的用法一致。
            pool[key] = _candidate(cv, strategy, capital, today, base.anchor,
                                   base, axis_of)
        return key

    def strat(r):
        return {
            "strategy": r.strategy, "status": r.status, "message": r.message,
            "n_qualified": r.n_qualified,
            # FB4-01（#60）：合約層級的抓到／通過筆數。不可由 `n_qualified`
            # 反推——spread 路徑的 `n_qualified` 是**配對數**
            # （`service._spread_result` 取 `pair_report.passed`）。
            "filter_report": ({"total": r.filter_report.total,
                               "passed": r.filter_report.passed}
                              if r.filter_report else None),
            "filter_stages": ([{"label": s.label, "removed": s.removed,
                               "filter_class": s.filter_class,
                               # T05（#226，Initial V2）：純加法——被這一關
                               # 剔除掉的候選身份範例，供診斷指認「是哪一組」。
                               "removed_examples": list(s.removed_examples)}
                               for s in r.filter_report.stages]
                              if r.filter_report else []),
            # FB5-04（#65，spec #61）：C 類品質標示在整個合格池裡的計數
            # （`filters.quality_flag_counts()`）——跟 `filter_stages`
            # （A／B 兩類「排除」）並排但語意不同，前端據此分開呈現。
            "quality_flags": [{"label": qf.label, "count": qf.count}
                              for qf in r.quality_flags],
            "pair_report": ({"total_pairs": r.pair_report.total_pairs,
                             "removed_sanity": r.pair_report.removed_sanity,
                             # T05（#226）：B 層淘汰數，配對單位，獨立於
                             # 既有的 removed_sanity（A 層／per-subtype
                             # 結構合法性）。
                             "b_layer_removed": r.pair_report.b_layer_removed,
                             # T05（`/code-review` Spec 軸回饋）：純加法——
                             # B 層剔除掉的配對身份範例（買腿／賣腿合約
                             # 代碼組成），供診斷指認「是哪兩腿」。
                             "b_layer_removed_examples":
                                 list(r.pair_report.b_layer_removed_examples),
                             "passed": r.pair_report.passed}
                            if r.pair_report else None),
            "candidates": [cand_key(cv, r.strategy) for cv in r.candidates],
            "expiry_best": [cand_key(cv, r.strategy) for cv in r.expiry_best],
            "expiry_counts": [list(e) for e in r.expiry_counts],
            # T9（#23）：各到期日自己的前十名（含 Heatmap 矩陣，供 T10 詳細頁）。
            # T09（#191）：`candidates`（完整內容）→ `candidate_keys`
            # （key 引用），完整內容改到頂層 `candidate_pool`。
            "expiry_top10": [{"expiry": exp,
                              "candidate_keys": [cand_key(cv, r.strategy)
                                                for cv in cvs]}
                             for exp, cvs in r.expiry_top10],
            # T9（附錄A7）：該次全部有效候選的歷史五欄位（不只入榜者）；
            # 更新時間／標的價共用父層 analyzed_at／meta.spot，不逐候選重複。
            "all_candidates": [_history_entry(sv, exp, rank)
                              for exp, ranked_group in r.expiry_ranked
                              for rank, sv in enumerate(ranked_group, start=1)],
            # T04（#188）：`report_text`／`methodology_text` 不再進 View
            # payload——前端 `src/` 對兩者皆零引用（`methodology_text`
            # 曾經宣告在契約型別裡，但既有測試明文斷言它從不被渲染）。
            # `report_text` 本身仍是引擎欄位（`StrategyResult.report_text`，
            # `option_chaser/cli.py` 的文字報告輸出直接讀 `res.report_text`，
            # 不經過這個序列化函式），只是不再複製進 View；
            # `methodology_text` 純粹是這裡的序列化產物，移除後
            # `methodology_lines` 這個匯入在本檔案已無他用，一併移除。
            # `disclaimer_text` 前端仍會渲染，維持不動。
            "disclaimer_text": disclaimer_text(),
        }

    def group(g):
        return {"expiry": g.expiry, "buffer_days": g.buffer_days,
                "hidden_count": g.hidden_count,
                # T09（#191）：`candidate`（完整內容）→ `candidate_key`
                # （key 引用）——這裡橫跨多個策略（同一到期日、不同
                # 策略各一列），`candidate_key` 本身跨策略不衝突，池子
                # 因此不必按策略分開。
                "rows": [{"strategy": row.strategy,
                          "badges": list(row.badges),
                          "candidate_key": cand_key(row.candidate, row.strategy)}
                         for row in g.rows]}

    all_quotes_filtered = bool(result.results) and all(
        r.status == "empty" and r.filter_report is not None and any(
            s.label == "報價異常" and s.removed >= 1
            for s in r.filter_report.stages)
        for r in result.results)

    m = result.meta
    results = [strat(r) for r in result.results]
    expiry_groups = [group(g) for g in result.expiry_groups]
    return {
        # T04（#188）：1→2——report_text／methodology_text 從每個策略的
        # 結果物件移除。T09（#191）：2→3——`candidates`／`expiry_best`／
        # `expiry_top10`／`expiry_groups[].rows[]` 四個容器裡的完整候選
        # 內容集中到新增的頂層 `candidate_pool`，四個位置一律只留 key
        # 引用。純資訊性欄位，讀取端不依它分派任何邏輯（見全文唯一引用
        # 點：test_store_serialize.py 的版本斷言）；既有已存的 View
        # （schema_version=1／2，仍是舊形狀）不做遷移，讀取端（`find_
        # candidate()`／`representative_candidate()`）維持相容分支。
        # T12（#228，Initial V2）：3→4——每一腿新增顯式 `side`／`quantity`
        # 欄位（取代「陣列位置＝方向」的隱性慣例）＋候選新增
        # `breakeven_points`（損益兩平的點集合傳輸格式，純加法，既有
        # `breakeven` 純量欄位不變）。純新增，讀取端無需相容分支——舊
        # View 沒有這兩個欄位，`representative_candidate()` 對缺欄位的
        # `side` 有位置回推備援（見上）。
        # T05（#226，Initial V2）：4→5——`pair_report` 新增
        # `b_layer_removed`／`b_layer_removed_examples`，`filter_stages`
        # 每一關新增 `removed_examples`（皆純加法，`/code-review` Spec
        # 軸回饋補上——診斷需要指認「是哪一組」，不是只有計數）。
        # T08（#225，Initial V2）：5→6——新增頂層 `family_eligibility`
        # （純加法）。
        # T14（#233，Initial V2，研究 #216 定案的「組合一」）：6→7——
        # 熱力圖 matrix 傳輸壓縮，這次是**破壞性**改變既有欄位形狀
        # （非純加法）：候選的 `matrix`／`comparator.matrix` 從內嵌完整
        # `{prices, dates, cells}` 改成 `{axis_index, cells}`（`cells`
        # 攤平成一維陣列＋捨入到 `MATRIX_CELL_DECIMALS` 位），座標軸
        # 集中存進新增的頂層 `axis_sets`（去重，見 `axis_of()`）。舊存
        # 的 View（schema_version < 7）沒有 `axis_sets`，前端
        # `resolveMatrix()` 讀不到座標軸會顯示「無法解析」而不是誤讀
        # 出錯誤的圖——這與 T09（#191）當時「既有已儲存的 View 不做
        # 資料遷移」的既有裁示一致，下一次刷新就會拿到新 schema。
        # T15（#230，Initial V2）：7→8——候選新增 `profit_region`
        # （純加法，非單調結構的獲利區間，見 `CandidateView.
        # profit_region` 欄位註解）；`legs[].quantity` 首次出現大於 1
        # 的真實值（Butterfly 中腿賣 2 口）——欄位本身在 T12（#228）
        # 就已存在，這裡只是第一次真的用到，不是新增欄位，因此本身
        # 不構成版本升版理由，`profit_region` 才是。
        # OPTION-CHASER-CLOSEOUT-001（Scenario Detail 補劇本摘要）：
        # 8→9——新增頂層 `direction`（純加法，比照 T08／#225 的
        # `family_eligibility` 同一種「新增頂層欄位」升版慣例）。
        "schema_version": 9,
        "engine_version": __version__,
        "analyzed_at": m.fetched_at,
        "scenario_id": scenario_id,
        "params": {**dataclasses.asdict(base),
                   "iv_shifts": list(base.iv_shifts),
                   "delta_bands": list(base.delta_bands)},
        "snapshot_ref": {"path": m.snapshot_path, "fetched_at": m.fetched_at,
                         "source": m.source, "spot": m.spot},
        "meta": {"symbol": m.symbol, "spot": m.spot,
                 "fetched_at": m.fetched_at, "source": m.source,
                 "snapshot_path": m.snapshot_path,
                 "target_move": m.target_move},
        "capital_assumed": capital,
        "data_quality": {"fetched_at": m.fetched_at,
                         "all_quotes_filtered": all_quotes_filtered},
        "results": results,
        # T09（#191）：`results`／`expiry_groups` 兩者的生成式都經由
        # `cand_key()` 這個共用 closure 寫入同一個 `pool`——上面已先
        # 算成區域變數 `results`／`expiry_groups`（而不是把生成式直接
        # 寫進這個字典字面量），確保這裡讀到的 `pool` 已收齊兩邊寫入的
        # 全部候選，不受字典字面量鍵值對求值順序影響。
        "candidate_pool": pool,
        # T14（#233，Initial V2）：座標軸去重後的集中儲存區——同一份
        # `axis_of()` closure 已在算 `results`／`expiry_groups` 的過程
        # 副作用寫入，這裡直接讀已經填好的區域變數（跟 `pool` 同一個
        # 讀取時機保證）。
        "axis_sets": axis_sets,
        "expiry_groups": expiry_groups,
        "hidden_expiries": list(result.hidden_expiries),
        "default_selection": (list(result.default_selection)
                              if result.default_selection else None),
        # T10（#24，附錄A8.5）：詳細頁進頁預設——baseline 期本身、及其第 1 名。
        # 與 `default_selection`（v4 舊有、跨到期日全域最高報酬避警示語意）
        # 刻意分開，兩者服務不同的產品決策。
        "baseline_expiry": result.baseline_expiry,
        "baseline_selection": (list(result.baseline_selection)
                               if result.baseline_selection else None),
        "comparison": [dataclasses.asdict(c) for c in result.comparison],
        "best_strategy": result.best_strategy,
        "today": today.isoformat(),
        # T08（#225，Initial V2 spec #217）：每個 family 的可選／不可選
        # verdict，涵蓋全部 `FAMILIES`（不只這次請求的 `request.
        # strategies`）——建立／編輯表單（T10）需要看到全部三個 family
        # 的 checkbox 狀態，不只是這個劇本目前選中的那些。方向由
        # `target_price` 相對 `spot` 於**這次分析當下**推導，衍生值，
        # 不落盤（`AnalysisResult` 本身沒有 `direction` 欄位）。前端
        # 只渲染這個 verdict，永不自行計算 eligibility（CONTEXT.md
        # 「Eligibility」一節）。
        "family_eligibility": _family_eligibility_map(base.target_price, m.spot),
        # OPTION-CHASER-CLOSEOUT-001（Scenario Detail 補劇本摘要）：
        # 衍生方向本身也純加法輸出——detail 頁要呈現「使用者原本建立
        # 的劇本設定」，方向是其中一項，且必須跟 `family_eligibility`
        # 用同一個判準算出來的同一個值，不能讓前端自己比較
        # `target_price` 與 `spot` 再猜一次（那正是 CONTEXT.md
        # 「Eligibility」一節要擋的事——這裡延伸到「顯示方向本身」，
        # 不是只有「顯示可選／不可選」）。與 `family_eligibility` 各自
        # 獨立呼叫 `derive_direction()`——這個函式本身是零 I/O 的純
        # 比較，`_family_eligibility_map()` docstring 已記錄「兩個模組
        # 各自獨立呼叫」是既有、刻意接受的跨模組前提，這裡是同一個
        # 前提在同一個函式內的延伸，不是新增風險。
        "direction": derive_direction(base.target_price, m.spot),
    }


def historical_fact_context(view: dict) -> dict:
    """SCALE-01（#252，Scaling Foundation Stage 1-0）：從一份（新鮮或
    既有）`view` dict 抽出「重建歷史事實所需、真正不可丟的 context」，
    以獨立、可窄查詢的形式回傳——不是新計算，純粹是把已經在 `view`
    裡的欄位投影出來，供 `api_app/main.py` 寫入新 `ResultRecord` 欄位、
    也供既有資料的 backfill 腳本重用同一份邏輯（保證兩條路徑算出來的
    結果永遠一致，不會各自維護一份、日後漂移）。

    回傳的 6 個 key 直接對應 `ResultRecord` 新增的 6 個欄位：

    - `resolved_params`：完整 resolved `AnalysisParams`（`view["params"]`
      本身已是 `dataclasses.asdict(base_params)`＋`iv_shifts`／
      `delta_bands` 轉成 list 的 JSON-safe 形狀，直接引用不重算）。
    - `requested_strategies`：這次分析實際請求的 subtype 清單——
      `view["results"]` 的每一項就是 `AnalysisRequest.strategies` 逐一
      對應的結果（`store.serialize_result()` 的 `results = [strat(r)
      for r in result.results]`，而 `result.results` 與請求的
      `strategies` 一一對應），因此不需要另外傳一份、從這裡反推即可。
    - `engine_version`：`view["engine_version"]`。
    - `view_schema_version`：`view["schema_version"]`。
    - `history_replay_version`：**永遠是目前程式碼認得的
      `HISTORY_REPLAY_VERSION`**，不是 view 裡的任何既有欄位（這個
      版本號本來就不存在於 view 形狀裡）——不論這份 view 是剛產生的
      還是很久以前存的舊資料，「用今天的語意去理解它的歷史成員資格」
      都只有一種答案：今天的版本號。未來版本號真的往前推進時，這個
      函式本身要跟著改成依某個判準決定舊列該標哪個版本，不能自動沿用
      「不管多舊都套用最新版」這個目前唯一成立的邏輯。
    - `snapshot_source`：這次分析用的原始快照資料源（`"cboe"`／
      `"yfinance"`，`view["meta"]["source"]`）——provenance 明文要求的
      「snapshot source」半邊；另一半「snapshot fetched_at」不需要
      獨立欄位，因為 `ResultRecord.analyzed_at` 本身就定義為快照的
      `fetched_at`（見該欄位既有註解）。
    """
    return {
        "resolved_params": view["params"],
        "requested_strategies": tuple(r["strategy"] for r in view["results"]),
        "engine_version": view["engine_version"],
        "view_schema_version": view["schema_version"],
        "history_replay_version": HISTORY_REPLAY_VERSION,
        "snapshot_source": view["meta"]["source"],
    }


def project_for_detail(view: dict) -> dict:
    """T13（#231，Initial V2）：詳細頁端點（`GET /api/scenarios/{id}`）
    傳輸投影——**只服務這一個 HTTP 端點**，不動儲存層。落盤的
    `ResultRecord.view` 維持 `serialize_result()` 原樣的全保真輸出；
    V9 Spread 淨成本走勢（`spread_cost_history()`）、`find_candidate()`
    （`/iv-history` 用）等既有 server 端路徑都直接讀 storage 裡完整的
    `rec.view`，完全不經過這個函式，因此零回歸。

    移除兩個前端從未消費、只服務 server 端歷史查詢的完整候選序列
    （`Candidate` 這個 TS 型別本身就沒有 `strategy` 以外的容器層欄位
    宣告——`src/api.ts` 從未宣告過 `results[].candidates` 或
    `results[].all_candidates`）：
    - `all_candidates`（附錄A7：`spread_cost_history()` 專用，該函式吃
      的是 storage 裡完整的 `rec.view`，不吃這個投影後的結果）
    - `candidates`（引擎全量候選 key 清單——這才是「每多啟用一個
      spread 策略就多約 495KB」的真正成因：它會把**每一筆**通過過濾的
      候選都拉進 `candidate_pool`，遠遠超出 `expiry_top10` 每期前十名
      的既有上限）

    `expiry_groups`（v4 舊「到期日分組比較」結構）**刻意保留**：它本身
    很小（每個 (到期日, 策略) 組合只有一列，不是候選序列），且
    `representative_candidate()`／`best_return()` 需要它才能對**任何**
    view dict（含這個投影後的結果）正常運作——既有測試
    （`test_api_scenarios.py`）就是這樣呼叫的。它引用的候選鍵今天
    確實是 `expiry_best` 的子集（`_build_groups()` 對同一個 (到期日,
    策略) 取的是同一個 `pe_best` 候選），不會讓 pool 變大——但下面
    仍然把它自己的引用集合逐一走一遍納入 `referenced`，是刻意的防禦
    寫法，不是依賴這條子集關係省事：`_build_groups()` 未來若改變候選
    挑選邏輯而讓兩者出現分歧，這裡也不會不小心把 `expiry_groups` 真正
    需要的候選漏出投影後的池子。

    候選池只保留還被 `expiry_best`／`expiry_top10`／`expiry_groups`／
    `default_selection`／`baseline_selection` 引用到的鍵——這些容器
    加總起來已被引擎的既有規則限制在「到期日數 × 10」量級（`expiry_
    top10` 每期至多十筆，其餘容器的引用集合都是它的子集），因此不需要
    另外寫一段「檢查候選數不超過上限」的邏輯：移除 `candidates`／
    `all_candidates` 這兩個唯二會讓池子無界成長的來源之後，這個上限是
    結構上自動成立的。

    純函式、不修改輸入：回傳全新的頂層字典與 `results[]` 列表，`view`
    本身（連同它內部所有巢狀物件）維持原封不動，因此可以放心把
    `ResultRecord.view` 直接傳進來，不必先複製。
    """
    referenced: set[str] = set()

    def project_result(r: dict) -> dict:
        referenced.update(r.get("expiry_best") or ())
        for group in r.get("expiry_top10") or ():
            referenced.update(group["candidate_keys"])
        return {k: v for k, v in r.items()
               if k not in ("candidates", "all_candidates")}

    results = [project_result(r) for r in view.get("results", [])]
    for group in view.get("expiry_groups") or ():
        for row in group.get("rows", []):
            referenced.add(row["candidate_key"])
    if view.get("default_selection"):
        referenced.add(view["default_selection"][1])
    if view.get("baseline_selection"):
        referenced.add(view["baseline_selection"][1])

    pool = view.get("candidate_pool") or {}
    projected_pool = {k: pool[k] for k in referenced if k in pool}
    return {**view, "results": results, "candidate_pool": projected_pool}


def find_candidate(view: dict, key: str) -> dict | None:
    """依身份鍵在 view dict 裡找出那個候選的**完整**形狀（含各腿）。

    走 `expiry_top10`（完整候選）而不是 `all_candidates`（精簡序列，只有
    成本與名次，沒有腿）——呼叫端要的是腿上的 IV／履約價／權別。找不到
    回 `None`，不拋錯：候選可能在這次刷新被過濾掉，那是正常狀態。

    單腳策略（Long Call／Long Put）過去沒有 `expiry_top10` 分組（T9
    附錄A7：範圍限定 Spread 路徑，single-leg 依 MVP 範圍不動）——候選
    活在扁平的 `r["candidates"]` 清單裡，只在該策略**完全沒有**
    `expiry_top10` 分組時才退去掃這份清單（#139）。**Initial V2 T09
    （#222）起，單腿策略正常情況下也會有非空的 `expiry_top10`**（見
    `service._single_leg_result()`），因此單腿候選現在多半也走
    `expiry_top10` 這條路——扁平清單 fallback 只在該策略**完全零合格
    候選**（`status != "ok"`，`expiry_top10` 恆空）時才會真正被用到，
    這種情況兩種策略（單腿／Spread）本來就一致。兩腿策略（Spread）
    一律只認 `expiry_top10`，「候選有沒有入榜」是既有規則的一部分，
    不因此擴大查找範圍——這保證兩腿路徑的既有行為與數值一字不動。

    T09（#191，schema_version 3）：`expiry_top10[].candidates`／
    `r["candidates"]` 從完整候選字典改成 `candidate_keys`／
    `candidates`（key 字串清單），完整內容改查頂層 `candidate_pool`；
    key「是否在這個容器的清單裡」才是既有規則的判準，`candidate_pool`
    本身跨策略共用、不能單獨拿來判斷某個 key 是否屬於這個策略。舊存的
    View（schema_version 1／2，無 `candidate_pool`）維持原始邏輯不動，
    讀取端相容——這條票（#191）明文要求「既有已儲存的 View 不做資料
    遷移，讀取端維持相容」。
    """
    pool = view.get("candidate_pool")
    if pool is None:
        # 舊 schema（<=2）：容器內直接內嵌完整候選字典，原始邏輯不動。
        for r in view.get("results", []):
            groups = r.get("expiry_top10") or []
            for group in groups:
                for cand in group.get("candidates", []):
                    if cand.get("candidate_key") == key:
                        return cand
            if groups:
                continue
            for cand in r.get("candidates", []) or []:
                if cand.get("candidate_key") == key:
                    return cand
        return None
    # 新 schema（>=3）：容器內只有 key 引用，完整內容統一查 `pool`。
    for r in view.get("results", []):
        groups = r.get("expiry_top10") or []
        for group in groups:
            if key in (group.get("candidate_keys") or []):
                return pool.get(key)
        if groups:
            continue
        if key in (r.get("candidates") or []):
            return pool.get(key)
    return None
