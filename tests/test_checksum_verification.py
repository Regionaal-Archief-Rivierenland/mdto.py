import pytest

from mdto.gegevensgroepen import Bestand, ChecksumGegevens
from pathlib import Path

def test_checksum_verification(voorbeeld_bestand_xml, voorbeeld_pdf_file):
    """Test checksum verification."""
    # pdf and bestand XML don't live in the same folder by default
    new_pdf_loc = voorbeeld_bestand_xml.parent / voorbeeld_pdf_file.name
    if not new_pdf_loc.exists(follow_symlinks=False):
        new_pdf_loc.symlink_to(voorbeeld_pdf_file)

    bestand = Bestand.open(voorbeeld_bestand_xml)
    assert bestand.verify_checksum()
    bestand.checksum.checksumWaarde = "incorrect value"
    assert not bestand.verify_checksum()
    
    
