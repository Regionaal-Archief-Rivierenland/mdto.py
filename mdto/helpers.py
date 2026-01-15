# Private helper methods

# enables annotations from mdto.gegevensgroepen without creating a circular import
from __future__ import annotations

import logging
import mimetypes
import re
import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

import lxml.etree as ET

# satisfy type checkers
if TYPE_CHECKING:
    from mdto.gegevensgroepen import (
        BegripGegevens,
        IdentificatieGegevens,
        VerwijzingGegevens,
    )

# setup logging
logger = logging.getLogger("mdto.py")

if os.environ.get("MDTO_QUIET"):
    logger.addHandler(logging.NullHandler())
else:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)

    logging.addLevelName(
        logging.WARNING,
        "\033[1;33m%s\033[1;0m" % logging.getLevelName(logging.WARNING),
    )


@lru_cache(maxsize=1)
def load_tooi_register_gemeenten() -> dict:
    """Transforms the gemeente register JSON into a lookup table, and
    caches the result for subsequent calls.

    Caching this table makes a big difference in performance.

    Returns:
        dict: bidirectional lookup table that maps TOOI gemeentenamen
              to TOOI codes, and vice versa

    """
    import importlib.resources  # importing here improves initialization speed
    import json

    gemeentenaam_key = (
        "https://identifier.overheid.nl/tooi/def/ont/officieleNaamExclSoort"
    )
    gemeentecode_key = "https://identifier.overheid.nl/tooi/def/ont/gemeentecode"

    json_path = importlib.resources.files("mdto.data") / "rwc_gemeenten_compleet_4.json"
    with json_path.open("r") as f:
        raw_dict = json.load(f)

    # transform into a bidirectional lookup table
    gemeente_lookup_table = {}
    for gem in raw_dict:
        # the JSON records things other than gemeente entries
        if not "https://identifier.overheid.nl/tooi/def/ont/Gemeente" in gem["@type"]:
            continue

        naam, code = (
            gem[gemeentenaam_key][0]["@value"],
            gem[gemeentecode_key][0]["@value"],
        )
        # use lowercase version as key
        naam_key = naam.lower()
        gemeente_lookup_table[naam_key] = code
        gemeente_lookup_table[code] = naam

    return gemeente_lookup_table


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


def pronominfo(file: str | Path) -> BegripGegevens:
    """Generate PRONOM information about `file`. This information can be used in
    a Bestand's `<bestandsformaat>` tag.

    Args:
        file (str | Path): Path to the file to inspect

    Raises:
        RuntimeError: siegfried failed to detect PRONOM info

    Returns:
        BegripGegevens: Object with the following properties:
          - `begripLabel`: The file's PRONOM signature name
          - `begripCode`: The file's PRONOM ID
          - `begripBegrippenLijst`: A reference to the PRONOM registry
    """
    import pygfried  # import here for performance

    from mdto.gegevensgroepen import BegripGegevens, VerwijzingGegevens

    # we only care about the first file
    prinfo = pygfried.identify(str(file), detailed=True)["files"][0]

    err = prinfo["errors"]
    if err:
        if "empty" in err:
            logger.warning(f"{file} appears to be an empty file")
        elif "no such file or directory" in err:
            # this specific message only occurs for files
            raise FileNotFoundError(f"{file}: no such file")
        else:
            # just pass on the error
            raise RuntimeError(err)

    # extract match
    matches = prinfo["matches"]
    if len(matches) > 1:
        logger.warning(
            "siegfried returned more than one PRONOM match "
            f"for {file}. Selecting the first one."
        )

    match = matches[0]
    # check if a match was found (matches is non-empty even if no match is found)
    if match["id"] == "UNKNOWN":
        raise RuntimeError(
            f"siegfried failed to detect PRONOM information about {file}"
        )

    # log siegfried's warnings (such as extension mismatches)
    warning = match["warning"]
    if warning:
        logger.warning(f"siegfried reports PRONOM warning about {file}: {warning}")

    return BegripGegevens(
        begripLabel=match["format"],
        begripCode=match["id"],
        begripBegrippenlijst=VerwijzingGegevens("PRONOM-register"),
    )


def mimetypeinfo(file: str | Path) -> BegripGegevens:
    """Generate MIME type information about `file`. This information can be used in
    a Bestand's `<bestandsformaat>` tag.

    Args:
        file (str | Path): Path to the file to inspect

    Raises:
        RuntimeError: failed to detect mimetype info

    Returns:
        BegripGegevens: Object with the following properties:
          - `begripLabel`: The file's MIME subtype
          - `begripCode`: The file's MIME type (top-level type + subtype)
          - `begripBegrippenLijst`: A reference to the IANA registry
    """
    import importlib
    from mdto.gegevensgroepen import BegripGegevens, VerwijzingGegevens

    if importlib.util.find_spec("magic"):
        import magic
        mimetype = magic.from_file(file, mime=True)
    else:
        # strict means: use only mimetypes registered with the IANA
        mimetype, _ = mimetypes.guess_type(file, strict=False)

    if mimetype is None:
        # libmagic never returns None, so know the user has yet to install it.
        #(https://github.com/ahupp/python-magic/issues/252#issuecomment-949082143)
        # TODO: maybe link to mdto.py's installation instructions?
        raise RuntimeError(
            f"failed to detect MIME type information about {file}. "
            "Hint: install the python-magic package to get more comprehensive coverage."
        )
    elif mimetype.endswith("empty"):
        raise RuntimeError(f"{file} appears to be an empty file")

    _, subtype = mimetype.split("/")

    return BegripGegevens(subtype, VerwijzingGegevens("IANA Media types"), mimetype)


def detect_verwijzing(informatieobject: TextIO | str) -> VerwijzingGegevens:
    """A Bestand object must contain a reference to a corresponding
    informatieobject.  Specifically, it expects an <isRepresentatieVan> tag with
    the following children:

    1. <verwijzingNaam>: name of the informatieobject
    2. <verwijzingIdentificatie> (optional): reference to the informatieobject's
    ID and source thereof

    This function infers these so-called 'VerwijzingGegevens' by parsing the XML
    of the file `informatieobject`.

    Args:
        informatieobject (TextIO | str): XML file to infer VerwijzingGegevens from

    Returns:
        VerwijzingGegevens: reference to the informatieobject specified by `informatieobject`
    """
    from mdto.gegevensgroepen import VerwijzingGegevens, IdentificatieGegevens

    id_gegevens = None
    namespaces = {"mdto": "https://www.nationaalarchief.nl/mdto"}
    tree = ET.parse(informatieobject)
    root = tree.getroot()

    id_xpath = ".//mdto:informatieobject/mdto:identificatie/"

    kenmerk = root.find(f"{id_xpath}mdto:identificatieKenmerk", namespaces=namespaces)
    bron = root.find(f"{id_xpath}mdto:identificatieBron", namespaces=namespaces)
    naam = root.find(".//mdto:informatieobject/mdto:naam", namespaces=namespaces)

    if None in [kenmerk, bron]:
        raise ValueError(f"Failed to detect <identificatie> in {informatieobject}")

    if naam is None:
        raise ValueError(f"Failed to detect <naam> in {informatieobject}")

    identificatie = IdentificatieGegevens(kenmerk.text, bron.text)

    return VerwijzingGegevens(naam.text, identificatie)


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


def _valid_mdto_date(date: str, fmts: list[tuple]) -> bool:
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
