"""Minimal stand-ins for the main_modules registered under bot.core(name).

The real modules touch the database on construction (see
main_modules/access_control.py, settings.py, ...), so tests that only
care about Bot's own dispatch/logging/registry logic register these
instead of the real thing.
"""
from __future__ import annotations


class FakeSettings:
    def __init__(self, values: dict[tuple[str, str], object] | None = None):
        self._values = dict(values or {})

    def get(self, module: str, setting: str):
        return self._values.get((module, setting), False)

    def set(self, module: str, setting: str, value) -> None:
        self._values[(module, setting)] = value


class FakeAccessControl:
    def __init__(self, allow: bool = True, min_rights: int = 0):
        self.allow = allow
        self.min_rights = min_rights
        self.calls: list[tuple] = []

    def check_rights(self, user, command, msg, channel) -> bool:
        self.calls.append((user, command, msg, channel))
        return self.allow

    def get_min_rights(self, command, msg, channel) -> int:
        return self.min_rights


class FakeSecurity:
    def __init__(self, banned: bool = False, access: bool = True):
        self.banned = banned
        self.access = access

    def is_banned(self, player) -> bool:
        return self.banned

    def check_access(self, player, level) -> bool:
        return self.access


class FakeChatQueue:
    def __init__(self, queue_open: bool = True):
        self.queue_open = queue_open
        self.queued: list[tuple] = []

    def check_queue(self) -> bool:
        return self.queue_open

    def into_queue(self, to, msg, kind, priority) -> None:
        self.queued.append((to, msg, kind, priority))


class FakeColors:
    def parse(self, text: str) -> str:
        return text

    def colorize(self, color: str, text: str) -> str:
        return text


class FakePlayer:
    def __init__(self, names: dict[int, str] | None = None, ids: dict[str, int] | None = None):
        self._names = dict(names or {})
        self._ids = dict(ids or {})

    def name(self, uid):
        return self._names.get(uid, str(uid))

    def id(self, name):
        return self._ids.get(name, 0)


class FakeCommandAlias:
    def replace(self, msg: str) -> str:
        return msg


class FakeTimer:
    def __init__(self):
        self.registered: dict[str, object] = {}
        self.checked = False

    def register_callback(self, name, module) -> None:
        self.registered[name] = module

    def unregister_callback(self, name):
        return self.registered.pop(name, None)

    def check_timers(self) -> None:
        self.checked = True


class FakeHelp:
    def show_help(self, to, command):
        return f"help for {command}"


class FakeLogonNotifies:
    def __init__(self):
        self.registered: list[object] = []

    def register(self, module) -> None:
        self.registered.append(module)

    def unregister(self, module) -> None:
        if module in self.registered:
            self.registered.remove(module)


class FakeAOChat:
    def __init__(self, connect_result: bool = True):
        self.connect_result = connect_result
        self.disconnected = False
        self.calls: list[tuple] = []

    async def connect(self, server, port):
        self.calls.append(("connect", server, port))
        return self.connect_result

    async def authenticate(self, username, password):
        self.calls.append(("authenticate", username, password))
        return []

    async def login(self, char):
        self.calls.append(("login", char))
        return True

    def disconnect(self):
        self.disconnected = True


class RecordingModule:
    """Generic fake module used for register_module()/command dispatch tests."""

    def __init__(self, name="module", return_value=None):
        self.name = name
        self.return_value = return_value
        self.calls: list[tuple] = []

    def __getattr__(self, item):
        def _record(*args, **kwargs):
            self.calls.append((item, args, kwargs))
            return self.return_value

        return _record
