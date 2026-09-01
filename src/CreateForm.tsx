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

import type { FamilyEligibility } from "./api";

export interface DraftScenario {
  symbol: string;
  target_price: number;
  target_month: string;
  /**
   * T10（#227，Initial V2）：使用者勾選的 Strategy Family 代碼——
   * 必填、無預設值，至少要有一個。
   */
  strategies: string[];
  /** V7（#55）劇本區間兩端，選填。未設定時**不出現在物件裡**（而不是送
   *  `null`）——後端的 optional 欄位語意是「沒送＝沒設定」。 */
  best_price?: number;
  worst_price?: number;
}

/**
 * T10（#227，Initial V2）：Strategy Family 勾選選項——family 代碼與
 * 顯示標籤的唯一對照表，直接沿用 CONTEXT.md「策略與方向」一節列出的
 * 三個名字（"Call / Put"／"Vertical Spread"／"Butterfly"），不是自創
 * 譯名。順序即畫面呈現順序。
 */
const FAMILY_OPTIONS: { code: string; label: string }[] = [
  { code: "single-leg", label: "Call / Put" },
  { code: "vertical-spread", label: "Vertical Spread" },
  { code: "butterfly", label: "Butterfly" },
];

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
  families: string[],
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
  // T10（#227，Initial V2）：AC「至少要選一個才能送出」——後端也擋
  // （pydantic `Field(min_length=1)`），這裡先擋只是省一趟往返。
  if (families.length === 0) {
    return { ok: false, error: "請至少勾選一個策略類型" };
  }
  // V7（#55）兩端。與後端 `_ends_must_straddle_the_target` 同一套規則——
  // 前端先擋只是省一趟往返，後端仍是權威（重複的是規則，不是真相來源）。
  const b = parseOptionalPrice(best, "最高價位");
  if (!b.ok) return b;
  const w = parseOptionalPrice(worst, "最低價位");
  if (!w.ok) return w;
  if (b.value !== undefined && b.value < value) {
    return { ok: false, error: "最高價位不可低於目標價" };
  }
  if (w.value !== undefined && w.value > value) {
    return { ok: false, error: "最低價位不可高於目標價" };
  }

  return {
    ok: true,
    draft: {
      symbol: sym, target_price: value, target_month: month,
      strategies: families,
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
 *
 * 標籤走 `aria-labelledby`，不是其他三個欄位那種 `<label>` 隱式包裹：
 * `<label>` 的內容模型只收 phrasing content（外加最多一個 labelable
 * 子元素），這個元件的根節點與展開面板都是 `<div>`（flow content），
 * 包在 `<label>` 裡是無效巢狀——瀏覽器會寬鬆處理、`getByLabelText` 也
 * 照樣找得到，但驗證器與 axe 這類工具會標記出來，「正確的可及性語意」
 * 不該只靠寬鬆容錯撐過去。
 */
function MonthPicker({ value, onChange, today, labelId }: {
  value: string;
  onChange: (month: string) => void;
  today: Date;
  labelId: string;
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
        aria-labelledby={labelId}
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

/** 編輯模式要預填的原資料（#132）。`null` ＝建立模式。 */
export interface EditTarget {
  id: string;
  symbol: string;
  target_price: number;
  target_month: string;
  best_price: number | null;
  worst_price: number | null;
  /** T10（#227，Initial V2）：目前勾選的 Strategy Family，預填成
   *  checkbox 的初始狀態。 */
  strategies: string[];
  /**
   * T10（#227，Initial V2）：最近一次分析的 family verdict——編輯
   * 表單據此顯示「這個 family 現在為什麼不可選」。`null` ＝ 這個劇本
   * 還沒成功分析過，沒有可顯示的 verdict（checkbox 仍可勾選，只是
   * 不顯示任何原因文字）。
   */
  family_eligibility: Record<string, FamilyEligibility> | null;
}

function str(value: number | null | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

export default function CreateForm({
  onCreate,
  onSaveEdit,
  onCancelEdit,
  editing = null,
  busy = false,
  today = new Date(),
}: {
  onCreate: (draft: DraftScenario) => Promise<void>;
  /** 編輯模式的送出（#132）。標的不在 draft 裡送——後端也沒有那個欄位。 */
  onSaveEdit?: (id: string, draft: DraftScenario) => Promise<void>;
  onCancelEdit?: () => void;
  /** 非 null ＝這張表單現在是編輯模式，預填這個劇本的原資料。 */
  editing?: EditTarget | null;
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
  // T10（#227）：勾選狀態同樣沒有預設值——空陣列起手，使用者自己選。
  const [families, setFamilies] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const monthLabelId = useId();
  const familyLabelId = useId();

  function toggleFamily(code: string) {
    setFamilies((prev) =>
      prev.includes(code) ? prev.filter((f) => f !== code) : [...prev, code]);
  }

  // REPAIR-06（#243，OD-04）：全選——單一操作，已全選時再觸發同一個
  // 操作就是取消全選（AC 明文的 toggle 行為），不是獨立的「全不選」
  // 按鈕。`allFamilyCodes` 直接沿用 `FAMILY_OPTIONS` 順序，不另外
  // 維護一份代碼清單。
  const allFamilyCodes = FAMILY_OPTIONS.map((opt) => opt.code);
  const allFamiliesSelected =
    allFamilyCodes.every((code) => families.includes(code));

  function toggleAllFamilies() {
    setFamilies(allFamiliesSelected ? [] : allFamilyCodes);
  }

  // 進入／切換編輯目標時預填。用 `editing?.id` 當相依：同一個劇本重新
  // 渲染不該把使用者打到一半的內容蓋回原值。
  const editingId = editing?.id ?? null;
  useEffect(() => {
    setError(null);
    if (!editing) {
      setSymbol("");
      setPrice("");
      setMonth("");
      setBest("");
      setWorst("");
      setFamilies([]);
      return;
    }
    setSymbol(editing.symbol);
    setPrice(str(editing.target_price));
    setMonth(editing.target_month);
    setBest(str(editing.best_price));
    setWorst(str(editing.worst_price));
    setFamilies(editing.strategies);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editingId]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const checked = validateDraft(symbol, price, month, families, best, worst);
    if (!checked.ok) {
      setError(checked.error);
      return;
    }
    setError(null);
    if (editing && onSaveEdit) {
      try {
        await onSaveEdit(editing.id, checked.draft);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
      return;
    }
    try {
      await onCreate(checked.draft);
      setSymbol("");
      setPrice("");
      setMonth("");
      setBest("");
      setWorst("");
      setFamilies([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <form className="card" onSubmit={submit} noValidate>
      <h2 className="section-title">{editing ? "編輯劇本" : "建立劇本"}</h2>

      {/* 標的在編輯模式下不可改（#132）：換 underlying 是另一個劇本，
          不是「編輯」。前端反灰只是說明，真正的防線是後端的請求模型
          根本沒有 symbol 欄位。 */}
      <label className="field">
        <span className="row-label">標的代號</span>
        <input
          className="input"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          disabled={Boolean(editing)}
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

      {/* 不是 `<label>` 隱式包裹——理由見 `MonthPicker` 上方的說明
          （`<label>` 只收 phrasing content，這個元件的 `<div>` 根節點
          不合格）。改用 `aria-labelledby` 指向這個 `<span>` 的 id。 */}
      <div className="field">
        <span className="row-label" id={monthLabelId}>目標年月</span>
        <MonthPicker value={month} onChange={setMonth} today={today}
                     labelId={monthLabelId} />
      </div>

      {/* T10（#227，Initial V2）：Strategy Family 勾選——沒有預設值
          （AC「必填留白」延伸到這裡），至少要選一個才能送出。不是
          `<label>` 隱式包裹（同 `MonthPicker` 的理由），改用
          `aria-labelledby`。不可選的 family（`family_eligibility`，
          僅編輯模式才可能有值）只顯示原因文字，checkbox 本身仍可勾選
          ——「使用者已經可以勾選，後端也真的會跑」（票上原文），不是
          禁止勾選，也不做推薦／不推薦，只有可選／不可選兩種事實陳述。 */}
      <div className="field">
        {/* REPAIR-06（#243，OD-04）：全選／取消全選——同一顆按鈕、
            依目前是否已全選切換文案與行為，不是兩顆按鈕。沿用
            `.yield-note-row`（劇本庫既有「說明文字＋操作入口同一行」
            的版面手法，`ScenarioList.tsx` 的垃圾桶批次選取入口同一種
            用法）。 */}
        <div className="yield-note-row">
          <span className="row-label" id={familyLabelId}>策略類型</span>
          <button type="button" className="text-button"
                  onClick={toggleAllFamilies}>
            {allFamiliesSelected ? "取消全選" : "全選"}
          </button>
        </div>
        <div role="group" aria-labelledby={familyLabelId}
             className="family-options">
          {FAMILY_OPTIONS.map((opt) => {
            const verdict = editing?.family_eligibility?.[opt.code];
            const ineligible = verdict !== undefined && !verdict.eligible;
            return (
              <label key={opt.code} className="family-option">
                <input
                  type="checkbox"
                  checked={families.includes(opt.code)}
                  onChange={() => toggleFamily(opt.code)}
                />
                <span>{opt.label}</span>
                {ineligible && (
                  <span className="family-ineligible-reason">
                    {verdict.reason}
                  </span>
                )}
              </label>
            );
          })}
        </div>
      </div>

      {/* V7（#55）劇本區間兩端：選填，擺在三個必填欄位之後——它們是
          「除了比較最高，還能比較最低」的加分項，不該擋在主流程前面。 */}
      <label className="field">
        <span className="row-label">最高價位（選填）</span>
        <input
          className="input"
          value={best}
          onChange={(e) => setBest(e.target.value)}
          inputMode="decimal"
        />
      </label>

      <label className="field">
        <span className="row-label">最低價位（選填）</span>
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

      {editing ? (
        <div className="form-actions">
          {/* 取消**隨時**可按（#132）：不要求未修改、不要求 validation
              通過、不要求先復原內容。`type="button"` 而不是 submit，
              否則瀏覽器會先跑表單驗證。 */}
          <button className="text-button" type="button" onClick={onCancelEdit}>
            取消
          </button>
          <button className="button" type="submit" disabled={busy}>
            {busy ? "儲存中……" : "儲存變更"}
          </button>
        </div>
      ) : (
        <button className="button" type="submit" disabled={busy}>
          {busy ? "建立中……" : "建立"}
        </button>
      )}
    </form>
  );
}
