import { useEffect, useState } from "react";
import type { UsageSummary } from "./api";
import { getUsageSummary } from "./api";
import { formatAnalyzedAt } from "./scenarios";

/**
 * SW-04（#333，Seed Warm）：手機首頁 stat 卡——沿用 OG-05／#324
 * `GET /api/me/usage-summary`（跟桌面版 `ScenarioList.tsx::
 * UsageStatsStrip` 同一份唯讀資料，零新增端點）的「進行中劇本」／
 * 「最近活動」／「刷新節流間隔」三項既有欄位。
 *
 * 施工時試過額外加一項「最佳劇本報酬」（從已經拿到手的 `rows` 算
 * `Math.max`，零額外請求）：Playwright 全套跑下去才發現這個數字經常
 * 跟畫面上那張劇本卡片自己顯示的報酬率**逐字重複**（例如兩邊都是
 * 「100.0%」），大量既有測試用 `page.getByText("<百分比>")`
 * 這種不特別限定容器的查詢，會因此撞上「找到不只一個」的 strict
 * mode violation——不是這裡的元件本身錯，是「同一個數字重複出現在
 * 頁面兩個地方」這件事本身就會製造這類意外的模糊性。拿掉這項，只留
 * 三個不會跟卡片內容重複的帳戶層級事實，SW-03（#334，桌面版）沿用
 * 同一個判斷，不重蹈覆轍。
 *
 * 刻意不與桌面版 `UsageStatsStrip` 共用同一個元件：桌面版重新設計是
 * SW-03（#334）獨立的票，這裡先讓手機版能獨立完工、獨立測試，不互相
 * 牽動兩張還在分頭施工的票（兩邊 `/code-review` 各自跟進即可）。
 */
export default function MobileStatsStrip() {
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getUsageSummary()
      .then((u) => alive && setUsage(u))
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, []);

  if (error) {
    // 同 `UsageStatsStrip` 既有理由：背景 stats 讀取失敗不搶頁面既有
    // `role="alert"` 的語意角色。
    return <p className="notice error">{error}</p>;
  }
  if (!usage) {
    return <p className="caption">用量摘要載入中……</p>;
  }

  return (
    <div className="mobile-stats-grid">
      <div className="pstat">
        <span className="pstat-k">進行中劇本</span>
        <span className="pstat-v">
          {usage.quota_exempt
            ? "豁免"
            : usage.max_active_scenarios === null
            ? `${usage.active_scenarios}`
            : `${usage.active_scenarios} / ${usage.max_active_scenarios}`}
        </span>
      </div>
      <div className="pstat">
        <span className="pstat-k">最近活動</span>
        <span className="pstat-v">
          {usage.last_activity_at === null
            ? "尚無紀錄"
            : formatAnalyzedAt(usage.last_activity_at)}
        </span>
      </div>
      <div className="pstat">
        <span className="pstat-k">刷新節流間隔</span>
        <span className="pstat-v">
          {usage.throttle_exempt
            ? "豁免"
            : usage.refresh_min_interval_minutes === null
            ? "停用"
            : `${usage.refresh_min_interval_minutes} 分鐘`}
        </span>
      </div>
    </div>
  );
}
