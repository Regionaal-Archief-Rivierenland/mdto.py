import pytest

import mdto
from mdto.gegevensgroepen import *


def test_gemeentecode_from_gemeentenaam():
    """Test retrieving VerwijzingGegevens object with both TOOI
    gemeentecode and gemaantenaam using just a TOOI gemeentenaam"""
    v = mdto.verwijzing_gegevens_from_tooi_gemeentenaam("GEMEENTE tiel")
    assert v.verwijzingIdentificatie.identificatieKenmerk == "gm0281"
    v = mdto.verwijzing_gegevens_from_tooi_gemeentenaam("amsterdam")
    assert v.verwijzingIdentificatie.identificatieKenmerk == "gm0363"


def test_gemeentenaam_from_gemeentecode():
    """Test retrieving VerwijzingGegevens object with both TOOI
    gemeentecode and gemaantenaam using just a TOOI gemeentecode."""
    v = mdto.verwijzing_gegevens_from_tooi_gemeentecode("0281")
    assert v.verwijzingNaam == "Gemeente Tiel"
    v = mdto.verwijzing_gegevens_from_tooi_gemeentecode("GM0363")
    assert v.verwijzingNaam == "Gemeente Amsterdam"

    with pytest.raises(ValueError, match=r"Invalid gemeentecode '.+'"):
        mdto.verwijzing_gegevens_from_tooi_gemeentecode("348")
