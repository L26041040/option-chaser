"""PB-11（#303，Anonymous Public Beta）：daily email digest——內容組裝
（`build_digest_text()`）與寄送（`send_digest_email()`）刻意分成兩個
函式，前者是離線可測的純函式，後者才是唯一碰網路的地方，比照 PB-13
（#293）`api_app/observability.py` 的 Sentry 接線「未設定即嚴格
no-op」哲學。

**FREE-FIRST（spec §13）**：用 Python 標準庫 `smtplib`／`email`，不
引入任何新的第三方套件或付費服務——任何提供免費 SMTP relay 的信箱
（例如個人 Gmail 帳號＋App Password）皆可設定使用，選擇權留給 Owner，
程式碼本身不綁死特定 vendor。

**內容邊界（票面 §10 安全考量）**：`DigestSnapshot` 只含聚合數字與
alert 訊息，**沒有任何欄位可以承載個別 owner_id、劇本內容、或第三方
credential token**——PB-10 的跨 owner 檢視是獨立、需要另外解鎖的
Super User 端點，這裡的每日摘要信刻意不重複那個能力。
"""
from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.mime.text import MIMEText

from .ops_alerts import AlertCondition


@dataclass(frozen=True)
class DigestSnapshot:
    """一天份的聚合快照——由 `main.py` 組裝（它才碰得到 `Storage`／
    `chain_backoff`），本模組只負責格式化與寄送，不查詢任何資料來源。
    """
    date: str
    owners_active: int
    owners_abandoned: int
    owners_eligible_for_hard_delete: int
    owners_protected: int
    owners_total: int
    scenarios_total: int
    scenarios_average_per_owner: float
    cleanup_owners_deleted_today: int
    cleanup_rows_deleted_today: int
    alerts: tuple[AlertCondition, ...]


def build_digest_text(snapshot: DigestSnapshot) -> str:
    """純文字信件內文——**五類指標分開陳列**（票面 §7 implementation
    constraint：product usage／system health／vendor usage-quota／
    storage growth／security-abuse signals 不得混成一個總分）。每一段
    的存在理由都寫在小標題旁——「看了會做什麼決定」說不出來的欄位，
    本函式結構上就沒有地方可以塞。"""
    lines: list[str] = []
    lines.append(f"Option Chaser 每日摘要 — {snapshot.date}")
    lines.append("")

    triggered = [a for a in snapshot.alerts if a.triggered]
    if triggered:
        lines.append("⚠ 需要留意")
        for a in triggered:
            lines.append(f"  - {a.message}")
        lines.append("")

    lines.append("使用量（product usage）——決定要不要提高／降低額度")
    lines.append(f"  活躍 owner：{snapshot.owners_active}")
    lines.append(f"  尚在緩衝期（abandoned）：{snapshot.owners_abandoned}")
    lines.append(f"  等待下次清理：{snapshot.owners_eligible_for_hard_delete}")
    lines.append(f"  受保護（不受清理影響）：{snapshot.owners_protected}")
    lines.append(f"  owner 總數：{snapshot.owners_total}")
    lines.append(f"  劇本總數：{snapshot.scenarios_total}"
                f"（平均每 owner {snapshot.scenarios_average_per_owner:.1f} 個）")
    lines.append("")

    lines.append("清理排程（storage growth）——決定 30+7 天門檻是否要調整")
    lines.append(f"  今天刪除的 owner 數：{snapshot.cleanup_owners_deleted_today}")
    lines.append(f"  今天刪除的資料列數：{snapshot.cleanup_rows_deleted_today}")
    lines.append("")

    lines.append("系統健康 ／ vendor 用量 ／ 異常訊號（system health ＋ "
                 "vendor usage-quota ＋ security-abuse）——決定要不要介入")
    for a in snapshot.alerts:
        mark = "⚠" if a.triggered else "✓"
        lines.append(f"  {mark} {a.message}")

    return "\n".join(lines)


def send_digest_email(
    text: str,
    *,
    smtp_host: str | None,
    smtp_port: int | None,
    smtp_user: str | None,
    smtp_password: str | None,
    mail_from: str | None,
    mail_to: str | None,
    subject: str,
) -> bool:
    """任一必要設定缺席即嚴格 no-op、回傳 `False`——比照
    `api_app/observability.py` 的 Sentry 接線同一套「未設定就什麼都
    不做」哲學，讓 `build_digest_text()` 在完全沒有 SMTP 設定的環境
    （例如本地開發、CI）也能被單獨測試，不需要一把真的信箱密碼。

    回傳 `True` 代表確實嘗試送出（`smtplib` 若真的連線/驗證失敗會讓
    例外往上炸，呼叫端決定要不要吞掉——這裡不吞，寄信失敗不該被
    靜默掩蓋成「寄了」）。"""
    if not all([smtp_host, smtp_port, smtp_user, smtp_password,
               mail_from, mail_to]):
        return False

    msg = MIMEText(text, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = mail_to

    with smtplib.SMTP(smtp_host, int(smtp_port), timeout=15) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(mail_from, [mail_to], msg.as_string())
    return True
