/**
 * 手機首頁最上方的 Dashboard 佔位區（MVP-v2／#77、#81）。
 *
 * 目前 MVP V2 尚未決定這裡要放哪些跨劇本報表或指標——需求方明確裁示
 * 「不要為了填滿空間自行發明 KPI」。這裡只保留版面位置：一塊低調但
 * 可見的區塊，內容只有標題與一句規劃中的說明，刻意不放任何數字（不
 * 重複工具列已有的劇本數、不重複最後刷新時間，更不自創指標）。
 *
 * 內容待跨劇本比較功能確定後另開票（見 spec #77〈Out of Scope〉）。
 * 只在手機版首頁渲染，桌面版面（#72／#75）不受影響。
 */
export default function Dashboard() {
  return (
    <section className="dashboard-placeholder" aria-label="Dashboard">
      <p className="dashboard-title">Dashboard</p>
      <p className="caption">跨劇本指標規劃中</p>
    </section>
  );
}
