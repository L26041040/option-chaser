#!/usr/bin/env python
"""#111：Market Data App 真實驗證探測腳本（vendor 已由需求方裁示指定）。

與既有的 `probe_iv_history_vendors.py` 不同，這支**不比較 vendor**——
需求方 2026-08-12 已裁示自訂 Provider 只支援 Market Data App，選型結束。
這支要回答的是剩下那個真正決定 #126 能不能做的問題：

    以候選的 (tenor, delta) 座標**逐日重錨定** 1 年、日粒度的歷史 IV，
    在這家 vendor 上「拿得到」而且「付得起」嗎？

## 為什麼這件事不是理所當然

`/v1/options/quotes/{optionSymbol}/?from=&to=` 一次回**單一合約**整段
日序列（研究文件 §4.7）。但那是一張**固定合約**的序列——它的 tenor
每天縮短一天，delta 每天隨標的漂移。拿它當「歷史 IV」會犯的正是 #114
AC 明文要避免的錯：序列的意義隨合約變老而漂移。

真正的逐日重錨定需要「每一天那一天的鏈」，也就是
`/v1/options/chain/{symbol}/?date=YYYY-MM-DD`。而 chain 端點有**兩種計價模式**
（`option-chain-data-sources.md` §3.6）：

- **cached mode：整鏈 1 credit**——但該節記載「免費與試用層不能用」
- **live mode：回幾筆合約就扣幾個 credit**（官方自舉 SPX 全鏈
  22,718 筆＝22,718 credits）

也就是說「逐日整鏈」的成本取決於**落在哪個模式**，不是端點本身就貴：
付費層（Starter US$12/月、10,000 credits/日）下 252 個交易日各一次
＝約 252 credits，綽綽有餘。真正沒查證的是
`historical-options-iv-data-sources.md` §4.7 明記的那一項：**歷史查詢
（帶 `date`／`from`／`to`）到底怎麼扣 credit——一次呼叫一點，還是逐日
扣？** 該節原文寫「未能查證」。

**這支腳本就是去量這件事**：逐日重錨定一年實際要花多少 credit，以及
回傳欄位裡到底有沒有 delta（沒有 delta 就根本錨不了）。

## 用法

沙箱出口封鎖 `api.marketdata.app`（CONNECT 403，本輪已用 curl 複驗），
因此**必須在可連網環境跑**——需求方本機，或本 repo 既有慣例的一次性
GitHub Actions workflow（跑完即刪，見 `tmp-vendor-probe.yml` 的前例）。

    export MARKETDATA_APP_TOKEN=...   # https://www.marketdata.app/ 免費註冊
    python3 scripts/probe_marketdata_app.py

輸出是一份 JSON 報告，直接貼回 issue #111 即可當驗證紀錄。**不會**把
token 印出來（本 repo 的既有紀律，#124／#125 一致）。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = "https://api.marketdata.app/v1"
TIMEOUT = 30.0

# 探測標的：流動性高、必然有 LEAPS，與需求方的實際劇本無關。
SYMBOL = "AAPL"


def _get(url: str, token: str) -> tuple[int, dict | str, dict]:
    """回傳 (HTTP 狀態, 解析後主體或原始字串, 回應標頭)。

    標頭要留著：credit 用量通常在 `X-Api-Ratelimit-*` 之類的標頭裡，
    而「一次呼叫扣幾點」正是本次要量的東西。
    """
    req = Request(url, headers={"Authorization": f"Bearer {token}",
                                "User-Agent": "option-chaser-probe",
                                "Accept": "application/json"})
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            headers = {k: v for k, v in resp.headers.items()}
            status = resp.status
    except HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        return e.code, raw, {k: v for k, v in e.headers.items()}
    except (URLError, OSError) as e:
        return 0, f"連線失敗：{e}", {}
    try:
        return status, json.loads(raw), headers
    except json.JSONDecodeError:
        return status, raw, headers


def _ratelimit(headers: dict) -> dict:
    """挑出跟額度有關的標頭——名稱大小寫與前綴依 vendor 而異，寬鬆比對。"""
    return {k: v for k, v in headers.items()
            if "ratelimit" in k.lower() or "credit" in k.lower()}


def probe_auth(token: str) -> dict:
    """第一關：這把 token 到底能不能用。"""
    status, body, headers = _get(f"{BASE}/options/expirations/{SYMBOL}/", token)
    ok = status == 200 and isinstance(body, dict) and body.get("s") == "ok"
    return {
        "step": "認證與可達性",
        "endpoint": f"/v1/options/expirations/{SYMBOL}/",
        "http_status": status,
        "ok": ok,
        "expirations_returned": len(body.get("expirations", []))
        if isinstance(body, dict) else None,
        "ratelimit_headers": _ratelimit(headers),
        "body_sample": body if not ok else "（成功，略）",
    }


def probe_live_chain(token: str) -> dict:
    """即時全鏈——順便量「回幾筆扣幾點」在實務上是多少。

    也是 #125 的 Market Data adapter（`option_chaser/data/marketdata.py`）
    實際會打的端點：這一關成功，等於那支 adapter 的欄位對應被真實回應
    驗證過一次。
    """
    status, body, headers = _get(f"{BASE}/options/chain/{SYMBOL}/", token)
    out = {
        "step": "即時全鏈（#125 adapter 的實際路徑）",
        "endpoint": f"/v1/options/chain/{SYMBOL}/",
        "http_status": status,
        "ratelimit_headers": _ratelimit(headers),
    }
    if not (status == 200 and isinstance(body, dict) and body.get("s") == "ok"):
        out["ok"] = False
        out["body_sample"] = body
        return out

    out["ok"] = True
    out["contracts_returned"] = len(body.get("optionSymbol", []))
    out["columns_present"] = sorted(k for k, v in body.items()
                                    if isinstance(v, list))
    # #125 的 adapter 靠這幾個欄位；缺任何一個都得改對應。
    needed = ["optionSymbol", "side", "strike", "expiration", "bid", "ask",
              "last", "volume", "openInterest", "iv", "underlyingPrice"]
    out["adapter_fields_missing"] = [k for k in needed if k not in body]

    # 真的餵進 adapter 跑一遍——「欄位都在」跟「解得出來」是兩回事。
    try:
        from option_chaser.data import marketdata

        snap = marketdata.map_chain_payload(SYMBOL, body, "probe")
        out["adapter_parse"] = {
            "ok": True, "contracts": len(snap.contracts), "spot": snap.spot,
            "with_iv": sum(1 for c in snap.contracts
                           if c.implied_volatility is not None),
        }
    except Exception as e:  # noqa: BLE001 — 探測腳本要如實記錄任何失敗
        out["adapter_parse"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return out


def probe_historical_chain(token: str) -> dict:
    """**本次的關鍵一關**：某一個過去日期的整鏈，含 delta。

    (tenor, delta) 逐日重錨定要成立，這一關必須同時滿足三件事：
      1. `date` 參數真的回得到那天的歷史鏈（不是默默回今天的）
      2. 回傳欄位裡有 `delta`（沒有 delta 就錨不了）
      3. 一次呼叫的 credit 成本可接受（× 252 個交易日仍在額度內）
    """
    target = date.today() - timedelta(days=90)
    url = (f"{BASE}/options/chain/{SYMBOL}/"
           f"?date={target.isoformat()}")
    status, body, headers = _get(url, token)
    out = {
        "step": "歷史整鏈（(tenor,delta) 逐日重錨定的前提）",
        "endpoint": f"/v1/options/chain/{SYMBOL}/?date={target.isoformat()}",
        "http_status": status,
        "ratelimit_headers": _ratelimit(headers),
    }
    if not (status == 200 and isinstance(body, dict) and body.get("s") == "ok"):
        out["ok"] = False
        out["body_sample"] = body
        out["verdict"] = ("歷史鏈拿不到 → (tenor,delta) 逐日重錨定在這家"
                          "做不到，#126 需改用其他方案或回頭找 vendor")
        return out

    out["ok"] = True
    out["contracts_returned"] = len(body.get("optionSymbol", []))
    out["has_delta"] = "delta" in body
    out["has_iv"] = "iv" in body
    out["has_dte"] = "dte" in body
    # 回傳的 `updated` 時戳要真的落在查詢日，否則就是默默回了今天的資料。
    updated = body.get("updated") or []
    out["updated_sample"] = updated[:3]
    out["verdict"] = (
        "可行" if out["has_delta"] and out["has_iv"]
        else "缺 delta／iv → 無法在 (tenor,delta) 座標上重錨定")
    return out


def probe_single_contract_history(token: str) -> dict:
    """對照組：單一合約的歷史序列（研究文件 §4.7 說的那條路）。

    留著是為了把「便宜但錨不住」這件事量化記錄下來——它一次呼叫就回
    整段日序列，成本遠低於逐日整鏈，但序列的意義會隨合約變老而漂移。
    #114 AC 明文排除這種做法，這裡只是把代價與限制一併記在紀錄裡。
    """
    status, body, _ = _get(f"{BASE}/options/expirations/{SYMBOL}/", token)
    if not (status == 200 and isinstance(body, dict) and body.get("s") == "ok"):
        return {"step": "單一合約歷史序列（對照組）", "ok": False,
                "note": "取不到到期日清單，跳過"}
    expiries = body.get("expirations") or []
    if not expiries:
        return {"step": "單一合約歷史序列（對照組）", "ok": False,
                "note": "沒有到期日可用"}

    # 隨便取一個中段到期日，組一個近價的 OCC 代號需要先拿到 strike，
    # 因此改用 chain 端點取一個真實存在的 optionSymbol。
    status, chain, _ = _get(
        f"{BASE}/options/chain/{SYMBOL}/?expiration={expiries[len(expiries) // 2]}",
        token)
    symbols = chain.get("optionSymbol") if isinstance(chain, dict) else None
    if not symbols:
        return {"step": "單一合約歷史序列（對照組）", "ok": False,
                "note": "取不到任何合約代號"}

    occ = symbols[len(symbols) // 2]
    frm = (date.today() - timedelta(days=365)).isoformat()
    to = date.today().isoformat()
    status, series, headers = _get(
        f"{BASE}/options/quotes/{occ}/?from={frm}&to={to}", token)
    ok = status == 200 and isinstance(series, dict) and series.get("s") == "ok"
    return {
        "step": "單一合約歷史序列（對照組，#114 AC 排除的做法）",
        "endpoint": f"/v1/options/quotes/{occ}/?from={frm}&to={to}",
        "http_status": status,
        "ok": ok,
        "days_returned": len(series.get("iv", [])) if ok else None,
        "has_delta": "delta" in series if isinstance(series, dict) else None,
        "ratelimit_headers": _ratelimit(headers),
        "note": ("一次呼叫回整段序列，成本遠低於逐日整鏈；但這是固定合約，"
                 "tenor 每天縮短、delta 每天漂移，不能當 (tenor,delta) "
                 "重錨定序列用"),
    }


def main() -> None:
    token = os.environ.get("MARKETDATA_APP_TOKEN")
    if not token:
        print(json.dumps({
            "error": "MARKETDATA_APP_TOKEN 未設定",
            "how": "到 https://www.marketdata.app/ 免費註冊取得 token，"
                   "設為環境變數後重跑。沙箱出口封鎖 api.marketdata.app，"
                   "必須在可連網環境執行。",
        }, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    report = {
        "vendor": "Market Data App",
        "probe_date": date.today().isoformat(),
        "symbol": SYMBOL,
        "steps": [
            probe_auth(token),
            probe_live_chain(token),
            probe_historical_chain(token),
            probe_single_contract_history(token),
        ],
    }
    # token 絕不進輸出——這份報告是要貼回 issue 的。
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
