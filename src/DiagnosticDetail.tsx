/**
 * 診斷事件的共用格式化與複製邏輯（QA 反饋，2026-08-16）。
 *
 * Settings 的 Diagnostics 清單（`Diagnostics.tsx`）與 Historical IV
 * 卡片的 inline diagnostics（`IvHistory.tsx`）呈現的是同一種東西——
 * 一筆或多筆 `DiagnosticEvent` 的完整欄位、外加一鍵複製。兩處各自維護
 * 一套格式化規則與 Copy 邏輯是遲早會漂移的重複（先前確實已經漂移過：
 * `IvHistory.tsx` 一度直接印 `event.severity` 的原始英文字串，跟這裡
 * 用中文標籤的既有版本不一致）——這裡是唯一的事實來源，兩處都改成
 * 呼叫這裡的匯出。
 *
 * 前端零解讀邏輯：這裡只做格式化與呈現，`severity`／`stage`／
 * `message`／`context` 的內容全部原樣來自後端（DG-02 的 sanitize
 * 已經套用過）。
 */
import { useState } from "react";

import type { DiagnosticEvent } from "./api";

export const SEVERITY_LABELS: Record<DiagnosticEvent["severity"], string> = {
  info: "資訊", warning: "警告", error: "錯誤",
};

/** 一筆事件要顯示的 (標籤, 值) 清單——`context` 逐 key 展開，沿用既有
 *  「只顯示實際存在的欄位」原則（後端 sanitize 時已經把 `None` 拿掉，
 *  這裡不需要再過濾一次）。 */
export function diagnosticEventFields(event: DiagnosticEvent): [string, string][] {
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

/** 一筆事件的欄位清單，純呈現——呼叫端決定要不要在旁邊加 Copy 按鈕、
 *  加在哪個位置（Settings 清單與 Historical IV 卡片的版面順序不同，
 *  這裡只提供共用的那一塊）。 */
export function DiagnosticEventFieldList({ event }: { event: DiagnosticEvent }) {
  return (
    <dl className="diagnostics-detail-fields">
      {diagnosticEventFields(event).map(([label, value]) => (
        <div key={label} className="diagnostics-detail-row">
          <dt className="caption">{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * 一鍵複製，clipboard API 不可用或被拒時退回顯示一個唯讀、可全選的
 * 文字區塊——不是靜默失敗，也不是只丟一句「複製失敗」。任何要複製
 * 診斷內容的地方都用這個，不要另外做第二套格式化／複製邏輯。
 */
export function CopyDiagnosticButton({ text, label = "Copy" }: {
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
