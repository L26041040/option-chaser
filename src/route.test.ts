import { describe, expect, it } from "vitest";

import { detailHash, isTrashHash, scenarioIdFromHash, trashHash } from "./route";

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

describe("垃圾桶畫面路由（TR6／#91）", () => {
  it("垃圾桶的 hash 認得出自己", () => {
    expect(isTrashHash(trashHash())).toBe(true);
  });

  it("劇本庫與詳細頁的 hash 都不是垃圾桶", () => {
    expect(isTrashHash("")).toBe(false);
    expect(isTrashHash("#/")).toBe(false);
    expect(isTrashHash(detailHash("abc123"))).toBe(false);
  });

  it("垃圾桶 hash 底下 scenarioIdFromHash 仍是 null（不會被誤判成詳細頁）", () => {
    expect(scenarioIdFromHash(trashHash())).toBeNull();
  });
});
