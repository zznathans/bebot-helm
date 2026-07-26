#!/bin/ash
# shellcheck shell=dash
/usr/bin/php -d error_reporting="E_ALL & ~E_DEPRECATED" StartBot.php "$@" &
PHP_PID=$!
trap 'kill "$PHP_PID"' TERM
wait "$PHP_PID"
exit $?
