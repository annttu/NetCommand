
def compare_version_old(a, b):
    """
    Returns 1 if a is bigger than b, 0 if same and -1 if b is bigger than a
    """
    if a == b:
        return 0
    a = a.strip().split("-")[0]
    b = b.strip().split("-")[0]
    a_build = 0
    a_patch = 0
    if len(a.split(".")) >= 4:
        a_major, a_minor, a_patch, a_build = a.split(".", 3)
    elif len(a.split(".")) >= 3:
        a_major, a_minor, a_patch = a.split(".", 2)
    elif len(a.split(".")) >= 2:
        a_major, a_minor = a.split(".", 1)
    else:
        raise ConnectionError("Invalid version number %s" % a)

    b_build = 0
    b_patch = 0
    if len(b.split(".")) >= 4:
        b_major, b_minor, b_patch, b_build = b.split(".", 3)
    elif len(b.split(".")) >= 3:
        b_major, b_minor, b_patch = b.split(".", 2)
        b_build = 0
    elif len(b.split(".")) >= 2:
        b_major, b_minor = b.split(".", 2)
    else:
        raise ConnectionError("Invalid version number %s" % b)

    a_major = int(a_major)
    a_minor = int(a_minor)
    a_patch = int(a_patch)
    a_build = int(a_build)
    b_major = int(b_major)
    b_minor = int(b_minor)
    b_patch = int(b_patch)
    b_build = int(b_build)

    if a_major > b_major:
        return 1
    elif b_major > a_major:
        return -1
    if a_minor > b_minor:
        return 1
    elif b_minor > a_minor:
        return -1
    if a_patch > b_patch:
        return 1
    elif b_patch > a_patch:
        return -1
    if a_build > b_build:
        return 1
    elif b_build > a_build:
        return -1
    return 0


def compare_version(a, b):
    a = a.strip().split("-")[0]
    b = b.strip().split("-")[0]
    a_parts = [int(x) for x in a.split(".")]
    b_parts = [int(x) for x in b.split(".")]
    max_parts = max(len(a_parts), len(b_parts))
    if len(a_parts) < max_parts:
        a_parts += [0] * (max_parts - len(a_parts))
    if len(b_parts) < max_parts:
        b_parts += [0] * (max_parts - len(b_parts))
    for idx in range(max_parts):
        if a_parts[idx] > b_parts[idx]:
            return 1
        if a_parts[idx] < b_parts[idx]:
            return -1
    return 0


def min_version(version, to_check):
    return compare_version(to_check, version) >= 0


def max_version(version, to_check):
    return compare_version(to_check, version) <= 0
