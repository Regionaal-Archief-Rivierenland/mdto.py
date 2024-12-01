import pytest
import lxml.etree as ET
from mdto import (
    Informatieobject,
    IdentificatieGegevens,
    VerwijzingGegevens,
    BeperkingGebruikGegevens,
    BegripGegevens,
)


def test_xml_validity(mdto_xsd):
    """Test if outpt XML is valid according to the MDTO XSD"""
    # create a schema object from the MDTO XSD 
    mdto_schema = ET.XMLSchema(ET.parse(mdto_xsd))
    # create informatieobject
    informatieobject = Informatieobject(
        naam="Verlenen kapvergunning",
        identificatie=IdentificatieGegevens("abcd-1234", "Corsa (Geldermalsen)"),
        archiefvormer=VerwijzingGegevens("Geldermalsen"),
        beperkingGebruik=BeperkingGebruikGegevens(
            BegripGegevens("nvt", VerwijzingGegevens("geen"))
        ),
        waardering=BegripGegevens(
            "V", VerwijzingGegevens("Begrippenlijst Waarderingen MDTO")
        ),
    )

    # lxml is silly, and does not bind namespaces to nodes until _after_ they've been serialized.
    # See: https://stackoverflow.com/questions/22535284/strange-lxml-behavior
    # As a workaround, we serialize the ElemenTree object to a string, and then deserialize this
    # namespaced string. There are other ways to fix this, but their decreased readability does not
    # outweigh mildly complicating this test.
    mdto_xml = ET.fromstring(ET.tostring(informatieobject.to_xml()))

    # validate against schema
    assert mdto_schema.validate(mdto_xml)
