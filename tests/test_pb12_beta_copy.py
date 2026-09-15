"""PB-12（#302，Anonymous Public Beta）：首頁 Beta 說明／隱私頁的天數
文案，與後端 `ANONYMOUS_ABANDONED_AFTER_DAYS`／`ANONYMOUS_GRACE_
PERIOD_DAYS` 實際預設值不得漂移。

票面 §7 明文：「若寫死在文案裡，需有測試或註解確保兩者不會漂移」——
前端沒有任何 API 呼叫可以即時查詢這兩個值（本票 Dependencies 只有
PB-02／PB-04，未要求新增這樣的端點），因此改用這條後端測試直接讀
`src/BetaNotice.tsx` 裡的具名常數字面值，與後端常數逐一比對。任一邊
改了另一邊沒跟著改，這條測試會紅——不是只靠 docstring 口頭保證。

刻意不解析 TypeScript AST（過度工程）：`BetaNotice.tsx` 的兩個常數
宣告是簡單的字面量賦值，用正規表示式直接抓數字即可，抓不到就讓測試
本身失敗（而不是靜默跳過），確保這條測試永遠是「真的比對過」。
"""
import re
from pathlib import Path

from api_app.main import ANONYMOUS_ABANDONED_AFTER_DAYS, ANONYMOUS_GRACE_PERIOD_DAYS

_BETA_NOTICE_TSX = (
    Path(__file__).resolve().parent.parent / "src" / "BetaNotice.tsx")


def _frontend_constant(name: str) -> int:
    text = _BETA_NOTICE_TSX.read_text(encoding="utf-8")
    match = re.search(rf"export const {name} = (\d+);", text)
    assert match is not None, (
        f"找不到 `export const {name} = <數字>;`——`src/BetaNotice.tsx` "
        "的常數宣告格式可能改變了，這條測試需要跟著更新，不是被跳過。")
    return int(match.group(1))


def test_the_days_hardcoded_in_the_frontend_copy_match_the_backend_defaults():
    assert _frontend_constant("ANONYMOUS_ABANDONED_AFTER_DAYS") == (
        ANONYMOUS_ABANDONED_AFTER_DAYS)
    assert _frontend_constant("ANONYMOUS_GRACE_PERIOD_DAYS") == (
        ANONYMOUS_GRACE_PERIOD_DAYS)


def test_the_backend_defaults_are_still_thirty_and_seven():
    """這兩個數字本身（30／7）也是需求方裁示的一部分（spec #291 OD-4）
    ——若哪天真的要改，這條測試會提醒改動的人：前端文案（`src/
    BetaNotice.tsx`）與這裡的隱私頁六項內容都要跟著更新，不是只改
    後端常數就結束。"""
    assert ANONYMOUS_ABANDONED_AFTER_DAYS == 30
    assert ANONYMOUS_GRACE_PERIOD_DAYS == 7
