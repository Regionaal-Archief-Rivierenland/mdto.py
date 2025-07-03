import hashlib
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, TextIO, Type, Any
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

    Returns:
        BegripGegevens: Object with the following attributes:
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
    mimetype, _ = mimetypes.guess_file_type(file, strict=True)

    if mimetype is None:
        raise RuntimeError(f"failed to detect MIME type information about {file}")

    subtype = re.search(r".*\/(.*)", mimetype).group(1)

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
    identificatie: IdentificatieGegevens | List[IdentificatieGegevens],
    isrepresentatievan: VerwijzingGegevens | TextIO | str,
    url: str | None = None,
    use_mimetype: bool = False,
) -> Bestand:
    """Convenience function for creating a Bestand object from a file.

    This function differs from calling Bestand() directly in that it
    infers most technical information for you (checksum, PRONOM info,
    etc.) by inspecting `file`. The value of <naam>, for example, is
    always set to the basename of `file`.


    Args:
        file (TextIO | str): the file the Bestand object represents
        identificatie (IdentificatieGegevens | List[IdentificatieGegevens]):
          identificatiekenmerk of Bestand object
        isrepresentatievan (TextIO | str | VerwijzingGegevens): a XML
          file containing an informatieobject, or a
          VerwijzingGegevens referencing an informatieobject.
          Used to construct the values for <isRepresentatieVan>.
        url (Optional[str]): value of <URLBestand>
        use_mimetype (Optional[bool]): populate `<bestandsformaat>`
          with mimetype instead of pronom info

    Example:
      ```python

     verwijzing_obj = VerwijzingGegevens("vergunning.mdto.xml")
     bestand = mdto.bestand_from_file(
          "vergunning.pdf",
          IdentificatieGegevens('34c5-4379-9f1a-5c378', 'Proza (DMS)'),
          isrepresentatievan=verwijzing_obj  # or pass the actual file
     )
     bestand.save("vergunning.bestand.mdto.xml")
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

    checksum = create_checksum(file)

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
        identificatie, naam, omvang, bestandsformaat, checksum, verwijzing_obj, url
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


def create_checksum(
    file_or_filename: TextIO | str, algorithm: str = "sha256"
) -> ChecksumGegevens:
    """Convience function for creating ChecksumGegegevens objects.

    Takes a file-like object or path to file, and then generates the requisite
    checksum metadata (i.e.  `checksumAlgoritme`, `checksumWaarde`, and
    `checksumDatum`) from that file.

    Example:

        ```python
        pdf_checksum = create_checksum('document.pdf')
        # create ChecksumGegevens with a 512 bits instead of a 256 bits checksum
        jpg_checksum = create_checksum('scan-003.jpg', algorithm="sha512")
        ```

    Args:
        infile (TextIO | str): file-like object to generate checksum data for
        algorithm (Optional[str]): checksum algorithm to use; defaults to sha256.
         For valid values, see https://docs.python.org/3/library/hashlib.html

    Returns:
        ChecksumGegevens: checksum metadata from `file_or_filename`
    """
    infile = helpers.process_file(file_or_filename)
    verwijzingBegrippenlijst = VerwijzingGegevens(
        verwijzingNaam="Begrippenlijst ChecksumAlgoritme MDTO"
    )

    # normalize algorithm name; i.e. uppercase it and insert a dash, like the NA
    algorithm_norm = re.sub(r"SHA(\d+)", r"SHA-\1", algorithm.upper())
    checksumAlgoritme = BegripGegevens(
        begripLabel=algorithm_norm, begripBegrippenlijst=verwijzingBegrippenlijst
    )

    # file_digest() expects a file in binary mode, hence `infile.buffer.raw`
    checksumWaarde = hashlib.file_digest(infile.buffer.raw, algorithm).hexdigest()

    checksumDatum = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    return ChecksumGegevens(checksumAlgoritme, checksumWaarde, checksumDatum)
