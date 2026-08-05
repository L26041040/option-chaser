/**
 * 建立劇本表單（V3／#51；年月選擇器 #71 改為自製）。
 *
 * 三欄全部留白、無任何預設值——這是 QA1-04（#31）的既有裁示：預設值會被
 * 當成建議，使用者照著按下去就得到一個不是他要的劇本。
 *
 * 目標年月是**單一欄位**（無「日」）：到期日由引擎依目標月選，使用者選日
 * 沒有意義。
 *
 * #71 推翻了 V3 當時「用原生 `<input type="month">`」的裁示：原生元件在
 * 桌面 Chrome 一定要按右邊圖示才展開、無法呈現 `20xx` 的年份輸入概念，
 * 且在桌面 Safari／Firefox 會直接退化成純文字框（見下方 `validateDraft`
 * 的格式檢查）。改自製 `MonthPicker`：點欄位本身就地展開，不是彈出浮層
 * ——面板就是文件流裡的下一個手足元素，Tab 鍵順序天然正確，不必額外
 * 管理焦點。
 */
import { useEffect, useId, useRef, useState } from "react";

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

const MONTHS = Array.from({ length: 12 }, (_, i) => i + 1);

/**
 * 年份輸入（#71）：聚焦時只框住後兩碼——多數操作是「換到另一個 20xx
 * 年份」，選取後兩碼讓打字直接覆蓋掉它們，不必先刪掉前面的「20」。也支援
 * 全選後直接打四碼跳到任何年份，箭頭鈕（`MonthPicker`）則是完全不必打字
 * 的路徑——三種操作方式殊途同歸，都只是在改同一個數字。
 *
 * `draft` 是打字打到一半的本地緩衝，只在滿四碼時才回報給外層；外層的
 * `year` 透過箭頭鈕改變時，`useEffect` 把緩衝同步回去。未滿四碼就失焦，
 * 緩衝重置回原本的年份，不留一個殘缺的顯示。
 */
function YearInput({ year, onChange }: {
  year: number;
  onChange: (year: number) => void;
}) {
  const [draft, setDraft] = useState(String(year));
  // 箭頭鈕改了外部的 `year`——同步顯示。打字打到一半時 `onChange` 早已
  // 把同一個值回報給外層、`year` 立刻追上 `draft`，這個 effect 因此是
  // no-op，不會覆蓋使用者正在打的字。
  useEffect(() => setDraft(String(year)), [year]);

  return (
    <input
      className="year-input"
      inputMode="numeric"
      aria-label="年份"
      value={draft}
      onFocus={(e) => e.currentTarget.setSelectionRange(2, 4)}
      onChange={(e) => {
        const digits = e.target.value.replace(/\D/g, "").slice(0, 4);
        setDraft(digits);
        if (digits.length === 4) onChange(Number(digits));
      }}
      onBlur={() => setDraft(String(year))}
    />
  );
}

/**
 * 自製年月選擇器（#71，推翻 V3「用原生 input」的裁示——理由見檔案頂端
 * 註解）。點欄位本身就地展開（不是浮層），展開預設落在今年，月份以
 * 按鈕呈現、當月有 `aria-current="date"` 標示，年份可箭頭切換或直接
 * 打四碼、不設上下限。
 *
 * 面板在文件流裡緊接在切換鈕之後——Tab 順序天然是切換鈕→上一年→
 * 年份→下一年→1 月…12 月→下一個表單欄位，不必用 `useEffect` 搬焦點。
 * 選定或再次點欄位本身都會收合；選定後把焦點還給切換鈕，鍵盤使用者
 * 才不會在元素被卸載後掉到 `<body>`，得從頁面最上方重新 Tab 一次。
 */
function MonthPicker({ value, onChange, today }: {
  value: string;
  onChange: (month: string) => void;
  today: Date;
}) {
  const [open, setOpen] = useState(false);
  const [displayYear, setDisplayYear] = useState(today.getFullYear());
  const toggleRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();

  const [selectedYear, selectedMonth] = value
    ? value.split("-").map(Number) : [null, null];

  function toggle() {
    if (!open) {
      // 每次重新展開都該有可預期的起點：已有選定值就回到那個值的年份
      // （不然調整月份會意外把年份改回今年），否則回到今年。
      setDisplayYear(selectedYear ?? today.getFullYear());
    }
    setOpen((o) => !o);
  }

  function pick(month: number) {
    onChange(`${displayYear}-${String(month).padStart(2, "0")}`);
    setOpen(false);
    toggleRef.current?.focus();
  }

  return (
    <div className="month-picker">
      <button
        ref={toggleRef}
        type="button"
        className="input month-picker-toggle"
        onClick={toggle}
        aria-expanded={open}
        aria-controls={panelId}
      >
        {value || <span className="muted">20xx-xx</span>}
      </button>

      {open && (
        <div id={panelId} className="month-picker-panel" role="group"
             aria-label="選擇年月">
          <div className="month-picker-year-row">
            <button type="button" className="month-picker-step"
                    aria-label="上一年"
                    onClick={() => setDisplayYear((y) => y - 1)}>
              ‹
            </button>
            <YearInput year={displayYear} onChange={setDisplayYear} />
            <button type="button" className="month-picker-step"
                    aria-label="下一年"
                    onClick={() => setDisplayYear((y) => y + 1)}>
              ›
            </button>
          </div>

          <div className="month-picker-grid">
            {MONTHS.map((m) => {
              const isSelected = selectedYear === displayYear && selectedMonth === m;
              const isToday = displayYear === today.getFullYear()
                && m === today.getMonth() + 1;
              return (
                <button
                  key={m}
                  type="button"
                  className={isSelected ? "month-cell selected" : "month-cell"}
                  aria-pressed={isSelected}
                  aria-current={isToday ? "date" : undefined}
                  onClick={() => pick(m)}
                >
                  {m} 月
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export default function CreateForm({
  onCreate,
  busy = false,
  today = new Date(),
}: {
  onCreate: (draft: DraftScenario) => Promise<void>;
  busy?: boolean;
  /** 「今天」由呼叫端傳入（沿用全站零 wall-clock 於元件內的既有原則）
   *  ——年月選擇器用它決定展開時的預設年份與當月標示。 */
  today?: Date;
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
        <MonthPicker value={month} onChange={setMonth} today={today} />
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
