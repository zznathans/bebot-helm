#!/bin/ash
# shellcheck shell=dash
EXITCODE=255
while [ "$EXITCODE" -eq 255 ]; do
        /usr/bin/php StartBot.php "$@" &
        PHP_PID=$!
        # Forward SIGTERM to the PHP process and stop restarting.
        trap 'kill "$PHP_PID"; EXITCODE=0' TERM
        wait "$PHP_PID"
        EXITCODE=$?
        trap - TERM
done
exit $EXITCODE
