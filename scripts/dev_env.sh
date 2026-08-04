#!/bin/sh
# 還原工作容器的測試環境（venv ＋ 本地 Postgres）。
#
# 為什麼需要這個：這個容器的檔案系統會不定時倒退回較早的提交，連同
# `.venv` 的套件與 Postgres 的資料目錄一起消失。倒退本身用
# `git fetch origin <branch> && git merge --ff-only origin/<branch>` 救回
# （所有工作都推到 origin 了），但測試環境要自己重建——沒重建的話
# `tests/test_storage_contract.py` 的 Postgres 那一半會**靜默跳過**，
# 全套測試看起來還是綠的，卻少驗了一個實作。
#
# 用法：
#   sh scripts/dev_env.sh
#   OC_TEST_DATABASE_URL="postgresql://postgres@127.0.0.1:55432/octest" \
#     PYTHONPATH=. .venv/bin/python -m pytest
set -e

PGBIN=/usr/lib/postgresql/16/bin
PGDATA=/var/lib/postgresql/ocdata
PGPORT=55432

echo "== Python 套件 =="
uv pip install --python .venv/bin/python -e ".[api,yf]" pytest >/dev/null
.venv/bin/python -c "import fastapi, psycopg, yfinance" && echo "ok"

echo "== Postgres =="
if "$PGBIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" >/dev/null 2>&1; then
  echo "已在跑"
else
  if [ ! -d "$PGDATA" ]; then
    mkdir -p "$PGDATA"
    chown postgres:postgres "$PGDATA"
    chmod 700 "$PGDATA"
    su -s /bin/sh postgres -c "$PGBIN/initdb -D $PGDATA -U postgres --auth=trust" >/dev/null
  fi
  su -s /bin/sh postgres -c "$PGBIN/pg_ctl -D $PGDATA -o '-p $PGPORT -k /tmp' -l /tmp/pg.log start" >/dev/null
  sleep 2
  su -s /bin/sh postgres -c "$PGBIN/createdb -h /tmp -p $PGPORT -U postgres octest" 2>/dev/null || true
fi
"$PGBIN/pg_isready" -h 127.0.0.1 -p "$PGPORT"
