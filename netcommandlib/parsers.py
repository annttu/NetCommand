import re
import logging

logger = logging.getLogger("parsers")


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
        parts = [x.strip() for x in re.split(split_pattern, row.strip())]
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


def get_fixed_field_length(string, field):
    """
    Get length of field + following whitespaces
    """
    field_length = len(field)
    if len(string) < field_length:
        raise ValueError("String shorter than field")
    if len(string) == len(field):
        return field_length
    for x in string[len(field):]:
        if x.isspace():
            field_length += 1
        else:
            break
    return field_length


def get_tabular_data_fixed_header_width(data, header, skip_after_header=1):
    """
    Parse tabular data with fixed size
    Guess fixed size from header row
    """
    header_found = False
    field_lengths = []
    out = []
    for row in data.splitlines():
        if not header_found:
            field_lengths = []
            remaining_row = str(row)
            for field in header:
                logger.info("field: %s, remaining_row: '%s'", field, remaining_row)
                if remaining_row.startswith(field):
                    # get length
                    length = get_fixed_field_length(remaining_row, field)
                    logger.debug("Field: %s length: %s", field, length)
                    field_lengths.append(length)
                    remaining_row = remaining_row[length:]
                else:
                    break
            else:
                if len(remaining_row) != 0:
                    logger.info("Garbage after last header field: %s", (remaining_row,))
                header_found = True
            continue
        elif skip_after_header > 0:
            skip_after_header -= 1
            continue
        parts = []
        remaining_row = str(row)
        for field_length in field_lengths:
            parts.append(remaining_row[:field_length])
            remaining_row = remaining_row[field_length:]
        print(parts)
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
