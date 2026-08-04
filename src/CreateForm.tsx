/**
 * 建立劇本表單（V3／#51）。
 *
 * 三欄全部留白、無任何預設值——這是 QA1-04（#31）的既有裁示：預設值會被
 * 當成建議，使用者照著按下去就得到一個不是他要的劇本。
 *
 * 目標年月是**單一欄位**（無「日」）：到期日由引擎依目標月選，使用者選日
 * 沒有意義。用原生 `<input type="month">`——手機上它就是系統的年月選擇器，
 * 自己刻一個彈窗只會比系統的更難用、更不無障礙。
 */
import { useState } from "react";

export interface DraftScenario {
  symbol: string;
  target_price: number;
  target_month: string;
  /** V7（#55）劇本區間兩端，選填。未設定時**不出現在物件裡**（而不是送
   *  `null`）——後端的 optional 欄位語意是「沒送＝沒設定」。 */
  best_price?: number;
  worst_price?: number;
}

/** 選填價位欄位的解析。留白＝未設定（不是錯誤）。 */
function parseOptionalPrice(
  raw: string, label: string,
): { ok: true; value: number | undefined } | { ok: false; error: string } {
  if (!raw.trim()) return { ok: true, value: undefined };
  if (!/^-?\d+(\.\d+)?$/.test(raw.trim())) {
    return { ok: false, error: `${label}要是數字` };
  }
  const value = Number(raw);
  if (!Number.isFinite(value) || value <= 0) {
    return { ok: false, error: `${label}要大於 0` };
  }
  return { ok: true, value };
}

/**
 * 驗證留在表單層而不是送出去讓後端擋：後端當然也擋（它是唯一接縫），
 * 但使用者不該為了知道「價格要填數字」而等一趟網路往返。
 */
export function validateDraft(
  symbol: string,
  price: string,
  month: string,
  best = "",
  worst = "",
): { ok: true; draft: DraftScenario } | { ok: false; error: string } {
  const sym = symbol.trim().toUpperCase();
  if (!sym) return { ok: false, error: "請填標的代號（例如 TLT）" };
  if (!/^[A-Z.\-]{1,10}$/.test(sym)) {
    return { ok: false, error: "標的代號只能是英文字母、點或連字號" };
  }
  if (!price.trim()) return { ok: false, error: "請填目標價位" };
  // 只收十進位寫法：`Number()` 會把 "0x1f" 讀成 31、"1e5" 讀成 100000，
  // 那不是使用者以為自己填的價格。
  // 負號放行，讓 "-5" 落到下面的「要大於 0」——那句話比「要是數字」
  // 更貼近使用者真正做錯的事。
  if (!/^-?\d+(\.\d+)?$/.test(price.trim())) {
    return { ok: false, error: "目標價位要是數字" };
  }
  const value = Number(price);
  if (!Number.isFinite(value)) return { ok: false, error: "目標價位要是數字" };
  if (value <= 0) return { ok: false, error: "目標價位要大於 0" };
  if (!month) return { ok: false, error: "請選目標年月" };
  // `type="month"` 在桌面 Safari／Firefox 會退化成純文字框，使用者可以
  // 打「May 2028」。不擋的話會換來一個後端 422，而 422 的 detail 是物件
  // 陣列、被壓成「請求失敗（HTTP 422）」，完全沒說哪裡錯。
  if (!/^\d{4}-\d{2}$/.test(month)) {
    return { ok: false, error: "目標年月格式為 YYYY-MM（例如 2028-05）" };
  }
  // V7（#55）兩端。與後端 `_ends_must_straddle_the_target` 同一套規則——
  // 前端先擋只是省一趟往返，後端仍是權威（重複的是規則，不是真相來源）。
  const b = parseOptionalPrice(best, "最好價位");
  if (!b.ok) return b;
  const w = parseOptionalPrice(worst, "最差價位");
  if (!w.ok) return w;
  if (b.value !== undefined && b.value < value) {
    return { ok: false, error: "最好價位不可低於目標價" };
  }
  if (w.value !== undefined && w.value > value) {
    return { ok: false, error: "最差價位不可高於目標價" };
  }

  return {
    ok: true,
    draft: {
      symbol: sym, target_price: value, target_month: month,
      // 未設定就整個不放進物件——`best_price: undefined` 會被 JSON.stringify
      // 丟掉，行為雖同，但型別上留一個永遠是 undefined 的欄位只會誤導讀者。
      ...(b.value !== undefined ? { best_price: b.value } : {}),
      ...(w.value !== undefined ? { worst_price: w.value } : {}),
    },
  };
}

export default function CreateForm({
  onCreate,
  busy = false,
}: {
  onCreate: (draft: DraftScenario) => Promise<void>;
  busy?: boolean;
}) {
  // 三欄一律空字串起手——沒有預設值，也沒有「上次填的」。
  const [symbol, setSymbol] = useState("");
  const [price, setPrice] = useState("");
  const [month, setMonth] = useState("");
  const [best, setBest] = useState("");
  const [worst, setWorst] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const checked = validateDraft(symbol, price, month, best, worst);
    if (!checked.ok) {
      setError(checked.error);
      return;
    }
    setError(null);
    try {
      await onCreate(checked.draft);
      setSymbol("");
      setPrice("");
      setMonth("");
      setBest("");
      setWorst("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <form className="card" onSubmit={submit} noValidate>
      <h2 className="section-title">建立劇本</h2>

      <label className="field">
        <span className="row-label">標的代號</span>
        <input
          className="input"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          autoCapitalize="characters"
          autoCorrect="off"
          spellCheck={false}
        />
      </label>

      <label className="field">
        <span className="row-label">目標價位</span>
        {/* inputMode="decimal" 讓手機跳出數字鍵盤；type 仍是 text，
            數字型別在 iOS 上會出現用不到的上下微調鈕。 */}
        <input
          className="input"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          inputMode="decimal"
        />
      </label>

      <label className="field">
        <span className="row-label">目標年月</span>
        <input
          className="input"
          type="month"
          value={month}
          onChange={(e) => setMonth(e.target.value)}
        />
      </label>

      {/* V7（#55）劇本區間兩端：選填，擺在三個必填欄位之後——它們是
          「除了比較最高，還能比較最低」的加分項，不該擋在主流程前面。 */}
      <label className="field">
        <span className="row-label">最好價位（選填）</span>
        <input
          className="input"
          value={best}
          onChange={(e) => setBest(e.target.value)}
          inputMode="decimal"
        />
      </label>

      <label className="field">
        <span className="row-label">最差價位（選填）</span>
        <input
          className="input"
          value={worst}
          onChange={(e) => setWorst(e.target.value)}
          inputMode="decimal"
        />
      </label>

      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}

      <button className="button" type="submit" disabled={busy}>
        {busy ? "建立中……" : "建立"}
      </button>
    </form>
  );
}
