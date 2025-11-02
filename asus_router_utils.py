def parse_hex(s: str) -> int:
    return int(s, 16)

def ids_for(prefix: str, keys) -> list[int]:
    return sorted({
        int(k[len(prefix):k.index("_")])
        for k in keys
        if k.startswith(prefix) and "_" in k
    }, key=int)
