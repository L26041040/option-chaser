"""#362：單一正式網址。

`vercel.json` 的 `redirects` 是這個行為的唯一實作（零程式碼），所以測試守的是
設定檔的形狀——任何一條被改壞都會讓 Normal User 在不同網址變成不同的人，或讓舊
網址上的人遺失劇本：

- 只重導兩個已確認的 Production 別名網址，且正式網址本身、Preview、deployment
  專屬網址都不受影響（host 完全比對）。
- `/api/*` 一律不重導（`/api/health` 部署驗證在用；從別名網址載入的舊 SPA 打 API
  也必須維持同源）。
- 舊網址上**已經有身分 cookie** 的瀏覽器不重導（`missing` cookie）——它的劇本掛
  在那個 origin 的身分上，轉走就是孤兒。
"""
import json
import pathlib
import re

from api_app import main as main_module

ROOT = pathlib.Path(__file__).resolve().parent.parent
CANONICAL = "option-chaser.vercel.app"
ALIASES = {
    "option-chaser-ofriedoriceo-5352s-projects.vercel.app",
    "option-chaser-git-master-ofriedoriceo-5352s-projects.vercel.app",
}


def _redirects() -> list[dict]:
    return json.loads((ROOT / "vercel.json").read_text())["redirects"]


def test_exactly_the_two_confirmed_aliases_redirect_to_the_canonical_host():
    hosts = set()
    for rule in _redirects():
        host_conditions = [c for c in rule["has"] if c["type"] == "host"]
        assert len(host_conditions) == 1, "每條規則只綁一個完全比對的 host"
        hosts.add(host_conditions[0]["value"])
        assert rule["destination"] == f"https://{CANONICAL}/$1"
    assert hosts == ALIASES
    assert CANONICAL not in hosts


def test_api_paths_are_never_redirected():
    for rule in _redirects():
        pattern = re.compile("^" + rule["source"] + "$")
        assert pattern.match("/")
        assert pattern.match("/index.html")
        assert pattern.match("/assets/app.js")
        assert not pattern.match("/api/health")
        assert not pattern.match("/api/scenarios")


def test_browsers_that_already_hold_an_identity_cookie_stay_on_their_host():
    for rule in _redirects():
        assert {"type": "cookie", "key": main_module._OWNER_COOKIE_NAME} in rule["missing"]


def test_redirect_is_temporary_so_it_can_be_rolled_back():
    for rule in _redirects():
        assert rule.get("statusCode") == 307
        assert "permanent" not in rule
