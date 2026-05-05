#!/bin/ash
# shellcheck shell=dash
errorMessage() {
        echo "$*"
        exit 1
}
EXITCODE=255
while [ "$EXITCODE" -eq 255 ]; do
        trap "" TERM
        # shellcheck disable=SC2086
        /usr/bin/php  StartBot.php "$@"
        EXITCODE=$?
        trap - TERM
done
exit $EXITCODE
