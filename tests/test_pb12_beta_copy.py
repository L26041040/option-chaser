"""PB-12（#302，Anonymous Public Beta）：首頁 Beta 說明／隱私頁的天數
文案，與後端 `ANONYMOUS_RETENTION_DAYS`／`ANONYMOUS_GRACE_
PERIOD_DAYS` 實際預設值不得漂移。

票面 §7 明文：「若寫死在文案裡，需有測試或註解確保兩者不會漂移」——
前端沒有任何 API 呼叫可以即時查詢這兩個值（本票 Dependencies 只有
PB-02／PB-04，未要求新增這樣的端點），因此改用這條後端測試直接讀
前端具名常數字面值，與後端常數逐一比對。任一邊改了另一邊沒跟著改，
這條測試會紅——不是只靠 docstring 口頭保證。

刻意不解析 TypeScript AST（過度工程）：這兩個常數宣告是簡單的字面量
賦值，用正規表示式直接抓數字即可，抓不到就讓測試本身失敗（而不是靜默
跳過），確保這條測試永遠是「真的比對過」。

SW-10（#340，Owner 真機驗收）跟進：常數原本宣告在 `src/BetaNotice.tsx`
——Owner 裁示首頁不再常駐這段說明，整段搬進設定頁的
`src/DisclaimerSection.tsx`，常數本身（連同這條比對測試）原封不動
一起搬過去，不是重新發明一份。
"""
import re
from pathlib import Path

from api_app.main import ANONYMOUS_GRACE_PERIOD_DAYS, ANONYMOUS_RETENTION_DAYS

_DISCLAIMER_SECTION_TSX = (
    Path(__file__).resolve().parent.parent / "src" / "DisclaimerSection.tsx")


def _frontend_constant(name: str) -> int:
    text = _DISCLAIMER_SECTION_TSX.read_text(encoding="utf-8")
    match = re.search(rf"export const {name} = (\d+);", text)
    assert match is not None, (
        f"找不到 `export const {name} = <數字>;`——`src/DisclaimerSection."
        "tsx` 的常數宣告格式可能改變了，這條測試需要跟著更新，不是被跳過。")
    return int(match.group(1))


def test_the_days_hardcoded_in_the_frontend_copy_match_the_backend_defaults():
    assert _frontend_constant("ANONYMOUS_RETENTION_DAYS") == (
        ANONYMOUS_RETENTION_DAYS)
    assert _frontend_constant("ANONYMOUS_GRACE_PERIOD_DAYS") == (
        ANONYMOUS_GRACE_PERIOD_DAYS)


def test_the_backend_defaults_are_one_eighty_and_seven():
    """這兩個數字本身（180／7）也是需求方裁示的一部分（SECURITY-FIX-01，
    取代 spec #291 OD-4 的 30／7）——若哪天真的要改，這條測試會提醒改動
    的人：前端文案（`src/DisclaimerSection.tsx`）與隱私頁內容都要跟著
    更新，不是只改後端常數就結束。"""
    assert ANONYMOUS_RETENTION_DAYS == 180
    assert ANONYMOUS_GRACE_PERIOD_DAYS == 7
