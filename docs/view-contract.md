# Option Chaser — Result View 契約（schema_version 2）

`store.serialize_result(result, scenario_id, capital) -> dict` 的輸出是本專案唯一的 GUI 資料介面；未來任何前端（含非 Streamlit 實作）只需讀 `results/<id>/<ts>.json`（此 dict 的落盤形式）＋ `workspace` 目錄下的 scenario/groups/events 檔，即可重建完整 UI，無需呼叫 `option_chaser.service` 或任何估值函數。

## 頂層鍵

`schema_version`(int, 現為2) / `engine_version`(str) / `analyzed_at`(ISO8601) / `scenario_id` / `params`(dict) / `snapshot_ref`(`{path,fetched_at,source,spot}`) / `meta`(`{symbol,spot,fetched_at,source,snapshot_path,target_move}`) / `capital_assumed`(float|null) / `data_quality`(`{fetched_at,all_quotes_filtered}`) / `results`(list) / `expiry_groups`(list) / `hidden_expiries`(list) / `default_selection`(`[expiry,candidate_key]`|null) / `comparison`(list) / `best_strategy`(str|null) / `today`(ISO date)

## candidate dict（`results[].candidates[]` / `expiry_best[]` / `expiry_groups[].rows[].candidate`）

`candidate_key` `strategy` `legs`(list of `{contract_symbol,option_type,strike,expiry,bid,ask,iv,volume,open_interest}`；單腿長度1、Spread長度2＝[long,short]) `mid_cost` `natural_cost` `baseline_pnl` `baseline_return` `natural_return` `scenario_vector`(`{entries,worst_code,worst_return}`) `completion_curve` `completion_prices` `completion_threshold` `breakeven_at_target` `retention` `friction` `friction_amount` `buffer_days` `quote_warning` `theta_day_rate` `vega_per_pt` `decay_30d_return` `net_delta` `breakeven` `max_profit`(nullable) `effective_leverage` `matrix`(`{prices,dates,cells}`) `capital_per_contract` `max_loss_per_contract` `pct_of_capital`(nullable) `days_to_target` `days_to_expiry` **`natural_per_contract`（v2新）** **`max_profit_per_contract`（v2新，nullable）** **`cap_price`（v2新，nullable；Spread=賣腿strike，單腿=null）**

## 消費者

`webapp/render.py`（heatmap／比較表／進階區）、`webapp/components.py`（卡片）——皆為純函數，僅格式化與展示層比較，零金融公式。

（此文件與 `tests/test_store_serialize_v2.py` 互為印證；欄位變動須同步兩者。）
