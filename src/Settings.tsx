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
  saveCredential,
  saveSettings,
  testCredential,
  type CredentialState,
  type SettingsView,
  type UsageChoice,
} from "./api";
import DeleteMyData from "./DeleteMyData";
import Diagnostics from "./Diagnostics";
import { getSettingsCached, setSettingsCache } from "./fetchCache";
import RoleLogin from "./RoleLogin";
import SuperUserAdmin from "./SuperUserAdmin";
import { roleAtLeast, type Role } from "./superuser";
import { useIsDesktop } from "./useIsDesktop";

/**
 * OG-11（#322）：桌面設定頁左側 subnav 的分頁鍵——內容跟手機版單欄
 * 堆疊逐字相同，只是桌面版把它們拆成「一次只顯示一塊」的分頁，不是
 * 重新設計每一塊各自的內容。「管理後台」只在達到 Super Admin 才出現
 * 在 subnav 清單裡（跟手機版 `roleAtLeast(role, "superadmin") &&
 * &lt;SuperUserAdmin /&gt;` 同一個守門條件，只是手機版是「有沒有這一塊」，
 * 桌面版多一步「這一塊在不在分頁清單裡」）。
 */
type SettingsSection = "general" | "datasource" | "diagnostics" | "delete" | "admin";

const SECTION_LABELS: Record<SettingsSection, string> = {
  general: "一般",
  datasource: "資料來源",
  diagnostics: "診斷",
  delete: "刪除我的資料",
  admin: "管理後台",
};

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
  // AUTH-06（#313）：軸二狀態——三層角色，決定要不要顯示自訂 provider
  // token 輸入（>= superadmin，AUTH-03 起 credential CRUD 收斂為
  // Super-Admin-only）與跨 owner 管理面板（== superadmin）。
  const [role, setRole] = useState<Role>("normal");
  const isDesktop = useIsDesktop();
  // OG-11（#322）：桌面版 subnav 目前選中哪一塊——手機版不需要這個
  // state（單欄堆疊全部一次顯示），只在 `isDesktop` 分支使用。
  const [activeSection, setActiveSection] = useState<SettingsSection>("general");

  // T03（#187）：走快取——與 `IvHistory` 自己那次讀取共用同一份
  // settings 結果，不各自 mount 各抓一次。
  useEffect(() => {
    let alive = true;
    const { promise, release } = getSettingsCached();
    promise
      .then((v) => {
        if (!alive) return;
        setView(v);
        setDraft(draftFrom(v));
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
      release();
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
      setSettingsCache(next);   // T03（#187）：這次拿到的就是最新狀態
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
      const next = await testCredential(provider);
      setView(next);
      setSettingsCache(next);   // T03（#187）
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
      setSettingsCache(next);   // T03（#187）
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  // 「Data / API」這一塊的內容手機／桌面逐字相同，抽成一個變數只是
  // 避免兩個分支各自貼一份一模一樣的 JSX（純提取，不改變任何條件式
  // 或渲染結果——手機分支拿到的還是原本那份 `USAGE_ORDER.map(...)`）。
  const datasourcePanel = (
    <>
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
            canManageCredential={roleAtLeast(role, "superadmin")}
            onChoose={(choice) => choose(usage, choice)}
            onToken={(v) => setTokens((prev) => ({ ...prev, [usage]: v }))}
            onSave={() => void save(usage)}
            onTest={() => void test(usage)}
            onClear={clear}
          />
        ))
      )}
    </>
  );

  // OG-11（#322）：桌面 subnav 的分頁清單——「管理後台」只在達到
  // Super Admin 時出現，跟手機版 `roleAtLeast(role, "superadmin") &&
  // <SuperUserAdmin />` 同一個守門條件。角色降級（例如登出）導致目前
  // 選中的分頁不再存在時，退回第一個可用分頁——與 `FamilyTabs.tsx::
  // resolveFamily()` 同一種「使用者選擇優先、退回預設」寫法。
  const availableSections: SettingsSection[] = roleAtLeast(role, "superadmin")
    ? ["general", "datasource", "diagnostics", "delete", "admin"]
    : ["general", "datasource", "diagnostics", "delete"];
  const currentSection = availableSections.includes(activeSection)
    ? activeSection : availableSections[0];

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

      {isDesktop ? (
        <div className="settings-shell">
          <nav className="settings-subnav" role="tablist" aria-label="設定">
            {availableSections.map((key) => (
              <button
                key={key}
                role="tab"
                aria-selected={currentSection === key}
                className={currentSection === key ? "chip selected" : "chip"}
                onClick={() => setActiveSection(key)}
              >
                {SECTION_LABELS[key]}
              </button>
            ))}
          </nav>
          <div className="settings-panel">
            {currentSection === "general" && (
              <RoleLogin role={role} onChange={setRole} />
            )}
            {/* PB-10（#301）／AUTH-06（#313）：跨 owner 檢視／管理僅在
                角色達到 Super Admin 才掛載——未達門檻時這塊分頁根本不在
                `availableSections` 裡，不會被選中、也不會掛載，不打任何
                `/api/superuser/owners*` 請求。伺服器端 401 只是第二道
                防線，不是唯一防線。 */}
            {currentSection === "admin" && <SuperUserAdmin />}
            {currentSection === "datasource" && datasourcePanel}
            {currentSection === "diagnostics" && <Diagnostics />}
            {currentSection === "delete" && <DeleteMyData />}
          </div>
        </div>
      ) : (
        <>
          <RoleLogin role={role} onChange={setRole} />

          {/* PB-10（#301）／AUTH-06（#313）：跨 owner 檢視／管理僅在角色
             達到 Super Admin 才掛載——未達門檻時不打任何
             `/api/superuser/owners*` 請求，伺服器端 401 只是第二道防線，
             不是唯一防線。 */}
          {roleAtLeast(role, "superadmin") && <SuperUserAdmin />}

          {datasourcePanel}

          <Diagnostics />

          <DeleteMyData />
        </>
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
  canManageCredential,
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
  /** AUTH-03（#310）：`owner_credentials` 的寫入路徑（設定／測試／
   *  清除 token）gate 在 Super Admin——Normal／Super User 看得到
   *  「自訂」這個選項本身（純偏好設定，不涉及 credential），但看不到
   *  token 輸入框，見下方渲染區塊。呼叫端已經算好
   *  `roleAtLeast(role, "superadmin")`，這裡只消費結果，不自己判斷
   *  角色高低（票面 Implementation constraints）。 */
  canManageCredential: boolean;
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
          ) : !canManageCredential ? (
            // AUTH-03（#310）：`owner_credentials` 寫入路徑 gate 在
            // Super Admin（OD-3：匿名者不得存第三方 token）——輸入框
            // 直接不呈現，不是呈現後靠後端 401 擋，事實陳述、非評價
            // 字眼。
            <p className="caption settings-shared">
              需要 Super Admin 身份才能設定 API Token
            </p>
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
            {ownsCredential && canManageCredential && (
              <button className="pbtn line sm" onClick={onTest}
                     disabled={testing || !configured}>
                {testing ? "測試中……" : "測試連線"}
              </button>
            )}
            <button className="pbtn sm" onClick={onSave} disabled={busy}>
              {busy ? "儲存中……" : "儲存"}
            </button>
            {ownsCredential && canManageCredential && configured && provider && (
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
          <button className="pbtn sm" onClick={onSave} disabled={busy}>
            {busy ? "儲存中……" : "儲存"}
          </button>
        </div>
      )}
    </section>
  );
}
