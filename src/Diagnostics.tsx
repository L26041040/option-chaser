/**
 * Settings 的 `Diagnostics / 報錯紀錄` 區塊（DG-06／#149，資料層見
 * DG-02／#145）。用途是保存近期 application diagnostic events，不必
 * 等下一次出錯就能回頭看最近發生過什麼。
 *
 * MVP，刻意不做的事（票上明文）：沒有 pagination、沒有搜尋引擎、沒有
 * 圖表、沒有 alerting、沒有跨 session 聚合分析。
 *
 * 前端零解讀邏輯：`severity`／`stage`／`message`／`context` 全是後端
 * 給的字串，這裡只做格式化與呈現——跟 `IvHistory.tsx` 的
 * `InlineDiagnostics` 同一種分層原則，只是這裡是清單而不是單一卡片。
 */
import { useEffect, useState } from "react";

import { clearDiagnostics, getDiagnostics, type DiagnosticEvent } from "./api";

const SEVERITY_LABELS: Record<DiagnosticEvent["severity"], string> = {
  info: "資訊", warning: "警告", error: "錯誤",
};

function eventFields(event: DiagnosticEvent): [string, string][] {
  return [
    ["時間", event.ts],
    ["事件 ID", event.event_id],
    ["Correlation ID", event.correlation_id],
    ["子系統", event.subsystem],
    ["階段", event.stage],
    ["嚴重程度", SEVERITY_LABELS[event.severity]],
    ["訊息", event.message],
    ...Object.entries(event.context).map(
      ([k, v]): [string, string] => [k, String(v)]),
  ];
}

/**
 * 複製失敗（clipboard API 不可用或被拒）時**退回顯示一個唯讀、可全選
 * 的文字區塊**——不是靜默失敗，也不是只丟一句「複製失敗」，使用者仍
 * 拿得到完整內容，只是得自己選取。
 */
function CopyButton({ text, label = "Copy" }: {
  text: string;
  label?: string;
}) {
  const [state, setState] = useState<"idle" | "copied" | "fallback">("idle");

  async function handleClick() {
    try {
      if (!navigator.clipboard?.writeText) throw new Error("clipboard 不可用");
      await navigator.clipboard.writeText(text);
      setState("copied");
      setTimeout(() => setState("idle"), 1500);
    } catch {
      setState("fallback");
    }
  }

  return (
    <div className="diagnostics-copy">
      <button className="pill" onClick={() => void handleClick()}>
        {state === "copied" ? "已複製" : label}
      </button>
      {state === "fallback" && (
        <textarea
          className="diagnostics-copy-fallback"
          readOnly
          value={text}
          aria-label="複製失敗，請手動全選複製"
          onFocus={(e) => e.currentTarget.select()}
        />
      )}
    </div>
  );
}

function EventDetail({ event }: { event: DiagnosticEvent }) {
  return (
    <div className="diagnostics-detail">
      <dl className="diagnostics-detail-fields">
        {eventFields(event).map(([label, value]) => (
          <div key={label} className="diagnostics-detail-row">
            <dt className="caption">{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <CopyButton text={JSON.stringify(event, null, 2)} />
    </div>
  );
}

function EventRow({ event }: { event: DiagnosticEvent }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="diagnostics-row">
      <button
        type="button"
        className="diagnostics-row-summary"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        {/* metadata 與 message 分兩行——手機窄螢幕塞不下一整行的
            timestamp＋subsystem＋stage＋severity＋message，硬擠會把
            message 擠到寬度歸零（QA-FIX-1／QA-FIX-4 同一類教訓）。 */}
        <span className="diagnostics-row-meta">
          <span className="diagnostics-row-ts">{event.ts}</span>
          <span className="diagnostics-row-subsystem">{event.subsystem}</span>
          <span className="diagnostics-row-stage">{event.stage}</span>
          <span className={`diagnostics-row-severity severity-${event.severity}`}>
            {SEVERITY_LABELS[event.severity]}
          </span>
        </span>
        <span className="diagnostics-row-message">{event.message}</span>
      </button>
      {open && <EventDetail event={event} />}
    </li>
  );
}

export default function Diagnostics() {
  const [events, setEvents] = useState<DiagnosticEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmingClear, setConfirmingClear] = useState(false);
  const [clearing, setClearing] = useState(false);

  useEffect(() => {
    let alive = true;
    getDiagnostics()
      .then((got) => alive && setEvents(got))
      .catch((e) => alive
        && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, []);

  async function handleClear() {
    setClearing(true);
    setError(null);
    try {
      await clearDiagnostics();
      setEvents([]);
      setConfirmingClear(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setClearing(false);
    }
  }

  return (
    <section className="card settings-section" aria-label="Diagnostics">
      <h3 className="settings-usage-title">Diagnostics / 報錯紀錄</h3>

      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}

      {events === null ? (
        <p className="caption">載入中……</p>
      ) : events.length === 0 ? (
        <p className="caption">目前沒有紀錄</p>
      ) : (
        <>
          <ul className="diagnostics-list">
            {events.map((event) => (
              <EventRow key={event.event_id} event={event} />
            ))}
          </ul>
          <div className="settings-actions">
            {confirmingClear ? (
              <>
                <span className="caption">確定清除全部紀錄？</span>
                <button className="pill" onClick={() => void handleClear()}
                       disabled={clearing}>
                  {clearing ? "清除中……" : "確定清除"}
                </button>
                <button className="text-button"
                       onClick={() => setConfirmingClear(false)}
                       disabled={clearing}>
                  取消
                </button>
              </>
            ) : (
              <button className="text-button danger"
                     onClick={() => setConfirmingClear(true)}>
                Clear diagnostics
              </button>
            )}
          </div>
        </>
      )}
    </section>
  );
}
