#!/usr/bin/env sh
# 数据库备份：把容器里的 MySQL 全量导出成压缩 SQL，保留最近 7 份。
#
# 用法（在 infra 目录下）：
#   sh backup.sh                 # 备份到 infra/backups/
#   BACKUP_DIR=/data/bak sh backup.sh
#
# 恢复：
#   gunzip -c backups/xuanshu-20261024-0300.sql.gz | \
#     docker compose exec -T mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" xuanshu
#
# 定时：Windows 用任务计划程序调用本脚本；Linux 用 cron（例：0 3 * * *）。

set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP="${KEEP:-7}"

# 从 .env 读取口令，避免把密码写进脚本
if [ -f .env ]; then
  # shellcheck disable=SC1091
  . ./.env
fi

: "${MYSQL_ROOT_PASSWORD:?请先在 infra/.env 里设置 MYSQL_ROOT_PASSWORD}"
: "${MYSQL_DATABASE:=xuanshu}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M)"
OUT="$BACKUP_DIR/${MYSQL_DATABASE}-${STAMP}.sql.gz"

echo "[backup] 导出 ${MYSQL_DATABASE} -> ${OUT}"
docker compose -f "$COMPOSE_FILE" exec -T mysql \
  mysqldump --single-transaction --quick --routines --events \
  -uroot -p"${MYSQL_ROOT_PASSWORD}" "${MYSQL_DATABASE}" | gzip -9 > "$OUT"

echo "[backup] 完成，大小 $(wc -c < "$OUT") 字节"

# 只保留最近 N 份，避免磁盘被备份占满
ls -1t "$BACKUP_DIR"/"${MYSQL_DATABASE}"-*.sql.gz 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r old; do
  echo "[backup] 清理旧备份 ${old}"
  rm -f "$old"
done
