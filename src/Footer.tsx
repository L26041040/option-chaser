/**
 * 全站常駐頁尾（PB-12／#302，Anonymous Public Beta）——每一個畫面
 * 都看得到同一行：「非投資建議」＋「Beta，資料存在瀏覽器 cookie」的
 * 合併文字，外加隱私頁與回報問題兩個連結（票面 §2 Scope 明文）。
 *
 * `App.tsx` 在全部既有渲染分支（手機設定／手機垃圾桶／手機詳細頁／
 * 手機首頁／桌面 workspace）與這支元件自己的 `PrivacyPage.tsx` 都
 * 掛上它——不是只在首頁。回報問題連到本 repo 的 GitHub issues（純
 * 外部連結，不需要新增任何後端端點）。
 */
import { privacyHash } from "./route";

export default function Footer() {
  return (
    <footer className="site-footer">
      <p className="caption">
        非投資建議・Beta 版本，資料存在您目前使用的瀏覽器
        {" · "}
        <a href={privacyHash()}>隱私與資料政策</a>
        {" · "}
        <a
          href="https://github.com/L26041040/option-chaser/issues"
          target="_blank"
          rel="noreferrer"
        >
          回報問題
        </a>
      </p>
    </footer>
  );
}
