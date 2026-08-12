/**
 * 設定頁（Settings／#124）：`Data / API` 兩列，各自「預設／自訂」二選一。
 *
 * 三條需求方裁示直接體現在這支元件的結構裡：
 *
 * 1. **自訂 ≠ 任意 API**——資料源是從後端白名單（`supported_providers`）
 *    來的下拉，不是一個可以填 URL 的輸入框。前端這份下拉只是方便，真正
 *    的防線在後端（`api_app/providers.py`）。
 * 2. **文案只寫「目前支援」**，不寫「推薦」、不做 vendor 比較、不寫未來
 *    規劃——這份清單描述的是系統現在有沒有那支 adapter，跟哪家比較好
 *    無關。有測試守門（`Settings.test.tsx`）。
 * 3. **一個 Provider 一把 credential**——`credentials` 以 provider 為 key，
 *    所以兩列選同一家時本來就是同一筆。第二列因此顯示「與 X 共用」而不是
 *    再要一次同樣的 token。
 *
 * 完整 token 只往一個方向走：使用者打字 → 送出。後端回來的永遠只有遮罩
 * 形式，這支元件也就沒有「把已存 token 顯示出來」的能力可言。
 */
import { useEffect, useState } from "react";

import {
  clearCredential,
  getSettings,
  saveCredential,
  saveSettings,
  testCredential,
  type CredentialState,
  type SettingsView,
  type UsageChoice,
} from "./api";

/** 兩列的識別鍵——與後端 `api_app/providers.py` 的 `USAGES` 同名。 */
type UsageKey = "market_data" | "historical_iv";

const USAGE_TITLES: Record<UsageKey, string> = {
  market_data: "Market Data",
  historical_iv: "Historical IV",
};

const USAGE_ORDER: UsageKey[] = ["market_data", "historical_iv"];

/** 三態的顯示文字（#125）。「尚未驗證」不是第四種狀態，是「已設定但
 *  還沒測」——把它講清楚，好過讓使用者以為存了就等於通了。 */
const STATE_LABELS: Record<CredentialState, string> = {
  unset: "未設定",
  unverified: "尚未驗證",
  ok: "已連線",
  failed: "驗證失敗",
};

type Draft = Record<UsageKey, UsageChoice>;

function draftFrom(view: SettingsView): Draft {
  return {
    market_data: {
      mode: view.market_data.mode,
      provider: view.market_data.provider,
    },
    historical_iv: {
      mode: view.historical_iv.mode,
      provider: view.historical_iv.provider,
    },
  };
}

export default function Settings() {
  const [view, setView] = useState<SettingsView | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  // 使用者剛打的 token，依「資料用途」分開記——即使兩列指向同一個
  // Provider，兩個輸入框仍是各自的欄位；送出時走的才是同一把 credential。
  const [tokens, setTokens] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<UsageKey | null>(null);
  const [testing, setTesting] = useState<UsageKey | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<UsageKey | null>(null);

  useEffect(() => {
    let alive = true;
    getSettings()
      .then((v) => {
        if (!alive) return;
        setView(v);
        setDraft(draftFrom(v));
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, []);

  function choose(usage: UsageKey, choice: UsageChoice) {
    setDraft((prev) => (prev ? { ...prev, [usage]: choice } : prev));
    // 改了選擇就把「已儲存」的提示收掉——留著會讓人以為剛改的那一下也
    // 已經存好了。
    setSaved(null);
  }

  /** 存這一列：模式一定送（後端一次收兩列，所以連同另一列的現況一起
   *  送出），該列有打 token 才連 credential 一起送。 */
  async function save(usage: UsageKey) {
    if (!draft) return;
    setBusy(usage);
    setError(null);
    try {
      let next = await saveSettings(draft);
      const typed = (tokens[usage] ?? "").trim();
      const provider = draft[usage].provider;
      if (typed && provider) {
        next = await saveCredential(provider, typed);
      }
      setView(next);
      setDraft(draftFrom(next));
      // 送出後就地清掉——完整 token 沒有留在畫面上的理由，留著只是多一份
      // 暴露面。
      setTokens((prev) => ({ ...prev, [usage]: "" }));
      setSaved(usage);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  /** 測試連線（#125）：驗證失敗不是例外，狀態就在回傳的 view 裡。 */
  async function test(usage: UsageKey) {
    const provider = draft?.[usage].provider;
    if (!provider) return;
    setTesting(usage);
    setError(null);
    try {
      setView(await testCredential(provider));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setTesting(null);
    }
  }

  async function clear(provider: string) {
    setError(null);
    try {
      const next = await clearCredential(provider);
      setView(next);
      setDraft(draftFrom(next));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="screen">
      <div className="settings-head">
        <a className="nav-back" href="#/">
          ‹ 劇本庫
        </a>
        <h1 className="toolbar-title">設定</h1>
      </div>

      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}

      <h2 className="section-title">Data / API</h2>

      {!view || !draft ? (
        <p className="caption">載入中……</p>
      ) : (
        USAGE_ORDER.map((usage) => (
          <UsageSection
            key={usage}
            usage={usage}
            view={view}
            draft={draft}
            token={tokens[usage] ?? ""}
            busy={busy === usage}
            testing={testing === usage}
            justSaved={saved === usage}
            onChoose={(choice) => choose(usage, choice)}
            onToken={(v) => setTokens((prev) => ({ ...prev, [usage]: v }))}
            onSave={() => void save(usage)}
            onTest={() => void test(usage)}
            onClear={clear}
          />
        ))
      )}
    </div>
  );
}

function UsageSection({
  usage,
  view,
  draft,
  token,
  busy,
  testing,
  justSaved,
  onChoose,
  onToken,
  onSave,
  onTest,
  onClear,
}: {
  usage: UsageKey;
  view: SettingsView;
  draft: Draft;
  token: string;
  busy: boolean;
  testing: boolean;
  justSaved: boolean;
  onChoose: (choice: UsageChoice) => void;
  onToken: (value: string) => void;
  onSave: () => void;
  onTest: () => void;
  onClear: (provider: string) => void;
}) {
  const choice = draft[usage];
  const custom = choice.mode === "custom";
  const options = view.supported_providers;
  // 選自訂但還沒挑資料源時，就用清單第一家當預設選擇——目前只有一家，
  // 讓使用者為了一個沒有第二選項的下拉多點一下沒有意義。
  const provider = choice.provider ?? options[0]?.id ?? null;
  const cred = provider ? view.credentials[provider] : undefined;
  const configured = cred?.configured ?? false;
  const state: CredentialState = cred?.status ?? "unset";

  // credential 是 per-Provider 的一把，所以「誰負責輸入它」必須有唯一
  // 答案：**由上而下第一個使用該 Provider 的自訂列**負責，其餘列只說
  // 自己共用。這條規則同時解掉兩種情況——兩列都自訂時輸入框在 Market
  // Data（＝需求方草圖），只有 Historical IV 自訂時輸入框就出現在它那
  // 列，不會變成「要設 token 卻無處可設」。
  const ownerUsage = USAGE_ORDER.find(
    (u) =>
      draft[u].mode === "custom" &&
      (draft[u].provider ?? options[0]?.id ?? null) === provider,
  );
  const ownsCredential = ownerUsage === usage;
  const sharesFrom = ownsCredential ? null : ownerUsage;

  const radioName = `mode-${usage}`;

  return (
    <section className="card settings-section" aria-label={USAGE_TITLES[usage]}>
      <h3 className="settings-usage-title">{USAGE_TITLES[usage]}</h3>

      <label className="settings-choice">
        <input
          type="radio"
          name={radioName}
          checked={!custom}
          onChange={() => onChoose({ mode: "default", provider: null })}
        />
        <span>預設：{view[usage].default_label}</span>
      </label>

      <label className="settings-choice">
        <input
          type="radio"
          name={radioName}
          checked={custom}
          onChange={() => onChoose({ mode: "custom", provider })}
        />
        <span>自訂</span>
      </label>

      {/* #125：選了自訂卻沒真的用上自訂時，說出來。靜默退回會讓使用者
          以為分析用的是他挑的那家資料源，而其實不是。 */}
      {usage === "market_data" && view.market_data_effective.fallback && (
        <p className="notice settings-fallback" role="status">
          目前使用 {view.market_data_effective.source}：
          {view.market_data_effective.reason}
        </p>
      )}

      {custom && (
        <div className="settings-custom">
          {/* 需求方裁示的兩行文案，不多不少：不寫「推薦」、不比較 vendor、
              不寫未來規劃。 */}
          <p className="caption">
            目前支援：{options.map((p) => p.label).join("、")}
          </p>
          <p className="caption">需自行申請 API Token</p>

          <label className="settings-field">
            <span className="caption">資料源</span>
            <select
              className="settings-select"
              value={provider ?? ""}
              onChange={(e) => onChoose({ mode: "custom", provider: e.target.value })}
            >
              {options.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>

          {sharesFrom ? (
            // 共用的那一列**完全不要求輸入**——不論設定過沒有。同一把
            // token 打兩次沒有意義，而「還沒設定所以再給你一個輸入框」
            // 正是需求方要收掉的那條路徑（#127）。
            <p className="caption settings-shared">與上方共用 credential</p>
          ) : (
            <label className="settings-field">
              <span className="caption">API Token</span>
              <input
                className="settings-input"
                type="password"
                autoComplete="off"
                value={token}
                placeholder={
                  configured ? "留白＝維持現有 token" : "貼上 API Token"
                }
                onChange={(e) => onToken(e.target.value)}
              />
            </label>
          )}

          <p className="caption settings-status">
            <span className={`settings-dot state-${state}`} aria-hidden="true" />
            {STATE_LABELS[state]}
            {configured && `　·　已儲存 ${cred?.masked}`}
          </p>

          {cred?.reason && (
            <p className="caption settings-reason">{cred.reason}</p>
          )}

          {/* credential 的操作（測試連線、清除）只屬於持有它的那一列——
              共用列重複一份，按下去做的是同一件事，只會讓人以為有兩把。
              「儲存」兩列都要有：模式選擇是各列自己的狀態，得存得起來。 */}
          <div className="settings-actions">
            {ownsCredential && (
              <button className="pill" onClick={onTest}
                     disabled={testing || !configured}>
                {testing ? "測試中……" : "測試連線"}
              </button>
            )}
            <button className="pill" onClick={onSave} disabled={busy}>
              {busy ? "儲存中……" : "儲存"}
            </button>
            {ownsCredential && configured && provider && (
              <button
                className="text-button danger"
                onClick={() => onClear(provider)}
              >
                清除 token
              </button>
            )}
          </div>

          {justSaved && (
            <p className="caption" role="status">
              已儲存
            </p>
          )}
        </div>
      )}

      {!custom && justSaved && (
        <p className="caption" role="status">
          已儲存
        </p>
      )}

      {!custom && (
        <div className="settings-actions">
          <button className="pill" onClick={onSave} disabled={busy}>
            {busy ? "儲存中……" : "儲存"}
          </button>
        </div>
      )}
    </section>
  );
}
