import lxml.etree as ET
import pytest

from mdto.gegevensgroepen import *


def test_out_of_order_tolerance(voorbeeld_archiefstuk_xml):
    """Test parser tolerance on out of order elements"""
    tree = ET.parse(voorbeeld_archiefstuk_xml)
    root = tree.getroot()
    children = list(root[0])
    # swap first and second elem
    children[0], children[1] = children[1], children[0]

    archiefstuk = Informatieobject._from_elem(children)
    assert archiefstuk.naam == "Verlenen kapvergunning Hooigracht 21 Den Haag"

def test_missing_but_required_tolerance(voorbeeld_archiefstuk_xml):
    """Test parser tolerance for missing but required elements"""
    tree = ET.parse(voorbeeld_archiefstuk_xml)
    root = tree.getroot()
    children = list(root[0])
    # delete naam
    del children[0]

    archiefstuk = Informatieobject._from_elem(children)
    assert archiefstuk.taal == "nl"
