/**
 * 意見回饋（CLAUDE-BETA-LAUNCH-FINAL-001）：Normal User 設定頁的第一塊。
 *
 * 刻意只有兩個純文字欄位——稱呼、反饋內容。沒有分類、星等、email、
 * 附件、截圖、markdown、回覆系統。送出成功顯示一句「收到，謝謝你的
 * 回饋。」並清空內容欄（稱呼保留，方便再送一則）。
 *
 * 長度上限與後端 `FeedbackRequest` 一致；頭尾空白不算字，只有空白視同
 * 沒填。送回饋不會替還沒建立 owner 的新訪客建 owner（後端刻意不
 * materialize），這裡不需要 owner bootstrap。
 */
import { useState } from "react";

import { FEEDBACK_CONTENT_MAX, FEEDBACK_NAME_MAX, submitFeedback } from "./api";

export default function FeedbackForm() {
  const [name, setName] = useState("");
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSend = name.trim().length > 0 && content.trim().length > 0 && !busy;

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!canSend) return;
    setBusy(true);
    setError(null);
    setSent(false);
    try {
      await submitFeedback(name.trim(), content.trim());
      setContent("");
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "送出失敗，請稍後再試一次。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card settings-section" aria-label="意見回饋">
      <h2 className="section-title">意見回饋</h2>
      <form onSubmit={(e) => void send(e)}>
        <label className="settings-field">
          <span className="caption">稱呼</span>
          <input
            className="settings-input"
            type="text"
            value={name}
            maxLength={FEEDBACK_NAME_MAX}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="settings-field">
          <span className="caption">反饋內容</span>
          <textarea
            className="settings-input feedback-content"
            rows={4}
            value={content}
            maxLength={FEEDBACK_CONTENT_MAX}
            onChange={(e) => {
              setContent(e.target.value);
              setSent(false);
            }}
          />
        </label>
        <div className="settings-actions">
          <button type="submit" className="pbtn" disabled={!canSend}>
            {busy ? "送出中……" : "送出"}
          </button>
        </div>
      </form>
      {sent && <p className="caption" role="status">收到，謝謝你的回饋。</p>}
      {error && <p className="notice error" role="alert">{error}</p>}
    </section>
  );
}
