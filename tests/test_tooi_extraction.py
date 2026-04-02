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
        VerwijzingGegevens.gemeente("_")

def test_provinciecode_from_provincienaam():
    """Test creating a VerwijzingGegevens from just a provincienaam"""
    v = VerwijzingGegevens.provincie("PROVINCIE noord-holland")
    assert v.verwijzingIdentificatie.identificatieKenmerk == "pv27"
    v = VerwijzingGegevens.provincie("zeeland")
    assert v.verwijzingIdentificatie.identificatieKenmerk == "pv29"

def test_provincienaam_from_provinciecode():
    """Test creating a VerwijzingGegevens from just a provinciecode"""
    v = VerwijzingGegevens.provincie("27")
    assert v.verwijzingNaam == "Provincie Noord-Holland"
    v = VerwijzingGegevens.provincie("PV29")
    assert v.verwijzingNaam == "Provincie Zeeland"

    with pytest.raises(ValueError, match=r"Name or code '.+' not found"):
        VerwijzingGegevens.provincie("348")

def test_waterschapcode_from_waterschapsnaam():
    """Test creating a VerwijzingGegevens from just a waterschapsnaam"""
    v = VerwijzingGegevens.waterschap("WATERSCHAP hoogheemraadschap van schieland en de krimpenerwaard")
    assert v.verwijzingIdentificatie.identificatieKenmerk == "ws0656"
    v = VerwijzingGegevens.waterschap("veluwe")
    assert v.verwijzingIdentificatie.identificatieKenmerk == "ws0153"

def test_waterschapsnaam_from_waterschapcode():
    """Test creating a VerwijzingGegevens from just a waterschapcode"""
    v = VerwijzingGegevens.waterschap("0656")
    assert v.verwijzingNaam == "Waterschap Hoogheemraadschap van Schieland en de Krimpenerwaard"
    v = VerwijzingGegevens.waterschap("ws0153")
    assert v.verwijzingNaam == "Waterschap Veluwe"

    with pytest.raises(ValueError, match=r"Name or code '.+' not found"):
        VerwijzingGegevens.waterschap("348785476756")

