#!/bin/ash
# shellcheck shell=dash
/usr/bin/php StartBot.php "$@" &
PHP_PID=$!
trap 'kill "$PHP_PID"' TERM
wait "$PHP_PID"
exit $?
