import { describe, expect, it } from "vitest";

import { detailHash, scenarioIdFromHash } from "./route";

describe("路由", () => {
  it("詳細頁的 hash 認得出自己的劇本", () => {
    expect(scenarioIdFromHash(detailHash("abc123"))).toBe("abc123");
  });

  it("劇本庫是預設畫面", () => {
    expect(scenarioIdFromHash("")).toBeNull();
    expect(scenarioIdFromHash("#/")).toBeNull();
  });

  it("認不得的 hash 回劇本庫，不是停在空白畫面", () => {
    expect(scenarioIdFromHash("#/nope/x")).toBeNull();
  });

  it("id 進出網址都經過編碼，特殊字元不會把路徑切壞", () => {
    const weird = "a/b c";
    expect(detailHash(weird)).not.toContain(" ");
    expect(scenarioIdFromHash(detailHash(weird))).toBe(weird);
  });
});
