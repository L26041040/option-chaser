/**
 * 首頁 Beta 說明（PB-12／#302，Anonymous Public Beta）：固定可見、
 * 非一次性彈窗、非 consent banner——涵蓋 spec §11／AC9 明文要求的
 * 四項事實：這是 Beta／資料存在這個瀏覽器的 cookie（清掉、換瀏覽器、
 * 無痕結束即無法找回）／閒置 30 天後緩衝 7 天會被清除／不是投資建議。
 *
 * 天數（30／7）在這裡匯出成具名常數，`PrivacyPage.tsx` 共用同一份
 * 而不是各自寫一次數字。**必須與後端 `api_app/main.py` 的
 * `ANONYMOUS_ABANDONED_AFTER_DAYS`／`ANONYMOUS_GRACE_PERIOD_DAYS`
 * 實際預設值一致**——前端沒有任何 API 呼叫可以即時查詢這兩個值（本票
 * Dependencies 只有 PB-02／PB-04，未要求新增這樣的端點），因此改用
 * `tests/test_pb12_beta_copy.py::test_the_days_hardcoded_in_the_
 * frontend_copy_match_the_backend_defaults` 從 Python 那一側直接
 * 讀取這個檔案裡的數字、與後端常數比對，任一邊改了另一邊沒跟著改，
 * 這條測試會紅——不是只靠這段註解口頭保證。
 *
 * 手機版渲染在 `Dashboard` 之前；桌面版（OG-02／#318 起）渲染在劇本庫
 * 頁面本身、跟著它一起隨 hash 切換出現或消失（切到詳細頁／垃圾桶／
 * 設定時不顯示）——比照手機版「只在這個裝置寬度下真正對應『首頁』的
 * 那個畫面出現一次」的既有裁示，桌面沒有獨立的首頁，劇本庫頁面就是
 * 那個位置。
 */
export const ANONYMOUS_ABANDONED_AFTER_DAYS = 30;
export const ANONYMOUS_GRACE_PERIOD_DAYS = 7;

export default function BetaNotice() {
  return (
    <section className="beta-notice" aria-label="Beta 版本說明">
      <p className="caption">
        Beta，非投資建議。資料存在瀏覽器 cookie，遺失不可復原；閒置
        {ANONYMOUS_ABANDONED_AFTER_DAYS}+{ANONYMOUS_GRACE_PERIOD_DAYS}
        天後清除。
      </p>
    </section>
  );
}
