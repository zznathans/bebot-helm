#!/usr/bin/env python3
"""Entry point for the Python BeBot port.

Replaces StartBot.php + Main.php's bootstrap and main loop. Usage:

    python run.py            # loads Conf/bot_conf.py
    python run.py mybot       # loads Conf/mybot_bot_conf.py

No auto-restart wrapper (StartBot.php's `while (true) { system(...) }`
loop) is provided yet -- run this under systemd/supervisord/pm2/etc. for
that, or wrap it in a shell loop.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from bebot.bot import Bot
from bebot.conf import load_bot_config
from bebot.main_modules import load_all

CONF_DIR = os.path.join(os.path.dirname(__file__), "Conf")


async def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else None
    config = load_bot_config(CONF_DIR, name)

    bot = Bot(config)
    load_all(bot)

    await bot.connect()

    while True:
        packet = await bot.aoc.wait_for_packet()
        if packet == "disconnected":
            await bot.reconnect()
        bot.cron()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
