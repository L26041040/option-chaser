/**
 * V2-04（#406）：指標旁的 ⓘ。文字一律來自 `metricHelp.ts`（唯一來源），
 * 互動與擺位沿用共用的 `InfoTooltip`（桌面懸停、手機點按、鍵盤 Enter／Esc）。
 */
import InfoTooltip from "./InfoTooltip";
import { METRIC_HELP, metricHelpLabel, type MetricHelpKey } from "./metricHelp";

export default function MetricInfo({ metric }: { metric: MetricHelpKey }) {
  const h = METRIC_HELP[metric];
  return (
    <InfoTooltip label={metricHelpLabel(metric)}>
      <span className="pinfo-title">{h.name}</span>
      <span className="pinfo-sec"><b>定義</b>{h.definition}</span>
      <span className="pinfo-sec"><b>方向</b>{h.direction}</span>
      <span className="pinfo-sec"><b>計算口徑</b>{h.basis}</span>
    </InfoTooltip>
  );
}

/**
 * 一列「指標說明：名稱ⓘ 名稱ⓘ …」。給每列重複出現同一組數字的清單與
 * 結果表（手機版表頭隱藏）用：說明只放一次，不在每一列重複放圖示。
 */
export function MetricHelpRow({ metrics }: { metrics: readonly MetricHelpKey[] }) {
  return (
    <p className="caption metric-help-row">
      <span>指標說明</span>
      {metrics.map((m) => (
        <span key={m} className="metric-help-item">
          {METRIC_HELP[m].name}
          <MetricInfo metric={m} />
        </span>
      ))}
    </p>
  );
}
