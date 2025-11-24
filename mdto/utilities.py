import os
import re
from pathlib import Path
from typing import List, TextIO
import mimetypes

import lxml.etree as ET
import pygfried

from mdto.gegevensgroepen import *

# allow running directly from interpreter
try:
    from . import helpers
except ImportError:
    import helpers


def _pronominfo_siegfried(file: str | Path) -> BegripGegevens:
    # we only care about the first file
    prinfo = pygfried.identify(str(file), detailed=True)["files"][0]

    if "empty" in prinfo["errors"]:
        helpers.logging.warning(f"{file} appears to be an empty file")

    # extract match
    matches = prinfo["matches"]
    if len(matches) > 1:
        helpers.logging.warning(
            "siegfried returned more than one PRONOM match "
            f"for {file}. Selecting the first one."
        )
    match = matches[0]

    # check if a match was found
    if match["id"] == "UNKNOWN":
        raise RuntimeError(
            f"siegfried failed to detect PRONOM information about {file}"
        )

    # log siegfried's warnings (such as extension mismatches)
    warning = match["warning"]
    if warning:
        helpers.logging.warning(
            f"siegfried reports PRONOM warning about {file}: {warning}"
        )

    return BegripGegevens(
        begripLabel=match["format"],
        begripCode=match["id"],
        begripBegrippenlijst=VerwijzingGegevens("PRONOM-register"),
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
    # check if file exists and is indeed a file (as opposed to a directory)
    if not os.path.isfile(file):
        raise TypeError(f"File '{file}' does not exist or might be a directory")

    return _pronominfo_siegfried(file)


def mimetypeinfo(file: str | Path) -> BegripGegevens:
    """Generate MIME type information about `file`. This information can be used in
    a Bestand's `<bestandsformaat>` tag.

    Args:
        file (str | Path): Path to the file to inspect

    Returns:
        BegripGegevens: Object with the following properties:
          - `begripLabel`: The file's MIME subtype
          - `begripCode`: The file's MIME type (top-level type + subtype)
          - `begripBegrippenLijst`: A reference to the IANA registry
    """
    # strict means: use only mimetypes registered with the IANA
    # this should be .guess_file_type when py3.13 releases
    mimetype, _ = mimetypes.guess_type(file, strict=True)

    if mimetype is None:
        raise RuntimeError(f"failed to detect MIME type information about {file}")

    _, subtype = mimetype.split("/")

    return BegripGegevens(subtype, VerwijzingGegevens("IANA Media types"), mimetype)

def _detect_verwijzing(informatieobject: TextIO | str) -> VerwijzingGegevens:
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

    identificatie = IdentificatieGegevens(kenmerk.text, bron.text)

    if naam is None:
        raise ValueError(f"Failed to detect <naam> in {informatieobject}")

    return VerwijzingGegevens(naam.text, identificatie)

def bestand_from_file(
    file: TextIO | str,
    isrepresentatievan: VerwijzingGegevens | TextIO | str,
    use_mimetype: bool = False,
) -> Bestand:
    """Convenience function for creating a Bestand object from a file.

    This function differs from calling Bestand() directly in that it
    infers most technical information for you (checksum, PRONOM info,
    etc.) by inspecting `file`. `<identificatie>` is set
    to a UUID.

    Args:
        file (TextIO | str): the file the Bestand object represents
        isrepresentatievan (TextIO | str | VerwijzingGegevens): a XML
          file containing an informatieobject, or a
          VerwijzingGegevens referencing an informatieobject.
          Used to construct <isRepresentatieVan>.
        use_mimetype (Optional[bool]): populate `<bestandsformaat>`
          with mimetype instead of pronom info

    Example:
      ```python

     verwijzing_obj = VerwijzingGegevens("vergunning.mdto.xml")
     bestand = mdto.bestand_from_file(
          "vergunning.pdf",

          isrepresentatievan=verwijzing_obj  # or pass the actual file
     )
     bestand.save("vergunning.pdf.bestand.mdto.xml")
     ```

    Returns:
        Bestand: new Bestand object
    """
    file = helpers.process_file(file)

    # set <naam> to basename
    naam = os.path.basename(file.name)

    omvang = os.path.getsize(file.name)
    if not use_mimetype:
        bestandsformaat = pronominfo(file.name)
    else:
        bestandsformaat = mimetypeinfo(file.name)

    checksum = ChecksumGegevens.from_file(file)

    # file or file path?
    if isinstance(isrepresentatievan, (str, Path)) or hasattr(
        isrepresentatievan, "read"
    ):
        informatieobject_file = helpers.process_file(isrepresentatievan)
        # Construct verwijzing from informatieobject file
        verwijzing_obj = _detect_verwijzing(informatieobject_file)
        informatieobject_file.close()
    elif isinstance(isrepresentatievan, VerwijzingGegevens):
        verwijzing_obj = isrepresentatievan
    else:
        raise TypeError(
            "isrepresentatievan must either be a path, file, or a VerwijzingGegevens object."
        )

    file.close()

    return Bestand(
        IdentificatieGegevens.uuid(),
        naam,
        omvang,
        bestandsformaat,
        checksum,
        verwijzing_obj,
    )


def verwijzing_gegevens_from_tooi_gemeentenaam(gemeentenaam: str) -> VerwijzingGegevens:
    """Convenience function for creating a reference to a municipality in the TOOI
    register.

    Expects a name from the 'TOOI register gemeente compleet' (e.g. `Tiel` or
    `Gemeente Brielle`), and returns a VerwijzingGegevens with a corresponding code.

    Example:

       ```python
       >>> archiefvormer = verwijzing_gegevens_from_tooi_gemeentenaam('Tiel')
       >>> print(archiefvormer.verwijzingIdentificatie.identificatieKenmerk)
       gm0218
       ```

    Raises:
        ...

    Args:
       gemeentenaam: The name of the municipality. May be prefixed with "Gemeente".

    Returns:
        VerwijzingGegevens: reference to a municipality in the TOOI register,
        including its assigned code

    """

    tooi_register_gemeenten = helpers.load_tooi_register_gemeenten()

    naam_key = "https://identifier.overheid.nl/tooi/def/ont/officieleNaamExclSoort"
    naam_incl_soort_key = (
        "https://identifier.overheid.nl/tooi/def/ont/officieleNaamInclSoort"
    )
    code_key = "https://identifier.overheid.nl/tooi/def/ont/organisatiecode"

    gemeentenaam = gemeentenaam.lower().removeprefix("gemeente ")

    for gem in tooi_register_gemeenten:
        gemeentenaam_tooi = gem[naam_key][0]["@value"]
        if gemeentenaam == gemeentenaam_tooi.lower():
            code = gem[code_key][0]["@value"]

            return VerwijzingGegevens(
                gem[naam_incl_soort_key][0]["@value"].title(),
                IdentificatieGegevens(code, "TOOI register gemeenten compleet"),
            )

    raise ValueError(
        f"'{gemeentenaam.title()}' not found in 'TOOI register gemeenten compleet'. "
        "For a list of possible values, see https://identifier.overheid.nl/tooi/set/rwc_gemeenten_compleet"
    )


def verwijzing_gegevens_from_tooi_gemeentecode(gemeentecode: str) -> VerwijzingGegevens:
    """Convenience function for creating a reference to a municipality in the TOOI
    register.

    Expects a code from the 'TOOI register gemeente compleet' (e.g. `gm0218)`, and
    returns a VerwijzingGegevens with the corresponding name.

    Example:

       ```python
       >>> archiefvormer = verwijzing_gegevens_from_tooi_gemeentecode('gm0218')
       >>> print(archiefvormer.verwijzingNaam)
       Gemeente Tiel
       ```

    Args:
       gemeentecode: Four-digit code that has been assigned to a municipality by
       TOOI. May optionally be prefixed with the string "gm".

     Returns:
        VerwijzingGegevens: reference to a municipality in the TOOI register,
        including its full name. Note that this name is always prefixed with "Gemeente".
    """
    if not (match := re.fullmatch(r"(gm)?(\d{4})", gemeentecode.lower())):
        raise ValueError(f"Invalid gemeentecode '{gemeentecode}'")

    gemeentecode = match.groups()[-1]

    tooi_register_gemeenten = helpers.load_tooi_register_gemeenten()

    naam_key = "https://identifier.overheid.nl/tooi/def/ont/officieleNaamInclSoort"
    code_key = "https://identifier.overheid.nl/tooi/def/ont/gemeentecode"


    for gem in tooi_register_gemeenten:
        tooi_code = gem[code_key][0]["@value"]
        if gemeentecode == tooi_code:
            return VerwijzingGegevens(
                gem[naam_key][0]["@value"].title(),
                IdentificatieGegevens(f"gm{gemeentecode}", "TOOI register gemeenten compleet"),
            )

    raise ValueError(
        f"Code '{gemeentecode}' not found in 'TOOI register gemeenten compleet'. "
        "For a list of possible values, see https://identifier.overheid.nl/tooi/set/rwc_gemeenten_compleet"
    )


def open(mdto_xml: TextIO | str) -> Object:
    """The same as calling `Informatieobject.open()` or `Bestand.open()`, but
    without having to know wether the object to be opened is a Bestand or
    Informatieobject.

    Note:
        This is the same as
        ```python
        from mdto.gegevensgroepen import Object
        # informatieobject_of_bestand = Object.open(...)
        ```
    """
    return Object.open(mdto_xml)
