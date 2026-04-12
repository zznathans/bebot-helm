#!/bin/ash
# shellcheck shell=dash
errorMessage() {
        echo "$*"
        exit 1
}
EXITCODE=255
git pull
ip a
sleep 5
while [ "$EXITCODE" -eq 255 ]; do
        trap "" TERM
        # shellcheck disable=SC2086
        /usr/bin/php  StartBot.php "$@"
        EXITCODE=$?
        trap - TERM
done
exit $EXITCODE