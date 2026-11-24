/**
 * V2-04（#406）：指標旁的 ⓘ。文字一律來自 `metricHelp.ts`（唯一來源），
 * 互動與擺位沿用共用的 `InfoTooltip`（桌面懸停、手機點按、鍵盤 Enter／Esc）。
 */
import InfoTooltip from "./InfoTooltip";
import {
  METRIC_HELP,
  metricHelpDescription,
  metricHelpLabel,
  type MetricHelpKey,
} from "./metricHelp";

/**
 * `decorative`：只給滑鼠懸停的視覺提示（放在 `<th>` 裡時用）——圖示對輔助科技
 * 隱藏、不進 Tab 順序，欄位名稱不會混進「…說明」。同一則說明必須另外有一顆
 * 一般的 ⓘ（例如 `MetricHelpRow`）給鍵盤與螢幕報讀器。
 */
export default function MetricInfo({
  metric,
  decorative = false,
}: {
  metric: MetricHelpKey;
  decorative?: boolean;
}) {
  const h = METRIC_HELP[metric];
  return (
    <InfoTooltip
      label={metricHelpLabel(metric)}
      description={decorative ? undefined : metricHelpDescription(metric)}
      decorative={decorative}
    >
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
export function MetricHelpRow({
  metrics,
  className,
}: {
  metrics: readonly MetricHelpKey[];
  className?: string;
}) {
  return (
    <p className={`caption metric-help-row${className ? ` ${className}` : ""}`}>
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
