# Private helper methods

import logging
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import List, Tuple, TextIO


# setup logging
logging.basicConfig(
    format="[%(asctime)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S"
)
logging.addLevelName(
    # colorize warning messages
    logging.WARNING,
    "\033[1;33m%s\033[1;0m" % logging.getLevelName(logging.WARNING),
)


@lru_cache(maxsize=1)
def load_tooi_register_gemeenten():
    """This function caches the JSON dict, so that it remains loaded within a single python session.

    Makes a big difference in performance.
    """
    import importlib.resources  # importing here improves helpers.py initialization speed
    import json

    json_path = importlib.resources.files("mdto.data") / "rwc_gemeenten_compleet_4.json"
    with json_path.open("r") as f:
        return json.load(f)


def process_file(file_or_filename: TextIO | str) -> TextIO:
    """Return file-object if input is already a file.
    Otherwise, assume the argument is a path, and convert
    it to a new file-object.

    Note:
        The returned file-object is always in read-only mode.
    """

    # filename or path?
    if isinstance(file_or_filename, (str, Path)):
        return open(file_or_filename, "r")
    # file-like object?
    elif hasattr(file_or_filename, "read"):
        # if file-like object, force it to be opened read-only
        if file_or_filename.writable():
            filename = file_or_filename.name
            file_or_filename.close()  # FIXME: callers might get confused by suddenly closed files
            return open(filename, "r")
        else:
            return file_or_filename
    else:
        raise TypeError(
            f"Expected file object or str, but got value of type {type(file_or_filename)}"
        )


def valid_url(url: str) -> bool:
    """Checks if URL(s) are RFC 3986 compliant URIs.

    Args:
        url (str): URL or URLs to check

    Returns:
        bool: whether the URL(s) are RFC 3986 compliant URIs
    """
    from validators import url as _valid_url

    return _valid_url(url)


# contains (datefmt, len), in order to ensure precense of zero padded months/days
date_fmt_precise = [("%Y-%m-%d", 10)]
date_fmts = date_fmt_precise + [
    ("%Y", 4),
    ("%Y-%m", 7),
]
datetime_fmts = date_fmts + [("%Y-%m-%dT%H:%M:%S", 19)]
tz_regex = re.compile(r"(.*?)(Z|[+-](\d{2}):(\d{2}))?")


def _valid_mdto_date(date: str, fmts: List[Tuple]) -> bool:
    """Generic date checking function; use valid_mdto_datetime or valid_mdto_date"""
    # strip and capture timezone info
    date, _, tz_info_hh, tz_info_mm = tz_regex.fullmatch(date).groups()

    #  verify timezone information
    if tz_info_mm:
        # check if in range of hh:mm
        if int(tz_info_mm) > 59 or int(tz_info_hh) > 23:
            return False

    for fmt, expected_len in fmts:
        try:
            # check for precense of zero padding
            if len(date) == expected_len:
                datetime.strptime(date, fmt)
                return True
        except ValueError:  # striptime() raises this on misformatted dates
            continue

    return False


def valid_mdto_datetime(date: str) -> bool:
    """Check if date is a correctly formatted datetime, year+month, or year."""
    return _valid_mdto_date(date, datetime_fmts)


def valid_mdto_datetime_precise(date: str) -> bool:
    """Check if date matches xs:datetime (YYYY-MM-DDThh:mm:ss) exactly."""
    return _valid_mdto_date(date, [datetime_fmts[-1]])


def valid_mdto_date(date: str) -> bool:
    """Check if date is a correctly formatted calendar date, year+month, or year."""
    return _valid_mdto_date(date, date_fmts)


def valid_mdto_date_precise(date: str) -> bool:
    """Check if date matches xs:date (YYYY-MM-DD) exactly."""
    return _valid_mdto_date(date, date_fmt_precise)


def valid_duration(duration: str) -> bool:
    """Check if duration is complaint with xs:duration/ISO8601."""

    # modified from https://github.com/gweis/isodate
    return len(duration) > 1 and bool(
        re.fullmatch(
            r"\+?P"
            r"(?:\d+(?:[.,]\d+)?Y)?"
            r"(?:\d+(?:[.,]\d+)?M)?"
            r"(?:\d+(?:[.,]\d+)?W)?"
            r"(?:\d+(?:[.,]\d+)?D)?"
            r"(?:T"
            r"(?:\d+(?:[.,]\d+)?H)?"
            r"(?:\d+(?:[.,]\d+)?M)?"
            r"(?:\d+(?:[.,]\d+)?S)?"
            r")?",
            duration,
        )
    )


def valid_langcode(langcode: str) -> bool:
    """Check if language code is complaint with xs:language/RFC3066."""
    return bool(re.fullmatch(r"[a-zA-Z]{1,8}(-[a-zA-Z0-9]{1,8})*", langcode))
