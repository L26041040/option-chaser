/**
 * 原始資料（當次快照，V8／#56）：查看與 CSV 下載——「免得你亂掰我卻查不到
 * 證據」（QA1-10／#37 原話，延續同一設計目標到新前端）。
 *
 * 逐筆合約報價只在分析當下拿得到（後端 V2 已把它跟結果分開存，見
 * `api_app/main.py` 的 `save_snapshot`），這裡按需抓一次（`GET
 * /api/scenarios/{id}/raw-data`）——跟候選池診斷／分析報告不同，這份資料
 * 不隨 `latest_result` 一起下載，展開才拉，省掉平常瀏覽不需要的流量。
 *
 * CSV 下載直接是 `<a href>`，不走 JS fetch＋blob：後端已經送
 * `Content-Disposition: attachment`，瀏覽器原生處理下載，程式碼最少。
 *
 * 零金融計算：表格逐欄直接印報價，CSV 內容正確性由既有純函式
 * `data.snapshot.snapshot_to_csv` 的測試覆蓋（QA1-10／#37），前端只驗接線。
 */
import { useState } from "react";

import { getRawData, rawDataCsvUrl, type RawSnapshot } from "./api";
import { money } from "./scenarios";

export default function RawData({ scenarioId, analyzedAt = null }: {
  scenarioId: string;
  /** 這次分析的時間戳（#69）——只用來替 CSV 下載連結加快取破壞參數，
   *  見 `rawDataCsvUrl`。 */
  analyzedAt?: string | null;
}) {
  const [data, setData] = useState<RawSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // 展開才抓一次；已經抓過或正在抓就不重複打。
  function onToggle(e: React.SyntheticEvent<HTMLDetailsElement>) {
    if (!e.currentTarget.open || data || loading) return;
    setLoading(true);
    setError(null);
    getRawData(scenarioId)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }

  return (
    <details className="card" onToggle={onToggle}>
      <summary className="section-title">原始資料（當次快照）</summary>

      {loading && <p className="caption">載入中……</p>}
      {error && <p className="notice error">{error}</p>}

      {data && (
        <>
          <div className="row">
            <span className="row-label">標的</span>
            <span className="row-value">{data.meta.symbol}</span>
          </div>
          <div className="row">
            <span className="row-label">現價</span>
            <span className="row-value">{money(data.meta.spot)}</span>
          </div>
          <div className="row">
            <span className="row-label">資料時間</span>
            <span className="row-value">{data.meta.fetched_at}</span>
          </div>
          <div className="row">
            <span className="row-label">來源</span>
            <span className="row-value">{data.meta.source}</span>
          </div>
          <div className="row">
            <span className="row-label">合約數</span>
            <span className="row-value">{data.meta.contract_count} 筆</span>
          </div>

          <a className="button raw-data-download"
            href={rawDataCsvUrl(scenarioId, analyzedAt)} download>
            下載 CSV
          </a>

          <div className="raw-data-scroll">
            <table className="report-table">
              <caption className="sr-only">
                {data.meta.symbol} 原始選擇權鏈快照，逐筆合約報價
              </caption>
              <thead>
                <tr>
                  <th scope="col">合約</th>
                  <th scope="col">類型</th>
                  <th scope="col">履約價</th>
                  <th scope="col">到期日</th>
                  <th scope="col">Bid</th>
                  <th scope="col">Ask</th>
                  <th scope="col">Last</th>
                  <th scope="col">成交量</th>
                  <th scope="col">未平倉量</th>
                  <th scope="col">IV</th>
                </tr>
              </thead>
              <tbody>
                {data.contracts.map((c) => (
                  <tr key={c.contract_symbol}>
                    <th scope="row">{c.contract_symbol}</th>
                    <td>{c.option_type}</td>
                    <td>{c.strike}</td>
                    <td>{c.expiry}</td>
                    <td>{c.bid === null ? "—" : c.bid}</td>
                    <td>{c.ask === null ? "—" : c.ask}</td>
                    <td>{c.last === null ? "—" : c.last}</td>
                    <td>{c.volume}</td>
                    <td>{c.open_interest}</td>
                    <td>{c.implied_volatility === null
                      ? "—" : `${(c.implied_volatility * 100).toFixed(0)}%`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </details>
  );
}
