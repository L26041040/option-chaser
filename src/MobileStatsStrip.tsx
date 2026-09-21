import { useEffect, useState } from "react";
import type { UsageSummary } from "./api";
import { getUsageSummary } from "./api";
import { strategyLabel } from "./detail";
import { formatReturn } from "./scenarios";

/**
 * SW-04（#333，Seed Warm）→ SW-10（#340，Owner 真機驗收）：手機首頁
 * stat 卡，沿用 `GET /api/me/usage-summary`（跟桌面版
 * `ScenarioList.tsx::UsageStatsStrip` 同一份唯讀資料，零新增請求）。
 *
 * SW-10 改版：Owner 真機驗收後直接裁示「最近活動」「刷新節流間隔」
 * 兩格拿掉——後者本來就是已經整段移除的產品層節流限制，前者對一般
 * 使用者沒有產品價值。改回 Artifact A 首頁 stats 板原本的第二格
 * 「最佳劇本報酬」（`best_return*`，後端一次算好，不是這裡重新掃
 * `rows` 算 `Math.max`）。
 *
 * 舊版曾經試過用前端 `Math.max(rows)` 算「最佳劇本報酬」但撤回，原因
 * 記在這份檔案舊版的檔頭：那個數字經常跟畫面上某張劇本卡片自己顯示
 * 的報酬率逐字重複，既有 `page.getByText("<百分比>")` 這類不特別限定
 * 容器的查詢會因此撞上「找到不只一個」。這次改由後端算好同一個數字
 * ——數字本身沒有變，重複的風險原則上仍在，差別是這次是 Owner 明確
 * 要求要有這一格、且核准過「不能再用既有 component 限制當理由」，
 * 所以不是撤回這個功能，而是既有 e2e 斷言改用 `.mobile-stats-grid`
 * 這類容器 scope 查詢來消歧義（見 e2e 測試改動）。
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
        <span className="pstat-k">最佳報酬</span>
        {usage.best_return === null ? (
          <span className="pstat-v muted">—</span>
        ) : (
          <>
            <span className={`pstat-v ${usage.best_return >= 0 ? "up" : "down"}`}>
              {formatReturn(usage.best_return)}
            </span>
            <span className="pstat-d">
              {usage.best_return_symbol}
              {usage.best_return_strategy &&
                ` · ${strategyLabel(usage.best_return_strategy)}`}
            </span>
          </>
        )}
      </div>
    </div>
  );
}
