"""AO chat packet encode/decode.

Ported from Sources/AoChatPacket.php, Anarchy Online (AO) wire format only.

Field-type codes:
    I - 32 bit unsigned integer
    S - 8 bit length-prefixed string: uint16 length, bytes
    G - 40 bit binary blob (5 raw bytes)
    i - integer array: uint16 count, uint32[count]
    s - string array: uint16 count, S[count]
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any

from . import constants as C

# args-string per (direction -> packet type)
_PACKET_MAP: dict[str, dict[int, str]] = {
    "in": {
        C.AOCP_LOGIN_SEED: "S",
        C.AOCP_LOGIN_OK: "",
        C.AOCP_LOGIN_ERROR: "S",
        C.AOCP_LOGIN_CHARLIST: "isii",
        C.AOCP_CLIENT_UNKNOWN: "I",
        C.AOCP_CLIENT_NAME: "IS",
        C.AOCP_CLIENT_LOOKUP: "IS",
        C.AOCP_MSG_PRIVATE: "ISS",
        C.AOCP_MSG_VICINITY: "ISS",
        C.AOCP_MSG_VICINITYA: "SSS",
        C.AOCP_MSG_SYSTEM: "S",
        C.AOCP_CHAT_NOTICE: "IIIS",
        C.AOCP_BUDDY_LOGONOFF: "IIS",
        C.AOCP_BUDDY_REMOVE: "I",
        C.AOCP_PRIVGRP_INVITE: "I",
        C.AOCP_PRIVGRP_KICK: "I",
        C.AOCP_PRIVGRP_PART: "I",
        C.AOCP_PRIVGRP_CLIJOIN: "II",
        C.AOCP_PRIVGRP_CLIPART: "II",
        C.AOCP_PRIVGRP_MESSAGE: "IISS",
        C.AOCP_PRIVGRP_REFUSE: "II",
        C.AOCP_GROUP_ANNOUNCE: "GSIS",
        C.AOCP_GROUP_PART: "G",
        C.AOCP_GROUP_MESSAGE: "GISS",
        C.AOCP_PING: "S",
        C.AOCP_ADM_MUX_INFO: "iii",
    },
    "out": {
        C.AOCP_LOGIN_CHARID: "IIIS",
        C.AOCP_LOGIN_REQUEST: "ISS",
        C.AOCP_LOGIN_SELECT: "I",
        C.AOCP_CLIENT_LOOKUP: "S",
        C.AOCP_MSG_PRIVATE: "ISS",
        C.AOCP_BUDDY_ADD: "IS",
        C.AOCP_BUDDY_REMOVE: "I",
        C.AOCP_ONLINE_SET: "I",
        C.AOCP_PRIVGRP_INVITE: "I",
        C.AOCP_PRIVGRP_KICK: "I",
        C.AOCP_PRIVGRP_JOIN: "I",
        C.AOCP_PRIVGRP_PART: "I",
        C.AOCP_PRIVGRP_KICKALL: "",
        C.AOCP_PRIVGRP_MESSAGE: "ISS",
        C.AOCP_GROUP_DATA_SET: "GIS",
        C.AOCP_GROUP_MESSAGE: "GSS",
        C.AOCP_GROUP_CM_SET: "GIIII",
        C.AOCP_CLIENTMODE_GET: "IG",
        C.AOCP_CLIENTMODE_SET: "IIII",
        C.AOCP_PING: "S",
        C.AOCP_CC: "s",
    },
}


def _as_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("latin-1", errors="replace")
    raise TypeError(f"Cannot coerce {value!r} to bytes")


class AOChatPacket:
    """A single decoded ('in') or encode-ready ('out') AO chat packet."""

    def __init__(self, direction: str, packet_type: int, data: Any):
        self.dir = direction
        self.type = packet_type
        self.args: list[Any] = []
        self.data: bytes = b""

        args_spec = _PACKET_MAP.get(direction, {}).get(packet_type)
        if args_spec is None:
            raise ValueError(f"Unsupported packet type ({direction}, {packet_type})")

        if direction == "in":
            self._decode(args_spec, _as_bytes(data))
        else:
            self._encode(args_spec, data)

    def _decode(self, args_spec: str, data: bytes) -> None:
        for code in args_spec:
            if code == "I":
                (res,) = struct.unpack(">I", data[:4])
                data = data[4:]
            elif code == "B":
                (res,) = struct.unpack(">B", data[:1])
                data = data[1:]
            elif code == "S":
                (length,) = struct.unpack(">H", data[:2])
                res = data[2 : 2 + length]
                data = data[2 + length :]
            elif code == "G":
                res = data[:5]
                data = data[5:]
            elif code == "i":
                (count,) = struct.unpack(">H", data[:2])
                res = list(struct.unpack(f">{count}I", data[2 : 2 + 4 * count]))
                data = data[2 + 4 * count :]
            elif code == "s":
                (count,) = struct.unpack(">H", data[:2])
                data = data[2:]
                res = []
                for _ in range(count):
                    (slen,) = struct.unpack(">H", data[:2])
                    res.append(data[2 : 2 + slen])
                    data = data[2 + slen :]
            else:
                raise ValueError(f"Unknown argument type! ({code})")
            self.args.append(res)

    def _encode(self, args_spec: str, data: Any) -> None:
        if isinstance(data, (list, tuple)):
            args = list(data)
        else:
            args = [data]

        out = b""
        for code in args_spec:
            if not args:
                raise ValueError(f"Missing argument for packet (type {self.type})")
            item = args.pop(0)
            if code == "I":
                out += struct.pack(">I", item & 0xFFFFFFFF)
            elif code == "i":
                out += struct.pack(">H", item)
            elif code == "S":
                item = _as_bytes(item)
                out += struct.pack(">H", len(item)) + item
            elif code == "G":
                out += _as_bytes(item)
            elif code == "s":
                out += struct.pack(">H", len(item))
                for elem in item:
                    elem = _as_bytes(elem)
                    out += struct.pack(">H", len(elem)) + elem
            else:
                raise ValueError(f"Unknown argument type! ({code})")
        self.data = out
