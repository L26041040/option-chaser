/**
 * 設定頁「機會搜尋」區塊（OS-02／#391，母票 #389 §6）——只給 Super User／
 * Super Admin（`Settings.tsx` 的 Normal 分支更早就 return，這裡不再判斷角色）。
 *
 * 兩道 Consensus Gate 門檻各自一個輸入框＋「恢復預設」、掃描股票範圍
 * （Search Universe）、策略家族、排序方式。幾條刻意的決定：
 *
 * - V2-03（#405）：第一道門檻以 PR 輸入（「分歧度歷史排序門檻：PR ≥ 80」），
 *   存回的仍是原百分位 `percentile_max = 100 − PR`（`dispersionRank.ts`）。
 *   欄位、單位與後端驗證都不變，新舊前端讀寫同一個值：舊值 20 ↔ PR ≥ 80。
 *
 * - 存檔走既有 `PUT /api/settings`；資料來源兩列照**已存的值**（`view`）
 *   帶上，不帶 `Settings.tsx` 那邊還沒按儲存的草稿——存機會搜尋不該順手
 *   存了別塊的半成品。
 * - 「恢復預設」是真的存檔：只送那一道門檻（後端欄位層級部分更新），
 *   另一道門檻與本區塊其他尚未儲存的修改都不動。
 * - 值的驗證交給後端：輸入框清空或打了不合法的數字照樣送出，畫面顯示
 *   後端回來的訊息，前端不自己吞掉、也不另寫一份規則。
 * - 選項（母體文案、家族、排序、預設值）由後端給；大型股樣本是暫定清單，
 *   文案照後端給的標示，絕不寫成 S&P 500。
 */
import { useState } from "react";

import {
  saveSettings,
  type OpportunitySearchPatch,
  type OpportunitySearchSettings as Opp,
  type SettingsView,
} from "./api";
import {
  PR_HISTORY_EXPLAINER,
  percentileMaxFromPrInput,
  prInputFromPercentileMax,
  prThresholdLabel,
} from "./dispersionRank";
import { FAMILY_LABELS } from "./family";
import MetricInfo from "./MetricInfo";
import type { MetricHelpKey } from "./metricHelp";

/** 區塊的 DOM id：機會搜尋頁「調整門檻」連到 `#/settings/opportunity`
 *  時，手機版設定頁捲到這裡（OS-05／#394）。 */
export const OPPORTUNITY_SETTINGS_ID = "settings-opportunity";

type Threshold = "percentile_max" | "dispersion_max";

/** 每道門檻的輸入單位：畫面上的值 ↔ 已存的值（API 欄位不變）。 */
const THRESHOLDS: Array<{
  key: Threshold;
  label: string;
  hint: string;
  /** ⓘ 說明（V2-04／#406）。 */
  help: MetricHelpKey;
  /** 已存的值 → 輸入框的值。 */
  toInput: (stored: number) => number;
  /** 輸入框的字串 → 要存的值（不是數字就原字串照送，讓後端回訊息）。 */
  fromInput: (text: string) => number | string;
  /** 已存的值 → 「預設 …」「已恢復預設（…）」裡的寫法。 */
  describe: (stored: number) => string;
}> = [
  {
    key: "percentile_max",
    label: "分歧度歷史排序門檻：PR ≥",
    hint: PR_HISTORY_EXPLAINER,
    help: "dispersionRank",
    toInput: prInputFromPercentileMax,
    fromInput: percentileMaxFromPrInput,
    describe: prThresholdLabel,
  },
  {
    key: "dispersion_max",
    label: "分析師分歧率上限（%）",
    hint: "分析師目標價的標準差 ÷ 平均",
    help: "dispersionRate",
    toInput: (stored) => stored,
    fromInput: numberOrRaw,
    describe: (stored) => `${stored}%`,
  },
];

const THRESHOLD_BY_KEY = Object.fromEntries(THRESHOLDS.map((t) => [t.key, t])) as
  Record<Threshold, (typeof THRESHOLDS)[number]>;

interface Draft {
  percentile_max: string;
  dispersion_max: string;
  universe_id: string;
  customText: string;
  strategies: string[];
  sort: Opp["sort"];
}

function draftFrom(opp: Opp): Draft {
  return {
    percentile_max: String(THRESHOLD_BY_KEY.percentile_max.toInput(opp.percentile_max)),
    dispersion_max: String(THRESHOLD_BY_KEY.dispersion_max.toInput(opp.dispersion_max)),
    universe_id: opp.universe_id,
    customText: opp.custom_symbols.join(", "),
    strategies: [...opp.strategies],
    sort: opp.sort,
  };
}

/** 能解析成數字就送數字；否則把原字串送出，讓後端回它的驗證訊息。 */
function numberOrRaw(text: string): number | string {
  const n = Number(text);
  return text.trim() !== "" && Number.isFinite(n) ? n : text;
}

/** 逗號（含全形）、空白、換行都當分隔；大小寫在這裡轉成大寫——後端只收
 *  大寫 ticker，去重與合法性由後端判斷。 */
function parseSymbols(text: string): string[] {
  return text.split(/[\s,，、]+/).filter(Boolean).map((s) => s.toUpperCase());
}

/** 舊後端（回滾期間的過期分頁）沒有 `opportunity_search_options` 時不渲染，
 *  不讓整個 Settings 頁崩潰。 */
export default function OpportunitySearchSettings(props: {
  view: SettingsView;
  onSaved: (next: SettingsView) => void;
}) {
  if (!props.view.opportunity_search_options || !props.view.opportunity_search) return null;
  return <OpportunitySearchSettingsForm {...props} />;
}

function OpportunitySearchSettingsForm({
  view,
  onSaved,
}: {
  view: SettingsView;
  onSaved: (next: SettingsView) => void;
}) {
  const options = view.opportunity_search_options;
  const [draft, setDraft] = useState<Draft>(() => draftFrom(view.opportunity_search));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  function edit(patch: Partial<Draft>) {
    setDraft((prev) => ({ ...prev, ...patch }));
    // 改了就把上一次的「已儲存」收掉——留著會讓人以為剛改的也存好了。
    setNotice(null);
  }

  async function put(opportunity: OpportunitySearchPatch): Promise<SettingsView | null> {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const next = await saveSettings({
        market_data: { mode: view.market_data.mode, provider: view.market_data.provider },
        historical_iv: { mode: view.historical_iv.mode, provider: view.historical_iv.provider },
        opportunity_search: opportunity,
      });
      onSaved(next);
      return next;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    const next = await put({
      universe_id: draft.universe_id,
      custom_symbols: parseSymbols(draft.customText),
      percentile_max: THRESHOLD_BY_KEY.percentile_max.fromInput(draft.percentile_max),
      dispersion_max: THRESHOLD_BY_KEY.dispersion_max.fromInput(draft.dispersion_max),
      strategies: draft.strategies,
      sort: draft.sort,
    });
    if (next) {
      setDraft(draftFrom(next.opportunity_search));
      setNotice("已儲存");
    }
  }

  async function restore(key: Threshold) {
    const t = THRESHOLD_BY_KEY[key];
    const next = await put({ [key]: options.defaults[key] });
    if (next) {
      setDraft((prev) => ({ ...prev, [key]: String(t.toInput(next.opportunity_search[key])) }));
      setNotice(`已恢復預設（${t.describe(options.defaults[key])}）`);
    }
  }

  function toggleFamily(family: string, on: boolean) {
    const set = new Set(draft.strategies);
    if (on) set.add(family);
    else set.delete(family);
    edit({ strategies: options.strategies.filter((f) => set.has(f)) });
  }

  return (
    <section className="card settings-section" aria-label="機會搜尋"
             id={OPPORTUNITY_SETTINGS_ID}>
      <h3 className="settings-usage-title">機會搜尋</h3>

      {THRESHOLDS.map(({ key, label, hint, help, describe }) => (
        <div className="settings-field" key={key}>
          <span className="settings-label-row">
            <label className="caption" htmlFor={`opp-${key}`}>{label}</label>
            <MetricInfo metric={help} />
          </span>
          <div className="settings-threshold-row">
            <input
              id={`opp-${key}`}
              className="settings-input"
              type="number"
              inputMode="decimal"
              min={0}
              max={100}
              step="any"
              value={draft[key]}
              onChange={(e) => edit({ [key]: e.target.value } as Partial<Draft>)}
            />
            <button
              className="pbtn line sm"
              onClick={() => void restore(key)}
              disabled={busy}
            >
              恢復預設
            </button>
          </div>
          <p className="caption">
            {hint}（預設 {describe(options.defaults[key])}）
          </p>
        </div>
      ))}

      <fieldset className="settings-fieldset" aria-labelledby="opp-universe-legend">
        <legend className="caption settings-label-row">
          <span id="opp-universe-legend">掃描股票範圍</span>
          <MetricInfo metric="scanUniverse" />
        </legend>
        {options.universes.map((u) => (
          <label className="settings-choice" key={u.id}>
            <input
              type="radio"
              name="opp-universe"
              checked={draft.universe_id === u.id}
              onChange={() => edit({ universe_id: u.id })}
            />
            <span>{u.label}</span>
          </label>
        ))}
        {draft.universe_id === "custom" && (
          <div className="settings-field">
            <label className="caption" htmlFor="opp-custom-symbols">Ticker 清單</label>
            <textarea
              id="opp-custom-symbols"
              className="settings-input"
              rows={3}
              value={draft.customText}
              onChange={(e) => edit({ customText: e.target.value })}
            />
            <p className="caption">
              以逗號或空白分隔，最多 {options.custom_symbols_max} 檔
            </p>
          </div>
        )}
      </fieldset>

      <fieldset className="settings-fieldset">
        <legend className="caption">策略家族</legend>
        {options.strategies.map((family) => (
          <label className="settings-choice" key={family}>
            <input
              type="checkbox"
              checked={draft.strategies.includes(family)}
              onChange={(e) => toggleFamily(family, e.target.checked)}
            />
            <span>{FAMILY_LABELS[family] ?? family}</span>
          </label>
        ))}
      </fieldset>

      <label className="settings-field">
        <span className="caption">排序方式</span>
        <select
          className="settings-select"
          value={draft.sort}
          onChange={(e) => edit({ sort: e.target.value as Opp["sort"] })}
        >
          {options.sorts.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
      </label>

      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}

      <div className="settings-actions">
        <button className="pbtn sm" onClick={() => void save()} disabled={busy}>
          {busy ? "儲存中……" : "儲存"}
        </button>
      </div>

      {notice && (
        <p className="caption" role="status">
          {notice}
        </p>
      )}
    </section>
  );
}
