from pathlib import Path

import lxml.etree as ET
import pytest

import mdto
from mdto.gegevensgroepen import *


def test_informatieobject_xml_validity(mdto_xsd, shared_informatieobject):
    """Test if running to_xml() on a informatieobject procudes valid MDTO XML"""
    # create a schema object from the MDTO XSD
    mdto_schema = ET.XMLSchema(ET.parse(mdto_xsd))

    # lxml is silly, and does not bind namespaces to nodes until _after_ they've been serialized.
    # See: https://stackoverflow.com/questions/22535284/strange-lxml-behavior
    # As a workaround, we serialize the ElemenTree object to a string, and then deserialize this
    # namespaced string. There are other ways to fix this, but their decreased readability does not
    # outweigh mildly complicating this test.
    informatieobject_xml = ET.fromstring(ET.tostring(shared_informatieobject.to_xml()))

    # validate against schema
    # change to assertValid to see more detailed errors
    assert mdto_schema.validate(informatieobject_xml)


def test_automatic_bestand_xml_validity(mdto_xsd, voorbeeld_archiefstuk_xml):
    """Test if running to_xml() on a automatically generated Bestand procudes valid MDTO XML"""
    # create a schema object from the MDTO XSD
    mdto_schema = ET.XMLSchema(ET.parse(mdto_xsd))

    # use this .py file for automatic metadata generation
    example_file = Path(__file__)
    # create Bestand object from example_file + existing informatieobject
    bestand = mdto.bestand_from_file(
        example_file,
        IdentificatieGegevens("abcd-1234", "Corsa"),
        voorbeeld_archiefstuk_xml,
        url="https://example.com/",
    )

    # see comment about lxml above
    bestand_xml = ET.fromstring(ET.tostring(bestand.to_xml()))

    # validate against schema
    assert mdto_schema.validate(bestand_xml)
