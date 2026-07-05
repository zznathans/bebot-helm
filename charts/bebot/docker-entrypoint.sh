#!/bin/sh
# shellcheck shell=dash
/usr/local/bin/python /BeBot/run.py "$@" &
BOT_PID=$!
trap 'kill "$BOT_PID"' TERM
wait "$BOT_PID"
exit $?
