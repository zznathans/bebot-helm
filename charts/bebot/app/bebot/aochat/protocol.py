"""AO chat server protocol client (Anarchy Online only).

Ported from Sources/AoChat.php. Uses asyncio streams instead of PHP's
blocking `socket_*` calls. The Diffie-Hellman key exchange and the custom
block cipher used for the login key are reimplemented with Python's
arbitrary-precision integers, which removes the need for PHP's bcmath
string-hex gymnastics and 32-bit-overflow workarounds entirely.

AoC (Age of Conan) support, the sfEvent dispatcher, and buddy/lookup
"wait_for_certain_packet"-style blocking helpers are intentionally not
ported -- out of scope for this pass. Player-name/id resolution instead
calls straight into `bot.core("player")` (the "direct call" pattern the
original code already used alongside its now-dropped event dispatcher).
"""
from __future__ import annotations

import asyncio
import os
import struct
import time

from . import constants as C
from .extmsg import AOExtMsg
from .packet import AOChatPacket

DEFAULT_SERVER = "chat.d1.funcom.com"
DEFAULT_PORT = 7105

_DH_Y = int(
    "9c32cc23d559ca90fc31be72df817d0e124769e809f936bc14360ff4bed758f260a0d596584eacbbc2"
    "b88bdd410416163e11dbf62173393fbc0c6fefb2d855f1a03dec8e9f105bbad91b3437d8eb73fe2f441"
    "59597aa4053cf788d2f9d7012fb8d7c4ce3876f7d6cd5d0c31754f4cd96166708641958de54a6def565"
    "7b9f2e92",
    16,
)
_DH_N = int(
    "eca2e8c85d863dcdc26a429a71a9815ad052f6139669dd659f98ae159d313d13c6bf2838e10a69b647"
    "8b64a24bd054ba8248e8fa778703b418408249440b2c1edd28853e240d8a7e49540b76d120d3b1ad28"
    "78b1b99490eb4a2a5e84caa8a91cecbdb1aa7c816e8be343246f80c637abc653b893fd91686cf8d32d"
    "6cfe5f2a6f",
    16,
)
_DH_G = 5

_MASK32 = 0xFFFFFFFF

# French/German/Spanish/Polish accented letters get folded to ASCII, same
# table as get_packet()'s $searches/$replaces in the PHP source.
_ACCENT_MAP = str.maketrans({
    "À": "A", "Â": "A", "Ç": "C", "É": "E", "È": "E", "Ê": "E", "Ë": "E", "Î": "I", "Ï": "I",
    "Ô": "O", "Ù": "U", "Û": "U", "Ÿ": "Y",
    "à": "a", "â": "a", "ç": "c", "é": "e", "è": "e", "ê": "e", "ë": "e", "î": "i", "ï": "i",
    "ô": "o", "ù": "u", "û": "u", "ÿ": "y",
    "Œ": "Oe", "Æ": "Ae", "œ": "oe", "æ": "ae",
    "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ẞ": "SS",
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Á": "A", "Í": "I", "Ó": "O", "Ú": "U", "Ñ": "N",
    "á": "a", "í": "i", "ó": "o", "ú": "u", "ñ": "n",
    "Ą": "A", "Ć": "C", "Ę": "E", "Ł": "L", "Ń": "N", "Ś": "S", "Ź": "Z", "Ż": "Z",
    "ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n", "ś": "s", "ź": "z", "ż": "Z",
})


def _fold_accents(text: str) -> str:
    return text.translate(_ACCENT_MAP)


class AOChat:
    def __init__(self, bot):
        self.bot = bot
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.state = "connect"
        self.char: dict | None = None
        self.chars: list[dict] = []
        self.username: str | None = None
        self.serverseed: int | None = None
        self.last_packet = 0.0
        self.last_ping = 0.0
        self.gid: dict = {}
        self.grp: dict = {}
        self.buddies: dict = {}

    def disconnect(self) -> None:
        if self.writer is not None:
            self.writer.close()
        self.reader = None
        self.writer = None
        self.serverseed = None
        self.char = None
        self.chars = []
        self.last_packet = 0.0
        self.last_ping = 0.0
        self.state = "connect"
        self.gid = {}
        self.grp = {}
        self.buddies = {}

    # -- connect / login --------------------------------------------------
    async def connect(self, server: str = DEFAULT_SERVER, port: int = DEFAULT_PORT) -> bool:
        if self.state != "connect":
            raise RuntimeError("AOChat: not expecting connect.")
        try:
            self.reader, self.writer = await asyncio.open_connection(server, port)
        except OSError as exc:
            self.bot.log("CONN", "ERROR", f"Could not connect to {server}:{port}: {exc}")
            self.disconnect()
            return False
        self.state = "auth"
        self.bot.log("LOGIN", "NOTICE", "AOChat waiting for AO login seed ...")
        packet = await self.get_packet()
        if not isinstance(packet, AOChatPacket) or packet.type != C.AOCP_LOGIN_SEED:
            self.bot.log("CONN", "ERROR", "Received invalid greeting packet from AO chat server.")
            self.disconnect()
            return False
        return True

    async def authenticate(self, username: str, password: str) -> list[dict]:
        if self.state != "auth":
            raise RuntimeError("AOChat: not expecting authentication.")
        key = self.generate_login_key(self.serverseed, username, password)
        pak = AOChatPacket("out", C.AOCP_LOGIN_REQUEST, [0, username, key])
        await self.send_packet(pak)
        packet = await self.get_packet()
        if packet == "disconnected" or packet.type != C.AOCP_LOGIN_CHARLIST:
            raise RuntimeError(f"AOChat expecting character list, received type {getattr(packet, 'type', packet)}")
        ids, names, levels, online = packet.args
        self.chars = [
            {
                "id": ids[i],
                "name": names[i].decode("latin-1").capitalize(),
                "level": levels[i],
                "online": online[i],
            }
            for i in range(len(ids))
        ]
        self.username = username
        self.state = "login"
        return self.chars

    async def login(self, char) -> bool:
        if self.state != "login":
            raise RuntimeError("AOChat: not expecting login.")
        if isinstance(char, str):
            char = char.capitalize()
            match = next((c for c in self.chars if c["name"] == char), None)
        elif isinstance(char, int):
            match = next((c for c in self.chars if c["id"] == char), None)
        else:
            match = char
        if not match:
            raise RuntimeError("AOChat: no valid character to login.")

        pq = AOChatPacket("out", C.AOCP_LOGIN_SELECT, match["id"])
        await self.send_packet(pq)
        pr = await self.get_packet()
        if pr == "disconnected" or pr.type != C.AOCP_LOGIN_OK:
            return False
        self.char = match
        self.state = "ok"
        return True

    # -- packet I/O ---------------------------------------------------------
    async def wait_for_packet(self, timeout: float = 1.0):
        try:
            return await asyncio.wait_for(self.get_packet(), timeout)
        except asyncio.TimeoutError:
            now = time.time()
            if now - self.last_packet > 60 and now - self.last_ping > 60:
                await self.send_ping()
            return None

    async def _read_exact(self, length: int) -> bytes:
        try:
            return await self.reader.readexactly(length)
        except (asyncio.IncompleteReadError, ConnectionError):
            return b""

    async def get_packet(self):
        head = await self._read_exact(4)
        if len(head) != 4:
            return "disconnected"
        packet_type, length = struct.unpack(">HH", head)
        data = await self._read_exact(length)
        packet = AOChatPacket("in", packet_type, data)
        self.bot.cron()

        if packet_type == C.AOCP_LOGIN_SEED:
            self.serverseed = packet.args[0]
        elif packet_type == C.AOCP_LOGIN_OK:
            self.bot.log("LOGIN", "RESULT", "OK")
        elif packet_type == C.AOCP_GROUP_ANNOUNCE:
            gid, name, status, _ = packet.args
            name = name.decode("latin-1")
            self.grp[gid] = status
            self.gid[gid] = name
            self.gid[name.lower()] = gid
            self.bot.inc_gannounce([gid, name, status])
        elif packet_type == C.AOCP_PRIVGRP_INVITE:
            (gid,) = packet.args
            name = self.bot.core("player").name(gid)
            self.gid[gid] = name
            self.gid[str(name).lower()] = gid
            self.bot.inc_pginvite([gid])
        elif packet_type in (C.AOCP_PRIVGRP_KICK, C.AOCP_PRIVGRP_KICKALL):
            (gid,) = packet.args
            name = self.bot.core("player").name(gid)
            self.gid.pop(gid, None)
            self.gid.pop(str(name).lower(), None)
        elif packet_type == C.AOCP_CLIENT_NAME:
            uid, name = packet.args
            self.bot.core("player").add(uid, name.decode("latin-1").capitalize())
        elif packet_type == C.AOCP_CLIENT_LOOKUP:
            uid, name = packet.args
            if 4294967294 < uid < 4294967296:
                uid = -1
            self.bot.core("player").add(uid, name.decode("latin-1").capitalize())
        elif packet_type == C.AOCP_BUDDY_LOGONOFF:
            bid, bonline, btype = packet.args
            self.buddies[bid] = (C.AOC_BUDDY_ONLINE if bonline else 0) | (C.AOC_BUDDY_KNOWN if btype else 0)
        elif packet_type == C.AOCP_BUDDY_REMOVE:
            self.buddies.pop(packet.args[0], None)
        elif packet_type == C.AOCP_PRIVGRP_CLIJOIN:
            self.bot.inc_pgjoin(packet.args)
        elif packet_type == C.AOCP_PRIVGRP_CLIPART:
            self.bot.inc_pgleave(packet.args)
        elif packet_type == C.AOCP_MSG_PRIVATE:
            uid, message, _blob = packet.args
            message = _fold_accents(message.decode("latin-1"))
            self.bot.inc_tell([uid, message])
        elif packet_type == C.AOCP_PRIVGRP_MESSAGE:
            gid, uid, message, _blob = packet.args
            message = _fold_accents(message.decode("latin-1"))
            self.bot.inc_pgmsg([gid, uid, message])
        elif packet_type == C.AOCP_GROUP_MESSAGE:
            gid, uid, message, _blob = packet.args
            message = _fold_accents(message.decode("latin-1"))
            if uid == 0 and message.startswith("~&"):
                em = AOExtMsg(message)
                if em.type != "AOEM_UNKNOWN":
                    message = em.text
            self.bot.inc_gmsg([gid, uid, message])
        elif packet_type in (C.AOCP_CHAT_NOTICE, C.AOCP_LOGIN_CHARLIST, C.AOCP_PING,
                             C.AOCP_MSG_VICINITYA, C.AOCP_MSG_SYSTEM, C.AOCP_LOGIN_ERROR):
            pass
        else:
            self.bot.log("MAIN", "TYPE", f"Unhandled packet of type {packet_type}. Args: {packet.args!r}")

        self.last_packet = time.time()
        return packet

    async def send_packet(self, packet: AOChatPacket) -> bool:
        data = struct.pack(">HH", packet.type, len(packet.data)) + packet.data
        if self.writer is None:
            return False
        self.writer.write(data)
        await self.writer.drain()
        return True

    async def send_ping(self) -> bool:
        self.last_ping = time.time()
        return await self.send_packet(AOChatPacket("out", C.AOCP_PING, "AoChat.py"))

    # -- messaging -----------------------------------------------------------
    async def send_tell(self, user, msg: str, blob: str = "\0") -> bool:
        uid = user if isinstance(user, int) else self.bot.core("player").id(user)
        if not isinstance(uid, int):
            return False
        return await self.send_packet(AOChatPacket("out", C.AOCP_MSG_PRIVATE, [uid, msg, blob]))

    async def send_group(self, group, msg: str, blob: str = "\0") -> bool:
        gid = self.get_gid(group)
        if gid is False:
            return False
        return await self.send_packet(AOChatPacket("out", C.AOCP_GROUP_MESSAGE, [gid, msg, blob]))

    async def send_privgroup(self, group, msg: str, blob: str = "\0") -> bool:
        gid = group if isinstance(group, int) else self.bot.core("player").id(group)
        if not isinstance(gid, int):
            return False
        return await self.send_packet(AOChatPacket("out", C.AOCP_PRIVGRP_MESSAGE, [gid, msg, blob]))

    async def privategroup_join(self, group) -> bool:
        return await self.send_packet(AOChatPacket("out", C.AOCP_PRIVGRP_JOIN, self.get_gid(group)))

    async def privategroup_leave(self, group) -> bool:
        return await self.send_packet(AOChatPacket("out", C.AOCP_PRIVGRP_PART, self.get_gid(group)))

    async def privategroup_invite(self, user) -> bool:
        uid = self.bot.core("player").id(user)
        if not isinstance(uid, int):
            return False
        return await self.send_packet(AOChatPacket("out", C.AOCP_PRIVGRP_INVITE, uid))

    async def privategroup_kick(self, user) -> bool:
        uid = self.bot.core("player").id(user)
        if not isinstance(uid, int):
            return False
        return await self.send_packet(AOChatPacket("out", C.AOCP_PRIVGRP_KICK, uid))

    async def buddy_add(self, user, buddy_type: bytes = b"\x01") -> bool:
        uid = user if isinstance(user, int) else self.bot.core("player").id(user)
        if not isinstance(uid, int) or (self.char and uid == self.char["id"]):
            return False
        return await self.send_packet(AOChatPacket("out", C.AOCP_BUDDY_ADD, [uid, buddy_type]))

    async def buddy_remove(self, user) -> bool:
        uid = user if isinstance(user, int) else self.bot.core("player").id(user)
        if not isinstance(uid, int):
            return False
        return await self.send_packet(AOChatPacket("out", C.AOCP_BUDDY_REMOVE, uid))

    def buddy_exists(self, who) -> int:
        uid = who if isinstance(who, int) else self.bot.core("player").id(who)
        if not isinstance(uid, int):
            return 0
        return self.buddies.get(uid, 0)

    def buddy_online(self, who) -> bool:
        return bool(self.buddy_exists(who) & C.AOC_BUDDY_ONLINE)

    async def lookup_user(self, name: str) -> bool:
        name = name.capitalize()
        await self.send_packet(AOChatPacket("out", C.AOCP_CLIENT_LOOKUP, name))
        for _ in range(200):
            if self.bot.core("player").exists(name):
                break
            pr = await self.wait_for_packet(1)
            if pr and getattr(pr, "type", None) == C.AOCP_CLIENT_LOOKUP:
                break
        return self.bot.core("player").exists(name)

    # -- group helpers --------------------------------------------------------
    def lookup_group(self, arg, is_gid_hint: bool = False):
        if not is_gid_hint:
            arg = arg.lower() if isinstance(arg, str) else arg
        return self.gid.get(arg, False)

    def get_gid(self, group):
        return self.lookup_group(group, is_gid_hint=True)

    def get_gname(self, group):
        gid = self.lookup_group(group, is_gid_hint=True)
        if gid is False:
            return False
        return self.gid[gid]

    def group_status(self, group):
        gid = self.get_gid(group)
        if gid is False:
            return False
        return self.grp.get(gid, False)

    # -- login key generation / custom cipher --------------------------------
    @staticmethod
    def _random_hex(bits: int) -> str:
        return os.urandom(bits // 8).hex()

    def generate_login_key(self, servkey: bytes, username: str, password: str) -> str:
        dh_x = int(self._random_hex(256), 16)
        dh_pub = pow(_DH_G, dh_x, _DH_N)
        dh_k = pow(_DH_Y, dh_x, _DH_N)

        payload = username.encode("latin-1") + b"|" + servkey + b"|" + password.encode("latin-1")
        key_hex = format(dh_k, "x")
        key_hex = key_hex.rjust(32, "0") if len(key_hex) < 32 else key_hex[:32]

        prefix = bytes.fromhex(self._random_hex(64))
        length = 8 + 4 + len(payload)
        pad = b" " * ((8 - length % 8) % 8)
        plain = prefix + struct.pack(">I", len(payload)) + payload + pad

        crypted = self._aochat_crypt(key_hex, plain)
        return f"{format(dh_pub, 'x')}-{crypted}"

    @staticmethod
    def _reduce32(value: int) -> int:
        return value & _MASK32

    @classmethod
    def _permute(cls, a: int, b: int, y: tuple[int, int, int, int]) -> tuple[int, int]:
        r32 = cls._reduce32
        c = 0
        d = 0x9E3779B9
        for _ in range(32):
            c = r32(c + d)
            delta_a = r32(
                r32(r32((b << 4) & 0xFFFFFFF0) + y[0]) ^ r32(b + c)
            ) ^ r32(((b >> 5) & 0x07FFFFFF) + y[1])
            a = r32(a + delta_a)
            delta_b = r32(
                r32(r32((a << 4) & 0xFFFFFFF0) + y[2]) ^ r32(a + c)
            ) ^ r32(((a >> 5) & 0x07FFFFFF) + y[3])
            b = r32(b + delta_b)
        return a, b

    @classmethod
    def _aochat_crypt(cls, key_hex: str, data: bytes) -> str:
        if len(key_hex) != 32 or len(data) % 8 != 0:
            raise ValueError("aochat_crypt: bad key/data length")
        keyarr = struct.unpack("<4I", bytes.fromhex(key_hex))
        dataarr = struct.unpack(f"<{len(data) // 4}I", data)
        prev = (0, 0)
        out = bytearray()
        for i in range(0, len(dataarr), 2):
            now = (dataarr[i] ^ prev[0], dataarr[i + 1] ^ prev[1])
            prev = cls._permute(now[0], now[1], keyarr)
            out += struct.pack("<I", prev[0])
            out += struct.pack("<I", prev[1])
        return out.hex()
