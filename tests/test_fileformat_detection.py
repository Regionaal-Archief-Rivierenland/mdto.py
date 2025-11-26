import pytest

from mdto.gegevensgroepen import *
from mdto.helpers import pronominfo, mimetypeinfo


def test_pronom_siegfried(voorbeeld_archiefstuk_xml):
    """Test siegfried-based PRONOM detection"""
    expected = BegripGegevens(
        "Extensible Markup Language", VerwijzingGegevens("PRONOM-register"), "fmt/101"
    )
    got = pronominfo(voorbeeld_archiefstuk_xml)
    assert expected == got


def test_mimetype(voorbeeld_archiefstuk_xml):
    """Test mimetype detection"""
    expected = BegripGegevens(
        "xml", VerwijzingGegevens("IANA Media types"), "application/xml"
    )
    got = mimetypeinfo(voorbeeld_archiefstuk_xml)
    # windows favors "text/xml"
    if got.begripCode == "text/xml":
        got.begripCode = "application/xml"

    assert expected == got

# TODO: find out why siegfried won't recognize these
# maybe this should be a little more relaxed; x-python is non-standard
def test_mimetype_py():
    """Test mimetype detection for python files.

    These are esotoric/non-IANA recognized, and thus deserve a seperate test"""
    expected = BegripGegevens(
        "x-python", VerwijzingGegevens("IANA Media types"), "text/x-python"
    )
    got = mimetypeinfo(__file__)

    assert expected == got
