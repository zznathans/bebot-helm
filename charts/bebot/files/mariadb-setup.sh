#!/bin/sh
# Idempotently creates one bot instance's database and user on the chart's MariaDB. Runs as
# an init container on every bot start, so new instances and password changes just work.
set -eu

export MYSQL_PWD="${MARIADB_ROOT_PASSWORD}"

client() {
  mariadb --skip-ssl -h "${MARIADB_HOST}" -uroot "$@"
}

until client -e "SELECT 1" >/dev/null; do
  echo "waiting for ${MARIADB_HOST}"
  sleep 2
done

# String literals need ' and \ doubled, identifiers need ` doubled.
sql_string() {
  printf '%s' "$1" | sed "s/[\\\\']/&&/g"
}
sql_identifier() {
  printf '%s' "$1" | sed 's/`/``/g'
}

database="$(sql_identifier "${MARIADB_DATABASE}")"
user="$(sql_string "${MARIADB_USER}")"
password="$(sql_string "${MARIADB_PASSWORD}")"

client <<SQL
CREATE DATABASE IF NOT EXISTS \`${database}\`;
CREATE USER IF NOT EXISTS '${user}'@'%' IDENTIFIED BY '${password}';
ALTER USER '${user}'@'%' IDENTIFIED BY '${password}';
GRANT ALL PRIVILEGES ON \`${database}\`.* TO '${user}'@'%';
SQL

echo "database ${MARIADB_DATABASE} ready for ${MARIADB_USER}"
