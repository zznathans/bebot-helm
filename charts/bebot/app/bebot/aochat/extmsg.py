"""Extended ("~&...") AO chat message parser.

Ported from Sources/AoChatExtMsg.php.
"""
from __future__ import annotations

AOEM_UNKNOWN = "AOEM_UNKNOWN"

# category -> instance -> (type_name, format_string, encoding_spec)
MSG_CAT: dict[int, dict[int, tuple[str, str, str]]] = {
    501: {
        0xAD0AE9B: (
            "AOEM_ORG_LEAVE",
            "{NAME} kicked from organization (alignment changed).",
            "s{NAME}",
        ),
    },
    506: {
        0x0C299D4: (
            "AOEM_NW_ATTACK",
            "The {ATT_SIDE} organization {ATT_ORG} just entered a state of war! "
            "{ATT_NAME} attacked the {DEF_SIDE} organization {DEF_ORG}'s tower in "
            "{ZONE} at location ({X}, {Y}).",
            "R{ATT_SIDE}/s{ATT_ORG}/s{ATT_NAME}/R{DEF_SIDE}/s{DEF_ORG}/s{ZONE}/i{X}/i{Y}",
        ),
        0x8CAC524: (
            "AOEM_NW_ABANDON",
            "Notum Wars Update: The {SIDE} organization {ORG} lost their base in {ZONE}.",
            "R{SIDE}/s{ORG}/s{ZONE}",
        ),
        0x70DE9B2: (
            "AOEM_NW_OPENING",
            "(PLAYER) just initiated an attack on playfield (PF) at location "
            "((X),(Y)). That area is controlled by (DEF_ORG). All districts "
            "controlled by your organization are open to attack! You are in a "
            "state of war. Leader chat informed.",
            "s(PLAYER)/i(PF)/i(X)/i(Y)/s(DEF_ORG)",
        ),
        0x5A1D609: (
            "AOEM_NW_TOWER_ATT_ORG",
            "The tower (TOWER) in (ZONE) was just reduced to (HEALTH) % health by "
            "(ATT_NAME) from the (ATT_ORG) organization!",
            "s(TOWER)/s(ZONE)/i(HEALTH)/s(ATT_NAME)/s(ATT_ORG)",
        ),
        0xD5A1D68: (
            "AOEM_NW_TOWER_ATT",
            "The tower (TOWER) in (ZONE) was just reduced to (HEALTH) % health by (ATT_NAME)!",
            "s(TOWER)/s(ZONE)/i(HEALTH)/s(ATT_NAME)",
        ),
        0xFD5A1D4: (
            "AOEM_NW_TOWER",
            "The tower (TOWER) in (ZONE) was just reduced to (HEALTH) % health!",
            "s(TOWER)/s(ZONE)/i(HEALTH)",
        ),
    },
    508: {
        0xA5849E7: (
            "AOEM_ORG_JOIN",
            "{INVITER} invited {NAME} to your organization.",
            "s{INVITER}/s{NAME}",
        ),
        0x2360067: (
            "AOEM_ORG_KICK",
            "{KICKER} kicked {NAME} from the organization.",
            "s{KICKER}/s{NAME}",
        ),
        0x2BD9377: (
            "AOEM_ORG_LEAVE",
            "{NAME} has left the organization.",
            "s{NAME}",
        ),
        0x8487156: (
            "AOEM_ORG_FORM",
            "{NAME} changed the organization governing form to {FORM}.",
            "s{NAME}/s{FORM}",
        ),
        0x88CC2E7: (
            "AOEM_ORG_DISBAND",
            "{NAME} has disbanded the organization.",
            "s{NAME}",
        ),
        0xC477095: (
            "AOEM_ORG_VOTE",
            "Voting notice: {SUBJECT}\nCandidates: {CHOICES}\nDuration: {DURATION} minutes",
            "s{SUBJECT}/u{MINUTES}/s{CHOICES}",
        ),
        0x9F2CB84: (
            "AOEM_ORG_ENDVOTE",
            'Organization leader has stopped the voting with message : "{MSG}"',
            "s{MSG}",
        ),
        0xA8241D4: (
            "AOEM_ORG_STRIKE",
            "Blammo! {NAME} has launched an orbital attack!",
            "s{NAME}",
        ),
        0x5517B44: (
            "AOEM_ORG_TAX",
            "Your leader, {NAME}, just changed the organizational tax. The new tax "
            "is {NEW} credits (the old value was {OLD}).",
            "s{NAME}/u{NEW}/u{OLD}",
        ),
        0xE5E16F8: (
            "AOEM_ORG_LEAD",
            "Leadership has been given to {NAME}.",
            "s{NAME}",
        ),
    },
    1001: {
        0x01: (
            "AOEM_AI_CLOAK",
            "{NAME} turned the cloaking device in your city {STATUS}.",
            "s{NAME}/s{STATUS}",
        ),
        0x02: (
            "AOEM_AI_RADAR",
            "Your radar station is picking up alien activity in the area surrounding your city.",
            "",
        ),
        0x03: (
            "AOEM_AI_ATTACK",
            "Your city in {ZONE} has been targeted by hostile forces.",
            "s{ZONE}",
        ),
        0x04: (
            "AOEM_AI_HQ_REMOVE",
            "{NAME} removed the organization headquarters in {ZONE}.",
            "s{NAME}/s{ZONE}",
        ),
        0x05: (
            "AOEM_AI_REMOVE_INIT",
            "{NAME} initiated removal of a {TYPE} in {ZONE}.",
            "s{NAME}/R{TYPE}/s{ZONE}",
        ),
        0x06: (
            "AOEM_AI_REMOVE",
            "{NAME} removed a {TYPE} in {ZONE}.",
            "s{NAME}/R{TYPE}/s{ZONE}",
        ),
        0x07: (
            "AOEM_AI_HQ_REMOVE_INIT",
            "{NAME} initiated removal of the organization headquarters in {ZONE}.",
            "s{NAME}/s{ZONE}",
        ),
    },
}

REF_CAT: dict[int, dict[int, str]] = {
    509: {0x00: "Normal House"},
    2005: {0x00: "Neutral", 0x01: "Clan", 0x02: "Omni"},
}


class AOExtMsg:
    def __init__(self, raw: str | bytes | None = None):
        self.type = AOEM_UNKNOWN
        self.args: dict[str, object] = {}
        self.text: str = ""
        if raw:
            self.read(raw)

    def arg(self, name: str):
        return self.args.get("{" + name.upper() + "}")

    def read(self, msg: str | bytes) -> bool:
        if isinstance(msg, bytes):
            msg = msg.decode("latin-1")
        if not msg.startswith("~&"):
            return False
        msg = msg[2:]
        msg, category = self._b85g(msg)
        msg, instance = self._b85g(msg)
        cat = MSG_CAT.get(category)
        entry = cat.get(instance) if cat else None
        if entry is None:
            print(f"\nAOChat ExtMsg Debug: Unknown Cat: {category} Instance: {instance}\n")
            return False
        typ, fmt, enc = entry
        args: dict[str, object] = {}
        if enc:
            for part in enc.split("/"):
                code, name = part[0], part[1:]
                msg = msg[1:]  # skip data-type id byte
                if code == "s":
                    length = ord(msg[0]) - 1
                    args[name] = msg[1 : 1 + length]
                    msg = msg[1 + length :]
                elif code in ("i", "u"):
                    msg, num = self._b85g(msg)
                    args[name] = num
                elif code == "R":
                    msg, cat_id = self._b85g(msg)
                    msg, ins_id = self._b85g(msg)
                    ref = REF_CAT.get(cat_id, {})
                    args[name] = ref.get(ins_id, f"Unknown ({cat_id}, {ins_id})")
        text = fmt
        for key, value in args.items():
            text = text.replace(key, str(value))
        self.type = typ
        self.text = text
        self.args = args
        return True

    @staticmethod
    def _b85g(s: str) -> tuple[str, int]:
        n = 0
        for i in range(5):
            n = n * 85 + ord(s[i]) - 33
        return s[5:], n
