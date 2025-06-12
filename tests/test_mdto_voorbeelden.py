import pytest
import lxml.etree as ET
import mdto
from mdto.gegevensgroepen import Informatieobject, Bestand


def serialization_chain(xmlfile: str) -> str:
    """
    Implements a serialization chain by calling from_xml(), followed by to_xml().

    Args:
        xmlfile (str): the xmlfile to run the chain on

    Returns:
        str: the re-serailized XML, as a string
    """
    # Deserialize
    object = mdto.Object.from_xml(xmlfile)

    # Serialize back to XML
    output_tree = object.to_xml()

    return (
        ET.tostring(
            output_tree.getroot(),
            doctype='<?xml version="1.0" encoding="UTF-8"?>',
            encoding="UTF-8",
        ).decode("UTF-8")
        + "\n"  # MDTO closes with a newline
    )


def test_from_xml_archiefstuk(voorbeeld_archiefstuk_xml):
    """Test that from_xml() correctly parses Voorbeeld Archiefstuk Informatieobject.xml"""
    archiefstuk = Informatieobject.from_xml(voorbeeld_archiefstuk_xml)

    assert isinstance(archiefstuk, Informatieobject)
    assert archiefstuk.naam == "Verlenen kapvergunning Hooigracht 21 Den Haag"


def test_from_xml_dossier(voorbeeld_dossier_xml):
    """Test that from_xml() correctly parses Voorbeeld Dossier Informatieobject.xml"""
    dossier = Informatieobject.from_xml(voorbeeld_dossier_xml)

    assert isinstance(dossier, Informatieobject)
    assert dossier.trefwoord[1] == "kappen"


def test_from_xml_serie(voorbeeld_serie_xml):
    """Test that from_xml() correctly parses Voorbeeld Serie Informatieobject.xml"""
    serie = Informatieobject.from_xml(voorbeeld_serie_xml)

    assert isinstance(serie, Informatieobject)
    assert serie.naam == "Vergunningen van de gemeente 's-Gravenhage vanaf 1980"


def test_from_xml_bestand(voorbeeld_bestand_xml):
    """Test that from_xml() correctly parses Voorbeeld Bestand.xml"""
    bestand = Bestand.from_xml(voorbeeld_bestand_xml)

    assert isinstance(bestand, Bestand)
    assert (
        bestand.isRepresentatieVan.verwijzingNaam
        == "Verlenen kapvergunning Hooigracht 21 Den Haag"
    )


def test_automatic_bestand_generation(voorbeeld_bestand_xml):
    """Test if automatic Bestand XML generation matches Voorbeeld Bestand.xml"""
    # TODO: this needs to read the resource at
    # <URLBestand>https://kia.pleio.nl/file/download/55815288/0090101KapvergunningHoogracht.pdf</URLBestand>
    # but that link is dead (as all other links)
    pass


def test_serialization_chain_informatieobject(voorbeeld_archiefstuk_xml):
    """Test the serialization chain for Informatieobject"""
    output_xml = serialization_chain(voorbeeld_archiefstuk_xml)

    # Read the original file into a string
    with open(voorbeeld_archiefstuk_xml, "r", encoding="utf-8") as f:
        original_xml = f.read()

    # Ensure the serialized XML matches the original
    assert output_xml == original_xml


def test_serialization_chain_bestand(voorbeeld_bestand_xml):
    """Test the serialization chain for Bestand"""
    output_xml = serialization_chain(voorbeeld_bestand_xml)

    # Read the original file into a string
    with open(voorbeeld_bestand_xml, "r", encoding="utf-8") as f:
        original_xml = f.read()

    # Ensure the serialized XML matches the original
    assert output_xml == original_xml


def test_file_saving(voorbeeld_archiefstuk_xml, tmp_path_factory):
    """Test if `save()` produces byte-for-byte equivalent XML from archiefstuk example"""
    # location to write to
    tmpdir = tmp_path_factory.mktemp("Output")
    outfile = tmpdir / "test archiefstuk.xml"

    informatieobject = Informatieobject.from_xml(voorbeeld_archiefstuk_xml)
    informatieobject.save(outfile)

    # MDTO uses CRLF (DOS) line endings. Convert them to UNIX line endings.
    with open(voorbeeld_archiefstuk_xml, "rb") as f:
        # Example files also contain newlines at the end of files, so append an extra \n
        voorbeeld_archiefstuk_xml_lf_endings = b"\n".join(f.read().splitlines()) + b"\n"

    # Read contents of saved file
    with open(outfile, "rb") as f:
        outfile_bytes = f.read()

    # MDTO use double qoutes in the xml declaration, whereas lxml uses single quotes. Both are valid.
    # (couldn't find an easy way to change lxml's behavior here, unfortunately)
    outfile_bytes = outfile_bytes.replace(
        b"<?xml version='1.0' encoding='UTF-8'?>",
        b'<?xml version="1.0" encoding="UTF-8"?>',
    )

    # Ensure the written file matches the original
    assert voorbeeld_archiefstuk_xml_lf_endings == outfile_bytes
