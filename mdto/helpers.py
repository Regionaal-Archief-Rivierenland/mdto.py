# Private helper methods

import importlib.resources
import logging
import json
from functools import lru_cache
from pathlib import Path
from typing import List, TextIO

import validators

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
    with importlib.resources.open_text(
        "mdto.data", "rwc_gemeenten_compleet_4.json"
    ) as f:
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


def validate_url_or_urls(url: str | List[str]) -> bool:
    """Checks if URL(s) are RFC 3986 compliant URIs.

    Args:
        url (str | List[str]): URL or URLs to check

    Returns:
        bool: whether the URL(s) are RFC 3986 compliant URIs
    """
    if url is None:  # in MDTO, URLS are never mandatory
        return True
    # listify string
    url = [url] if isinstance(url, str) else url
    return all(validators.url(u) for u in url)
