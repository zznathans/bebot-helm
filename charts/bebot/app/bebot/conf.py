"""Bot configuration loading.

Replaces Sources/Conf.php + the Bot::factory() config half of Sources/Bot.php.

Instead of executable PHP config files (Conf/<Name>.Bot.conf), the Python
port loads a plain Python module from the Conf/ directory, e.g.
Conf/bot_conf.py (see Conf/bot_conf.example.py for the template). No
interactive setup wizard is provided (yet) -- copy the example and edit it.
"""
from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass, field


SERVER_LIST = {
    # AO only (AoC is out of scope for this port).
    "Testlive": {"server": "chat.d1.funcom.com", "port": 7105},
    "Rubi-Ka": {"server": "chat.d1.funcom.com", "port": 7105},
    "Rubi-Ka-2019": {"server": "chat.d1.funcom.com", "port": 7105},
}

_DIMENSION_ALIASES = {
    "0": "Testlive",
    "5": "Rubi-Ka",
    "6": "Rubi-Ka-2019",
}


def _load_module(path: str):
    spec = importlib.util.spec_from_file_location(os.path.basename(path), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@dataclass
class BotConfig:
    ao_username: str
    ao_password: str
    bot_name: str
    dimension: str
    guild: str = ""
    owner: str = ""
    super_admin: dict[str, bool] = field(default_factory=dict)
    guildbot: bool = False
    guild_id: int = 0
    log: str = "chat"
    log_path: str = "./log"
    log_timestamp: str = "none"
    log_format: str = "json"
    command_prefix: str = "!"
    cron_delay: int = 30
    tell_delay: int = 2222
    reconnect_time: int = 60
    max_blobsize: int = 12000
    accessallbots: bool = False
    other_bots: dict[str, bool] = field(default_factory=dict)

    # MySQL
    db_name: str = ""
    db_user: str = ""
    db_password: str = ""
    db_server: str = "localhost"
    table_prefix: str | None = None
    master_tablename: str | None = None
    no_underscore: bool = False

    @property
    def server(self) -> str:
        return SERVER_LIST[self.resolved_dimension]["server"]

    @property
    def port(self) -> int:
        return SERVER_LIST[self.resolved_dimension]["port"]

    @property
    def resolved_dimension(self) -> str:
        return _DIMENSION_ALIASES.get(str(self.dimension), str(self.dimension))


def load_bot_config(conf_dir: str, name: str | None = None) -> BotConfig:
    """Load Conf/<name>_bot_conf.py (or Conf/bot_conf.py if name is None)."""
    filename = f"{name.lower()}_bot_conf.py" if name else "bot_conf.py"
    path = os.path.join(conf_dir, filename)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"Could not find bot config at {path}. Copy Conf/bot_conf.example.py "
            "and fill it in."
        )
    mod = _load_module(path)

    def get(attr, default=None):
        return getattr(mod, attr, default)

    ao_password = get("ao_password", "")
    if not ao_password:
        pw_path = os.path.join(conf_dir, "pw")
        if os.path.isfile(pw_path):
            with open(pw_path) as fh:
                ao_password = fh.read().strip()

    return BotConfig(
        ao_username=get("ao_username"),
        ao_password=ao_password,
        bot_name=get("bot_name"),
        dimension=str(get("dimension")),
        guild=get("guild", ""),
        owner=get("owner", ""),
        super_admin=get("super_admin", {}),
        guildbot=bool(get("guildbot", False)),
        guild_id=get("guild_id", 0),
        log=get("log", "chat"),
        log_path=get("log_path", "./log"),
        log_timestamp=get("log_timestamp", "none"),
        log_format=get("log_format", "json"),
        command_prefix=get("command_prefix", "!"),
        cron_delay=get("cron_delay", 30),
        tell_delay=get("tell_delay", 2222),
        reconnect_time=get("reconnect_time", 60),
        max_blobsize=get("max_blobsize", 12000),
        accessallbots=bool(get("accessallbots", False)),
        other_bots=get("other_bots", {}),
        db_name=get("db_name", ""),
        db_user=get("db_user", ""),
        db_password=get("db_password", ""),
        db_server=get("db_server", "localhost"),
        table_prefix=get("table_prefix"),
        master_tablename=get("master_tablename"),
        no_underscore=bool(get("no_underscore", False)),
    )
