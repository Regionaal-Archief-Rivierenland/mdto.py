import hashlib
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, TextIO

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
    url: str = None,
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
    bestandsformaat = pronominfo(file.name)
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
            "isrepresentatievan must either be a path/file, or a VerwijzingGegevens object."
        )

    file.close()

    return Bestand(
        identificatie, naam, omvang, bestandsformaat, checksum, verwijzing_obj, url
    )


def verwijzing_gegevens_from_tooi_gemeentenaam(gemeentenaam: str) -> VerwijzingGegevens:
    """Convenience function for creating a reference to a municipality in the TOOI
    register.

    Expects a name from the 'TOOI register gemeente compleet' (e.g. `Tiel` or
    `Gemeente Brielle`), and returns a VerwijzingGegevens object with a
    corresponding code.

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
        f"Municipality with name '{gemeentenaam}' not found in 'TOOI register gemeenten compleet'\n"
        "For a list of possible values, see https://identifier.overheid.nl/tooi/set/rwc_gemeenten_compleet"
    )


def verwijzing_gegevens_from_tooi_gemeentecode(gemeentecode: str) -> VerwijzingGegevens:
    """Convenience function for creating a reference to a municipality in the TOOI
    register.

    Expects a code from the 'TOOI register gemeente compleet' (e.g. `gm0218)`, and
    returns a VerwijzingGegevens object with a corresponding name.

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
        f"Code '{gemeente_code}' not found in 'TOOI register gemeenten compleet'\n"
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


def from_xml(mdto_xml: TextIO | str) -> Informatieobject | Bestand:
    """Construct a Informatieobject/Bestand object from a MDTO XML file.

    Example:

    ```python
    import mdto

    # read informatieobject from file
    informatieobject = mdto.from_xml("Voorbeeld Archiefstuk Informatieobject.xml")

    # edit the informatieobject
    informatieobject.naam = "Verlenen kapvergunning Flipje's Erf 15 Tiel"

    # override the original informatieobject XML
    informatieobject.save("Voorbeeld Archiefstuk Informatieobject.xml")
    ```

    Note:
        The parser will not raise an error when an element is required,
        but missing; childless; or contains out of order children. It
        _will_ error if tags are not potential children of a given
        element.

        This follows Postel's law: we accept malformed MDTO, but only
        send strictly valid MDTO (at least with `.save()`). This
        tolerance affords mdto.py error correction capabilities.

    Raises:
        ValueError: XML violates MDTO schema (though some violations are accepted;
         see above)

    Args:
        mdto_xml (TextIO | str): The MDTO XML file to construct an Informatieobject/Bestand from

    Returns:
        Bestand | Informatieobject: A new MDTO object
    """

    # Parsers:
    def parse_text(node) -> str:
        return node.text

    def parse_int(node) -> int:
        return int(node.text)

    def parse_identificatie(node) -> IdentificatieGegevens:
        return IdentificatieGegevens(
            node[0].text,
            node[1].text,
        )

    # FIXME: return value
    def elem_to_mdto(elem: ET.Element, mdto_class: classmethod, mdto_xml_parsers: dict):
        """Initialize MDTO class (TermijnGegevens, EventGegevens, etc.) with values
        from a given XML node, using parsers specified in `mdto_xml_parsers`.

        Returns:
            MDTO instance: a initialized MDTO instance of `mdto_class`
        """
        # initialize dictionary of keyword arguments (to be passed to MDTO class constructor)
        constructor_args = {mdto_field: [] for mdto_field in mdto_xml_parsers}

        for child in elem:
            mdto_field = child.tag.removeprefix(
                "{https://www.nationaalarchief.nl/mdto}"
            )
            # retrieve correct parser
            xml_parser = mdto_xml_parsers[mdto_field]
            # add value of parsed child element to class constructor args
            constructor_args[mdto_field].append(xml_parser(child))

        # cleanup class constructor arguments
        for argname, value in constructor_args.items():
            # Replace empty argument lists by None
            if len(value) == 0:
                constructor_args[argname] = None
            # Replace one-itemed argument lists by their respective item
            elif len(value) == 1:
                constructor_args[argname] = value[0]

        return mdto_class(**constructor_args)

    verwijzing_parsers = {
        "verwijzingNaam": parse_text,
        "verwijzingIdentificatie": parse_identificatie,
    }
    parse_verwijzing = lambda e: elem_to_mdto(e, VerwijzingGegevens, verwijzing_parsers)

    begrip_parsers = {
        "begripLabel": parse_text,
        "begripCode": parse_text,
        "begripBegrippenlijst": parse_verwijzing,
    }
    parse_begrip = lambda e: elem_to_mdto(e, BegripGegevens, begrip_parsers)

    termijn_parsers = {
        "termijnTriggerStartLooptijd": parse_begrip,
        "termijnStartdatumLooptijd": parse_text,
        "termijnLooptijd": parse_text,
        "termijnEinddatum": parse_text,
    }
    parse_termijn = lambda e: elem_to_mdto(e, TermijnGegevens, termijn_parsers)

    beperking_parsers = {
        "beperkingGebruikType": parse_begrip,
        "beperkingGebruikNadereBeschrijving": parse_text,
        "beperkingGebruikDocumentatie": parse_verwijzing,
        "beperkingGebruikTermijn": parse_termijn,
    }
    parse_beperking = lambda e: elem_to_mdto(
        e, BeperkingGebruikGegevens, beperking_parsers
    )

    raadpleeglocatie_parsers = {
        "raadpleeglocatieFysiek": parse_verwijzing,
        "raadpleeglocatieOnline": parse_text,
    }
    parse_raadpleeglocatie = lambda e: elem_to_mdto(
        e, RaadpleeglocatieGegevens, raadpleeglocatie_parsers
    )

    dekking_in_tijd_parsers = {
        "dekkingInTijdType": parse_begrip,
        "dekkingInTijdBegindatum": parse_text,
        "dekkingInTijdEinddatum": parse_text,
    }
    parse_dekking_in_tijd = lambda e: elem_to_mdto(
        e, DekkingInTijdGegevens, dekking_in_tijd_parsers
    )

    event_parsers = {
        "eventType": parse_begrip,
        "eventTijd": parse_text,
        "eventVerantwoordelijkeActor": parse_verwijzing,
        "eventResultaat": parse_text,
    }
    parse_event = lambda e: elem_to_mdto(e, EventGegevens, event_parsers)

    gerelateerd_informatieobject_parsers = {
        "gerelateerdInformatieobjectVerwijzing": parse_verwijzing,
        "gerelateerdInformatieobjectTypeRelatie": parse_begrip,
    }
    parse_gerelateerd_informatieobject = lambda e: elem_to_mdto(
        e, GerelateerdInformatieobjectGegevens, gerelateerd_informatieobject_parsers
    )

    betrokkene_parsers = {
        "betrokkeneTypeRelatie": parse_begrip,
        "betrokkeneActor": parse_verwijzing,
    }
    parse_betrokkene = lambda e: elem_to_mdto(e, BetrokkeneGegevens, betrokkene_parsers)

    checksum_parsers = {
        "checksumAlgoritme": parse_begrip,
        "checksumWaarde": parse_text,
        "checksumDatum": parse_text,
    }
    parse_checksum = lambda e: elem_to_mdto(e, ChecksumGegevens, checksum_parsers)

    informatieobject_parsers = {
        "naam": parse_text,
        "identificatie": parse_identificatie,
        "aggregatieniveau": parse_begrip,
        "classificatie": parse_begrip,
        "trefwoord": parse_text,
        "omschrijving": parse_text,
        "raadpleeglocatie": parse_raadpleeglocatie,
        "dekkingInTijd": parse_dekking_in_tijd,
        "dekkingInRuimte": parse_verwijzing,
        "taal": parse_text,
        "event": parse_event,
        "waardering": parse_begrip,
        "bewaartermijn": parse_termijn,
        "informatiecategorie": parse_begrip,
        "isOnderdeelVan": parse_verwijzing,
        "bevatOnderdeel": parse_verwijzing,
        "heeftRepresentatie": parse_verwijzing,
        "aanvullendeMetagegevens": parse_verwijzing,
        "gerelateerdInformatieobject": parse_gerelateerd_informatieobject,
        "archiefvormer": parse_verwijzing,
        "betrokkene": parse_betrokkene,
        "activiteit": parse_verwijzing,
        "beperkingGebruik": parse_beperking,
    }
    parse_informatieobject = lambda e: elem_to_mdto(
        e, Informatieobject, informatieobject_parsers
    )

    bestand_parsers = {
        "naam": parse_text,
        "identificatie": parse_identificatie,
        "omvang": parse_int,
        "checksum": parse_checksum,
        "bestandsformaat": parse_begrip,
        "URLBestand": parse_text,
        "isRepresentatieVan": parse_verwijzing,
    }
    parse_bestand = lambda e: elem_to_mdto(e, Bestand, bestand_parsers)

    # read xmlfile
    tree = ET.parse(mdto_xml)
    root = tree.getroot()
    children = list(root[0])

    # check if object type is Bestand or Informatieobject
    object_type = root[0].tag.removeprefix("{https://www.nationaalarchief.nl/mdto}")

    if object_type == "informatieobject":
        return parse_informatieobject(children)
    elif object_type == "bestand":
        return parse_bestand(children)
    else:
        raise ValueError(
            f"Unexpected first child <{object_type}> in {mdto_xml}: "
            "expected <informatieobject> or <bestand>."
        )
