# Public functions

import re
from typing import TextIO

from .gegevensgroepen import *

from . import helpers


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
                IdentificatieGegevens(
                    f"gm{gemeentecode}", "TOOI register gemeenten compleet"
                ),
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
