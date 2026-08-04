/**
 * FB4-01（#60）：候選池診斷。
 *
 * 這個元件同時是兩件事——診斷工具，以及「不再無聲誤導」的修正本身。
 * 排名第一的候選看起來永遠很正常，但如果整池只剩它一個，那個名次
 * 沒有意義；使用者必須看得到池子的實際狀態才能判斷。
 *
 * 資料全部由引擎算好（`filter_stages`／`pair_report`／`expiry_counts`），
 * 這裡只做計數加總與呈現，零金融計算。
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import CandidatePool from "./CandidatePool";
import type { AnalysisView } from "./api";

function view(overrides: Partial<{
  stages: { label: string; removed: number }[];
  report: { total: number; passed: number } | null;
  pairs: { total_pairs: number; removed_sanity: number; passed: number } | null;
  counts: [string, number][];
  baseline: string;
}> = {}): AnalysisView {
  return {
    meta: { symbol: "TLT", spot: 82.25, fetched_at: "", source: "cboe",
            target_move: 0 },
    baseline_expiry: overrides.baseline ?? "2028-06-16",
    results: [{
      strategy: "bull-call-spread",
      status: "ok",
      message: "",
      // spread 路徑的 n_qualified ＝ 配對數，刻意與合約數不同，
      // 確保元件不會誤用它當合約數。
      n_qualified: 680,
      filter_report: overrides.report === undefined
        ? { total: 68, passed: 40 }
        : overrides.report,
      filter_stages: overrides.stages ?? [
        { label: "報價異常", removed: 12 },
        { label: "IV 異常", removed: 8 },
        { label: "OI/成交量不足", removed: 3 },
        { label: "Spread 過寬", removed: 5 },
      ],
      pair_report: overrides.pairs === undefined
        ? { total_pairs: 780, removed_sanity: 100, passed: 680 }
        : overrides.pairs,
      expiry_counts: overrides.counts ?? [["2028-06-16", 25], ["2028-09-15", 30]],
    }],
  };
}

describe("候選池診斷", () => {
  it("逐關顯示砍掉幾筆，抓到／通過取引擎的合約層級計數", () => {
    render(<CandidatePool view={view()} />);

    expect(screen.getByText("報價異常")).toBeInTheDocument();
    expect(screen.getByText("IV 異常")).toBeInTheDocument();
    expect(screen.getByText("OI/成交量不足")).toBeInTheDocument();
    expect(screen.getByText("Spread 過寬")).toBeInTheDocument();

    // 每關砍掉的筆數
    expect(screen.getByText("−12")).toBeInTheDocument();
    expect(screen.getByText("−8")).toBeInTheDocument();

    expect(screen.getByText("68 筆")).toBeInTheDocument();
    expect(screen.getByText("40 筆")).toBeInTheDocument();
  });

  it("合約數只認 filter_report，不拿 n_qualified 當合約數", () => {
    // spread 路徑的 n_qualified 是配對數（這裡 680）。若元件誤用它，
    // 「通過品質過濾」就會顯示 680 筆而不是 40 筆。
    render(<CandidatePool view={view()} />);
    expect(screen.queryByText("680 筆")).not.toBeInTheDocument();
  });

  it("引擎沒給合約層級計數時顯示未知，不硬湊數字", () => {
    render(<CandidatePool view={view({ report: null })} />);
    // 抓到／通過兩列都是「—」，加上 baseline 期存在故有效組數正常顯示。
    expect(screen.getAllByText("—")).toHaveLength(2);
  });

  it("顯示配對結果", () => {
    render(<CandidatePool view={view()} />);
    expect(screen.getByText(/780/)).toBeInTheDocument();
    expect(screen.getByText(/680/)).toBeInTheDocument();
  });

  it("顯示 baseline 到期日的有效組數", () => {
    render(<CandidatePool view={view()} />);
    expect(screen.getByText(/25 組/)).toBeInTheDocument();
  });

  it("有效組數充足時不出現警示", () => {
    render(<CandidatePool view={view()} />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("有效組數過少時明確警示，說明排名參考價值有限", () => {
    render(<CandidatePool view={view({ counts: [["2028-06-16", 2]] })} />);

    const warning = screen.getByRole("status");
    expect(warning).toHaveTextContent("僅 2 組");
    expect(warning).toHaveTextContent("參考價值有限");
  });

  it("整池被清空時也警示，而不是靜靜顯示 0", () => {
    render(<CandidatePool view={view({ counts: [["2028-06-16", 0]] })} />);
    expect(screen.getByRole("status")).toHaveTextContent("僅 0 組");
  });

  it("baseline 期不在計數裡時不謊報，顯示為未知", () => {
    render(<CandidatePool view={view({ counts: [["2099-01-01", 30]] })} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("策略未產生結果時只說明狀態，不硬擠出數字", () => {
    const empty: AnalysisView = {
      ...view(),
      results: [{ strategy: "bull-call-spread", status: "empty",
                  message: "目前沒有符合流動性與報價條件的合約。",
                  n_qualified: 0, filter_report: null, filter_stages: [],
                  pair_report: null, expiry_counts: [] }],
    };
    render(<CandidatePool view={empty} />);
    expect(
      screen.getByText("目前沒有符合流動性與報價條件的合約。"),
    ).toBeInTheDocument();
  });
});
