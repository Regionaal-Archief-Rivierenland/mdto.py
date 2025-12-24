import lxml.etree as ET
import pytest

from mdto.gegevensgroepen import *


def test_remove_empty_nodes():
    """Test removal of nested empty elements"""
    nested_empty = VerwijzingGegevens("", IdentificatieGegevens('', ''))
    # arguebly this to_xml call should return None but if you do
    # something like `if child := val.to_xml(tag_name)` lxml will
    # complain about Truth-testing and needinig to use len()
    assert ET.tostring(nested_empty.to_xml('_')) == b"<_/>"


def test_out_of_order_tolerance(voorbeeld_archiefstuk_xml):
    """Test parser tolerance on out of order elements"""
    tree = ET.parse(voorbeeld_archiefstuk_xml)
    root = tree.getroot()
    children = list(root[0])
    # swap first and second elem
    children[0], children[1] = children[1], children[0]

    archiefstuk = Informatieobject._from_elem(children)
    assert archiefstuk.naam == "Atelier Kustkwaliteit, 2011. Ontwerpstudie Dwarsdoorsneden kust, vier Kustdoorsneden in beeld, Werkboek 2, Delft."

def test_missing_but_required_tolerance(voorbeeld_archiefstuk_xml):
    """Test parser tolerance for missing but required elements"""
    tree = ET.parse(voorbeeld_archiefstuk_xml)
    root = tree.getroot()
    children = list(root[0])
    # delete naam
    del children[1]

    archiefstuk = Informatieobject._from_elem(children)
    assert archiefstuk.naam is None
    assert archiefstuk.taal == "nl"
