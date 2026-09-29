/**
 * Super Admin 意見回饋 inbox（CLAUDE-BETA-LAUNCH-FINAL-001）。
 *
 * 封測規模很小，刻意只有最小功能：最新在最上、時間、稱呼、內容。沒有
 * 搜尋、標籤、指派、狀態、回覆、分頁框架——一次讀最近 100 則。
 * `owner_hint` 只是 owner_id 前 6 碼（辨認「同一個人送了好幾則」用），
 * 匿名回饋沒有。內容一律當純文字 render（React 預設跳脫），不解析 HTML
 * 或 markdown。
 *
 * 只在 `SuperUserAdmin`（`#/admin`，已經 gate 在 Super Admin）裡掛載；
 * `reloadKey` 變動時重讀一次（Reset 之後 inbox 要跟著變空）。
 */
import { useEffect, useState } from "react";

import { superuserListFeedback, type FeedbackEntry } from "./api";
import { formatArchivedAt } from "./scenarios";

export default function FeedbackInbox({ reloadKey = 0 }: { reloadKey?: number }) {
  const [rows, setRows] = useState<FeedbackEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    superuserListFeedback()
      .then((r) => {
        if (!alive) return;
        setRows(r);
        setError(null);
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => { alive = false; };
  }, [reloadKey]);

  return (
    <section className="settings-section" aria-label="意見回饋">
      <h3 className="settings-usage-title">意見回饋</h3>
      {error ? (
        <p className="notice error" role="alert">{error}</p>
      ) : rows === null ? (
        <p className="caption">載入中……</p>
      ) : rows.length === 0 ? (
        <p className="caption">目前還沒有任何回饋。</p>
      ) : (
        <ul className="feedback-inbox">
          {rows.map((row) => (
            <li key={row.feedback_id}>
              <p className="caption">
                {formatArchivedAt(row.created_at)}・{row.display_name}
                {row.owner_hint && `・${row.owner_hint}`}
              </p>
              <p className="feedback-inbox-text">{row.content}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
