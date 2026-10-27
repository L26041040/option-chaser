"""#362：單一正式網址（CANONICAL-REDIRECT-FIX-001）。

別名網址 → 正式網址的轉址由前端啟動閘門（`src/canonicalHost.ts`，行為測試在
`src/canonicalHost.test.ts` 與 `scripts/canonical_redirect_verify.mjs`）決定，
因為只有前端看得到 IndexedDB／localStorage 裡的憑證。這個檔案守住兩件事：

- `vercel.json` 不得再有 `redirects`：邊緣只看 cookie，cookie 掉了、本機憑證還在
  的舊使用者會在前端有機會恢復身分之前被導走，劇本變孤兒。
- 前端的別名清單與 vercel.json／spec 記載的兩個已確認 Production 別名一致，
  而且正式網址不在別名清單裡（否則會無限轉址）。
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = (ROOT / "src" / "canonicalHost.ts").read_text(encoding="utf-8")

EXPECTED_ALIASES = {
    "option-chaser-ofriedoriceo-5352s-projects.vercel.app",
    "option-chaser-git-master-ofriedoriceo-5352s-projects.vercel.app",
}


def test_vercel_json_has_no_edge_redirects():
    config = json.loads((ROOT / "vercel.json").read_text())
    assert "redirects" not in config


def test_frontend_alias_list_is_exactly_the_two_confirmed_hosts():
    block = re.search(r"ALIAS_HOSTS[^=]*=\s*\[(.*?)\]", SRC, re.S).group(1)
    assert set(re.findall(r'"([^"]+)"', block)) == EXPECTED_ALIASES


def test_canonical_origin_is_not_an_alias():
    origin = re.search(r'CANONICAL_ORIGIN\s*=\s*"https://([^"]+)"', SRC).group(1)
    assert origin == "option-chaser.vercel.app"
    assert origin not in EXPECTED_ALIASES
