/**
 * V2-06（#408）：成本與最大損失的「每股／每口」兩種單位——**只換單位，不重算**。
 *
 * 後端欄位的單位是固定的（`api_app/opportunity_search.py` 欄位表）：
 * - `entry_cost`＝候選的 `natural_cost`，**每股**（最差成交）→ 每口＝每股 × 100；
 * - `max_loss_per_contract`，**每口**（100 股）→ 每股＝每口 ÷ 100。
 *
 * 最大損失不從成本推（broken-wing Butterfly 的最大損失可能超過已付權利金），
 * 兩個數字各自從自己的後端欄位換單位。結果表（`OpportunityPage.tsx`）與劇本
 * 詳細頁（`ScenarioDetail.tsx`／`DesktopDetail.tsx`／`AnalysisReport.tsx`）共用
 * 這裡，存成劇本後兩邊顯示同一組數字。
 */
import { money } from "./scenarios";

/** 1 口 = 100 股。 */
export const SHARES_PER_CONTRACT = 100;

export const perContract = (perShare: number) => perShare * SHARES_PER_CONTRACT;
export const perShare = (perContractValue: number) => perContractValue / SHARES_PER_CONTRACT;

export interface PerShareAndContract {
  perShare: number;
  perContract: number;
}

/** 一列（或一個候選）的成本與最大損失，兩種單位各一份。 */
export function costAndMaxLoss(row: {
  entry_cost: number;
  max_loss_per_contract: number;
}): { cost: PerShareAndContract; maxLoss: PerShareAndContract } {
  return {
    cost: { perShare: row.entry_cost, perContract: perContract(row.entry_cost) },
    maxLoss: {
      perShare: perShare(row.max_loss_per_contract),
      perContract: row.max_loss_per_contract,
    },
  };
}

/** 「$0.81 / 股」。 */
export const perShareText = (x: number) => `${money(x)} / 股`;
/** 「$81.00 / 口」。 */
export const perContractText = (x: number) => `${money(x)} / 口`;
