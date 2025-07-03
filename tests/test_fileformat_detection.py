import pytest

from mdto.gegevensgroepen import *
from mdto.utilities import _pronominfo_siegfried, mimetypeinfo


def test_pronom_siegfried(voorbeeld_archiefstuk_xml):
    """Test siegfried-based PRONOM detection"""
    expected = BegripGegevens(
        "Extensible Markup Language", VerwijzingGegevens("PRONOM-register"), "fmt/101"
    )
    got = _pronominfo_siegfried(voorbeeld_archiefstuk_xml)
    assert expected == got


def test_mimetype(voorbeeld_archiefstuk_xml):
    """Test siegfried-based PRONOM detection"""
    expected = BegripGegevens(
        "xml", VerwijzingGegevens("IANA Media types"), "application/xml"
    )
    got = mimetypeinfo(voorbeeld_archiefstuk_xml)
    assert expected == got
