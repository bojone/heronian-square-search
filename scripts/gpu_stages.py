MAX_STAGE = 81


def stage_first(index):
    if index <= 15:
        return 9800000 - 200000 * index
    return 6800000 - 100000 * (index - 15)


def stage_index(name):
    if not name or len(name) > 2 or not name.isascii() or not name.isalpha() or not name.islower():
        raise ValueError(f"invalid stage: {name!r}")
    value = 0
    for char in name:
        value = value * 26 + ord(char) - ord("a") + 1
    return value - 1


def stage_name(index):
    if index < 0:
        raise ValueError(index)
    chars = []
    value = index + 1
    while value:
        value, remainder = divmod(value - 1, 26)
        chars.append(chr(ord("a") + remainder))
    return "".join(reversed(chars))
