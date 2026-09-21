/**
 * 自助刪除入口（PB-04／#296，Anonymous Public Beta）：「立刻刪除我的
 * 所有資料」——Normal User 對自己 owner_id 的操作，立即執行，不經過
 * PB-08 的 Abandoned／Grace Period 緩衝。
 *
 * 二次確認 modal 比照既有 `TrashView.tsx` 的 `ConfirmDeleteOne`／
 * `ConfirmDeleteBatch` 慣例（`.confirm-overlay`／`.confirm-sheet`）
 * ——本站唯一使用真 modal 的既有情境就是破壞性操作，這裡沿用同一套
 * 視覺語言與 `role="alertdialog"` 可及性寫法，不是另外發明一套。
 *
 * 刪除成功後整頁重新載入（`window.location.reload()`）：後端已經把
 * 這次 request 的舊 cookie 對應的身份清空，下一次請求會自然拿到一個
 * 全新、空的身份（見 `api_app/main.py::delete_my_data()` docstring）。
 * 前端不嘗試在記憶體裡局部清空 `App.tsx` 的既有狀態樹重建——重新整頁
 * 是最簡單、最不會遺漏某個沒清乾淨的畫面狀態的做法，且這本來就是一個
 * 低頻、破壞性、使用者已經有心理準備會「回到空白狀態」的操作。
 */
import { useState } from "react";

import { deleteMyData } from "./api";

function ConfirmDeleteMyData({
  busy,
  error,
  onCancel,
  onConfirm,
}: {
  busy: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="confirm-overlay">
      <div
        className="confirm-sheet"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-delete-my-data-heading"
      >
        <h2 id="confirm-delete-my-data-heading">刪除我的所有資料？</h2>
        <p>
          無法復原——全部劇本、分析歷史、報價快照與已儲存的設定都會立刻
          清除，不會進垃圾桶。
        </p>
        {error && (
          <p className="notice error" role="alert">
            {error}
          </p>
        )}
        <div className="confirm-actions">
          <button className="text-button" onClick={onCancel} disabled={busy}>
            取消
          </button>
          <button className="batch-pill danger" onClick={onConfirm} disabled={busy}>
            {busy ? "刪除中……" : "確定刪除"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function DeleteMyData() {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleConfirm() {
    setBusy(true);
    setError(null);
    try {
      await deleteMyData();
      window.location.hash = "#/";
      window.location.reload();
    } catch {
      setError("刪除失敗，請稍後再試一次。");
      setBusy(false);
    }
  }

  return (
    // SW-07（#336）：destructive 區塊——artifact 明文要求紅描邊，跟卡片
    // 上「危險文字鈕」用同一個紅色慣例（`--red`／`--down` 同一份既有
    // token），不是新發明一種警示色。
    <section className="card settings-section danger-zone" aria-label="刪除我的資料">
      <h2 className="section-title">刪除我的資料</h2>
      <p className="caption">
        立刻、不可逆地刪除你在本站儲存的全部資料——劇本、分析歷史、報價
        快照、設定與第三方資料源憑證。
      </p>
      <button
        type="button"
        className="text-button danger"
        onClick={() => setConfirming(true)}
      >
        立刻刪除我的所有資料
      </button>

      {confirming && (
        <ConfirmDeleteMyData
          busy={busy}
          error={error}
          onCancel={() => {
            setConfirming(false);
            setError(null);
          }}
          onConfirm={() => void handleConfirm()}
        />
      )}
    </section>
  );
}
