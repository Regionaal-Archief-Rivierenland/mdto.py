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

quiet = os.environ.get("MDTO_QUIET")
if quiet not in ["false", "0"]:
    logger.addHandler(logging.NullHandler())
else:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)

    logging.addLevelName(
        logging.WARNING,
        "\033[1;33m%s\033[1;0m" % logging.getLevelName(logging.WARNING),
    )


def load_tooi_register(json_filename: str, entity_type: str) -> dict:
    """Generic function to load TOOI register JSON into a lookup table.
    
    Args:
        json_filename: Name of the JSON file in mdto.data
        entity_type: The @type value to filter by (e.g., "Gemeente", "Provincie", "Waterschap")
        
    Returns:
        dict: bidirectional lookup table mapping names to codes and vice versa
    """
    import importlib.resources
    import json

    code_key = "https://identifier.overheid.nl/tooi/def/ont/organisatiecode"
    naam_key = "https://identifier.overheid.nl/tooi/def/ont/officieleNaamExclSoort"
    
    json_path = importlib.resources.files("mdto.data") / json_filename
    with json_path.open("r") as f:
        raw_dict = json.load(f)

    lookup_table = {}
    for item in raw_dict:
        if not f"https://identifier.overheid.nl/tooi/def/ont/{entity_type}" in item["@type"]:
            continue

        naam, code = (
            item[naam_key][0]["@value"],
            item[code_key][0]["@value"],
        )
        lookup_table[naam.lower()] = code
        lookup_table[code] = naam

    return lookup_table

# Caching the result of these functions makes a big difference in performance
@lru_cache(maxsize=1)
def load_tooi_register_gemeenten() -> dict:
    """Transforms the gemeente register JSON into a lookup table, and
    caches the result for subsequent calls.

    Returns:
        dict: bidirectional lookup table that maps TOOI gemeentenamen
              to TOOI codes, and vice versa
    """
    return load_tooi_register("rwc_gemeenten_compleet_4.json", "Gemeente")

@lru_cache(maxsize=1)
def load_tooi_register_provincies() -> dict:
    """Transforms the provincie register JSON into a lookup table, and
    caches the result for subsequent calls.

    Returns:
        dict: bidirectional lookup table that maps TOOI provincienamen
              to TOOI codes, and vice versa
    """
    return load_tooi_register("rwc_provincies_compleet_1.json", "Provincie")

@lru_cache(maxsize=1)
def load_tooi_register_waterschappen() -> dict:
    """Transforms the waterschap register JSON into a lookup table, and
    caches the result for subsequent calls.

    Returns:
        dict: bidirectional lookup table that maps TOOI waterschapsnamen
              to TOOI codes, and vice versa
    """
    return load_tooi_register("rwc_waterschappen_compleet_2.json", "Waterschap")


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
            raise RuntimeError(f"{file} appears to be an empty file")
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
tz_regex = re.compile(r"(.*?)(Z|[+-]\d{2}:\d{2})?")

def str_to_datetime(date: str, fmts: list[Tuple] = datetime_fmts) -> datetime:
    """Convert string to datetime object. Assumes `date` is already validated."""
    date, tz = tz_regex.fullmatch(date).groups()
    tz = tz or ''

    for fmt, fmt_len in fmts:
        if len(date) == fmt_len:
            return datetime.strptime(date + tz, f"{fmt}{tz and '%z'}")

    raise ValueError


def _valid_mdto_date(date: str, fmts: list[tuple]) -> bool:
    """Generic date checking function; use valid_mdto_datetime or valid_mdto_date"""
    try:
        str_to_datetime(date, fmts)
        return True
    except ValueError:  # striptime() raises this on misformatted dates
        return False

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
