/**
 * 免責聲明（SW-10／#340，Owner 真機驗收回饋）：取代原本 `BetaNotice.tsx`
 * 常駐在首頁的做法。
 *
 * 沿革：PB-12（#302）當時的 AC9 明文要求這段說明「固定可見、非彈窗、
 * 非需要 hover/focus 才展開的 tooltip」，SW-04（#333）施工時也確認過
 * 這與 Seed Warm「文案降級」的設計精神有衝突，但選擇維持常駐可見、
 * 不動（見該票 commit）。SW-10 是 Owner 親自用真機驗收後的直接裁示：
 * 首頁不該塞這類工程式、解釋式文案，Beta／cookie／非投資建議這幾件
 * 事收進設定頁的「免責聲明」這個獨立分頁——這是比 PB-12 更新的 HITL
 * 決定，取代原本 AC9 的常駐可見要求。
 *
 * 內容跟原本的 `BetaNotice`／`PrivacyPage.tsx`「留多久」「不是投資
 * 建議」兩節同一份事實，這裡只是換了個一定找得到、但不會擋主流程的
 * 位置。天數常數維持原本具名匯出（`PrivacyPage.tsx` 沿用同一份，
 * 一致性由 `tests/test_pb12_beta_copy.py` 從後端那側比對）。
 *
 * 「收益率以最差成交價計算」這句原本重複印在桌面/手機劇本庫清單頂端
 * 的計算口徑說明（V4／#52 舊裁示），Owner 這輪也要求從主流程移除、
 * 一併收進這裡——見 `ScenarioList.tsx`／`CompactScenarioList.tsx` 對應
 * 移除記錄。
 */
export const ANONYMOUS_ABANDONED_AFTER_DAYS = 30;
export const ANONYMOUS_GRACE_PERIOD_DAYS = 7;

export default function DisclaimerSection() {
  return (
    <section className="card settings-section" aria-label="免責聲明">
      <h2 className="section-title">免責聲明</h2>
      <p className="caption">
        Beta 測試版本，非投資建議：本站呈現的所有數字（含報酬率、機率、
        歷史走勢）僅供分析參考。劇本報酬以最差成交價計算（買腿 Ask −
        賣腿 Bid）。
      </p>
      <p className="caption">
        資料存在您目前使用的瀏覽器（cookie），清除瀏覽器資料、換一個
        瀏覽器、或結束無痕視窗都會讓您無法再存取；連續 {ANONYMOUS_ABANDONED_AFTER_DAYS}{" "}
        天沒有任何操作，資料會先進入 {ANONYMOUS_GRACE_PERIOD_DAYS} 天緩衝期，
        緩衝期滿仍無操作即自動、永久清除。
      </p>
      <p className="caption">
        完整說明（存了什麼、怎麼刪、清除 cookie 的具體後果）見
        <a href="#/privacy">隱私與資料政策</a>。
      </p>
    </section>
  );
}
