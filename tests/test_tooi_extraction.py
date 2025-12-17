import pytest

from mdto.gegevensgroepen import VerwijzingGegevens

def test_gemeentecode_from_gemeentenaam():
    """Test creating a VerwijzingGegevens from just a gemeentenaam"""
    v = VerwijzingGegevens.gemeente("GEMEENTE tiel")
    assert v.verwijzingIdentificatie.identificatieKenmerk == "gm0281"
    v = VerwijzingGegevens.gemeente("amsterdam")
    assert v.verwijzingIdentificatie.identificatieKenmerk == "gm0363"


def test_gemeentenaam_from_gemeentecode():
    """Test creating a VerwijzingGegevens from just a gemeentecode"""
    v = VerwijzingGegevens.gemeente("0281")
    assert v.verwijzingNaam == "Gemeente Tiel"
    v = VerwijzingGegevens.gemeente("GM0363")
    assert v.verwijzingNaam == "Gemeente Amsterdam"

    with pytest.raises(ValueError, match=r"Name or code '.+' not found"):
        VerwijzingGegevens.gemeente("348")
