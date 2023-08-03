import re


def get_vertical_data_row(data, key, delimiter=":"):
    for row in data.splitlines():
        if delimiter not in row:
            continue
        name, value = row.split(delimiter, 1)
        name = name.strip()
        value = value.strip()
        if key == name:
            return value.strip()


def get_regex_data_row(data, pattern):
    for row in data.splitlines():
        match = re.match(pattern, row)
        if match:
            return match.groups()[0]


def get_tabular_data(data, header, delimiter=" ", skip_after_header=1):
    header_found = False
    out = []
    split_pattern = "\\s*" + delimiter + "\\s*"
    for row in data.splitlines():
        parts = re.split(split_pattern, row)
        if not header_found:
            if parts == header:
                header_found = True
            continue
        if skip_after_header > 0:
            skip_after_header -= 1
            continue
        if not row.strip():
            continue
        out.append(dict(zip(header, parts)))
    return out


def match_text(data, text):
    for row in data.splitlines():
        if text in row:
            return row
    return None


def match_pattern(data, pattern):
    for row in data.splitlines():
        match = re.match(pattern, row)
        if match:
            return match.groups()
    return None
