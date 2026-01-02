import re

MAC_REGEX = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


def is_valid_mac(mac: str) -> bool:
    return bool(MAC_REGEX.fullmatch(mac))


def parse_hex(s: str) -> int:
    return int(s, 16)


def ids_for(prefix: str, keys) -> list[str]:
    ids = set()
    for k in keys:
        if not k.startswith(prefix):
            continue

        rest = k[len(prefix) :]
        underscore = rest.find("_")

        if underscore == 0:
            ids.add("")
            continue

        if underscore > 0:
            number_part = rest[:underscore]
            if number_part.isdigit():
                ids.add(number_part)

    return sorted(ids, key=lambda x: (0, 0) if x == "" else (1, int(x)))


def safe_int(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def int_or_none(s: str | None) -> int | None:
    st = trim_to_none(s)
    return safe_int(st) if st else None


def trim_to_none(s) -> str | None:
    """
    Trims leading/trailing whitespace from a string and converts empty strings to None.
    """
    if s is None:
        return None
    stripped_s = str(s).strip()  # Ensure input is a string before stripping
    return stripped_s or None


def to_bool(s: str) -> bool:
    return bool(int(s))
