/**
 * 極簡隱私頁（PB-12／#302，Anonymous Public Beta）——票面 §2 Scope
 * 明文要求的六項內容：存了什麼、留多久、怎麼刪、清 cookie 的後果、
 * 不是投資建議、Beta 狀態。第一版只做中文（Non-goals 明文）。
 *
 * 「怎麼刪」連到**真的存在**的自助刪除入口（PB-04／#296 的
 * `DeleteMyData.tsx`，已掛在 `Settings.tsx` 裡）——這裡不重複渲染
 * 那個元件本身，用一個連結指過去；那個按鈕本身早已有自己的單元
 * 測試與二次確認流程，不需要在這裡再實作一份。
 *
 * `App.tsx` 把這支元件當成獨立於手機／桌面版面之外的第三種畫面
 * （比照 `showSettings`／`showTrash` 同一套 hash 驅動慣例，但**不分
 * 裝置寬度**——隱私頁不屬於任何工作區脈絡，手機與桌面共用同一個
 * 渲染路徑）。
 *
 * 天數與 `DisclaimerSection.tsx`（SW-10／#340 起取代原本
 * `BetaNotice.tsx`）共用同一份具名常數（見那份檔案的 docstring：與
 * 後端實際預設值的一致性由 `tests/test_pb12_beta_copy.py` 守住）。
 */
import {
  ANONYMOUS_ABANDONED_AFTER_DAYS,
  ANONYMOUS_GRACE_PERIOD_DAYS,
} from "./DisclaimerSection";
import { settingsHash } from "./route";

export default function PrivacyPage() {
  return (
    <div className="screen">
      <section className="card">
        <h2 className="section-title">隱私與資料政策</h2>
        <p className="caption">
          Beta 測試版本。以下如實描述目前的實際行為，會隨產品調整而
          更新，不是行銷用語。
        </p>
      </section>

      <section className="card">
        <h3 className="section-title">存了什麼</h3>
        <p className="caption">
          您建立的劇本、分析結果，以及一個用來識別「這是同一個瀏覽器」
          的隨機代碼（存在瀏覽器的 cookie 裡）。使用本站不需要、也不會
          要求您提供姓名、email 或任何其他個人身分資訊。
        </p>
      </section>

      <section className="card">
        <h3 className="section-title">留多久</h3>
        <p className="caption">
          連續 {ANONYMOUS_ABANDONED_AFTER_DAYS} 天沒有任何操作（開站
          時自動刷新既有劇本不算操作），資料會先進入{" "}
          {ANONYMOUS_GRACE_PERIOD_DAYS} 天緩衝期；緩衝期內只要有任何
          操作即恢復正常。緩衝期滿仍無操作，系統會自動、永久清除。
        </p>
      </section>

      <section className="card">
        <h3 className="section-title">怎麼刪</h3>
        <p className="caption">
          您可以隨時到<a href={settingsHash()}>設定頁</a>
          按下「刪除我的全部資料」立即清除，不必等待閒置期限，也不需要
          任何人工協助。
        </p>
      </section>

      <section className="card">
        <h3 className="section-title">清除瀏覽器 cookie 的後果</h3>
        <p className="caption">
          識別身份的代碼只存在您的瀏覽器裡，我們沒有其他方式能替您
          找回它。清除瀏覽器資料、換一個瀏覽器、或結束無痕視窗，都會
          讓您無法再存取先前建立的劇本——這與上一段「刪除我的全部
          資料」是兩件不同的事：那是您主動、立即刪除；這裡說的是資料
          可能還在，只是這台瀏覽器已經找不到通往它的鑰匙。
        </p>
      </section>

      <section className="card">
        <h3 className="section-title">不是投資建議</h3>
        <p className="caption">
          本站呈現的所有數字（含報酬率、機率、歷史走勢）僅供分析參考，
          不構成、也不應被視為投資建議。
        </p>
      </section>

      <section className="card">
        <h3 className="section-title">Beta 狀態</h3>
        <p className="caption">
          本站目前為 Beta 測試版本，功能與資料保留政策可能持續調整。
        </p>
      </section>

      <section className="card">
        <p className="caption">
          發現問題？
          <a
            href="https://github.com/L26041040/option-chaser/issues"
            target="_blank"
            rel="noreferrer"
          >
            回報到 GitHub issue
          </a>
          （提醒：GitHub issue 是公開的，請不要在裡面貼出您的劇本內容
          或任何個人資訊）。
        </p>
      </section>
    </div>
  );
}
