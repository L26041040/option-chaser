"""儲存後端的環境變數選擇（V2／#50）。"""
from api_app.storage.factory import database_url, storage_from_env


def test_no_env_falls_back_to_memory_visibly():
    """沒有連線字串＝正式部署上的設定錯誤。退回記憶體是為了不整個掛掉，
    但 `kind` 必須如實說是 memory——`/api/health` 靠它讓「資料不會存活」
    看得見。"""
    assert storage_from_env({}).kind == "memory"


def test_pooled_url_wins_over_direct_one():
    """serverless 每次請求開新連線，該走 Neon 的連線池端點。"""
    env = {"DATABASE_URL": "postgresql://direct/db",
           "POSTGRES_PRISMA_URL": "postgresql://pooled/db"}
    assert database_url(env) == "postgresql://pooled/db"


def test_any_recognised_variable_is_picked_up():
    for name in ("DATABASE_URL", "POSTGRES_URL", "POSTGRES_URL_NON_POOLING"):
        assert database_url({name: "postgresql://x/db"}) == "postgresql://x/db"


def test_empty_string_is_treated_as_unset():
    assert database_url({"DATABASE_URL": ""}) is None
