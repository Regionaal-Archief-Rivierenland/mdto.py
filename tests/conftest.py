import zipfile
from io import BytesIO
from pathlib import Path

import pytest
import requests

from mdto.gegevensgroepen import *

xsd_filename = "MDTO-XML1.0.1.xsd"
xsd_url = f"https://www.nationaalarchief.nl/mdto/{xsd_filename}"
xml_url = "https://www.nationaalarchief.nl/sites/default/files/field-file/MDTO-XML%201.0.1%20Voorbeelden%20%283%29.zip"

# list of example files in the zip file
prefix = "MDTO-XML 1.0.1 Voorbeeld "
xml_voorbeelden = [
    f"{prefix}Archiefstuk Informatieobject.xml",
    f"{prefix}Dossier Informatieobject.xml",
    f"{prefix}Serie Informatieobject.xml",
    f"{prefix}Bestand.xml",
]


def download_mdto_voorbeelden(target_dir):
    """Downloads the MDTO example files, and extracts the zip to `target_dir`"""
    response = requests.get(xml_url)
    response.raise_for_status()  # raise error if download failed

    # unpack zip file
    with zipfile.ZipFile(BytesIO(response.content)) as zip_ref:
        zip_ref.extractall(target_dir)


def download_mdto_xsd(target_dir):
    """Download MDTO XSD to `target_dir`"""
    response = requests.get(xsd_url)
    response.raise_for_status()  # raise error if download failed

    # should be response.text and open(file, "w"), but NA is sending incorrect header information
    with open(target_dir / xsd_filename, "wb") as f:
        f.write(response.content)


@pytest.fixture
def mdto_example_files(pytestconfig, tmp_path_factory) -> dict:
    """Make (cached) MDTO example files available as a fixture"""

    # retrieve path to cached MDTO XML examples
    cache_path = pytestconfig.cache.get("voorbeelden/cache_path", None)
    # check if cached files exists
    if cache_path is None or not all(
        (Path(cache_path) / xml_file).exists() for xml_file in xml_voorbeelden
    ):
        # download MDTO XML examples to tmpdir
        cache_path = tmp_path_factory.mktemp("MDTO Voorbeeld Bestanden")
        download_mdto_voorbeelden(cache_path)
        # store new location in pytest cache
        pytestconfig.cache.set("voorbeelden/cache_path", str(cache_path))

    # cast str to Path
    cache_path = Path(cache_path)
    # create {filename : file_path} dict
    xml_file_paths = {
        xml_file.removeprefix(prefix): cache_path / xml_file
        for xml_file in xml_voorbeelden
        if (cache_path / xml_file).exists()
    }

    return xml_file_paths


@pytest.fixture
def mdto_xsd(pytestconfig, tmp_path_factory) -> Path:
    """Make (cached) MDTO XSD available as a fixture"""

    # retrieve path to cached XSD
    cache_path = pytestconfig.cache.get("xsd/cache_path", None)

    # check if cached XSD exists
    if cache_path is None or not (Path(cache_path) / xsd_filename).exists():
        # download MDTO XSD examples to tmpdir
        cache_path = tmp_path_factory.mktemp("MDTO XSD")
        download_mdto_xsd(cache_path)
        # store new location in pytest cache
        pytestconfig.cache.set("xsd/cache_path", str(cache_path))

    return str(Path(cache_path) / xsd_filename)


@pytest.fixture
def voorbeeld_archiefstuk_xml(mdto_example_files):
    return mdto_example_files["Archiefstuk Informatieobject.xml"]


@pytest.fixture
def voorbeeld_dossier_xml(mdto_example_files):
    return mdto_example_files["Dossier Informatieobject.xml"]


@pytest.fixture
def voorbeeld_serie_xml(mdto_example_files):
    return mdto_example_files["Serie Informatieobject.xml"]


@pytest.fixture
def voorbeeld_bestand_xml(mdto_example_files):
    return mdto_example_files["Bestand.xml"]


@pytest.fixture
def shared_informatieobject():
    """A basic pre-constructed informatieobject"""
    return Informatieobject(
        naam="Verlenen kapvergunning",
        identificatie=IdentificatieGegevens("abcd-1234", "Corsa (Geldermalsen)"),
        archiefvormer=VerwijzingGegevens("Geldermalsen"),
        beperkingGebruik=BeperkingGebruikGegevens(
            BegripGegevens("nvt", VerwijzingGegevens("geen"))
        ),
        waardering=BegripGegevens(
            "V", VerwijzingGegevens("Begrippenlijst Waarderingen MDTO")
        ),
        # These elements are added to increase test coverge
        aanvullendeMetagegevens=VerwijzingGegevens("technische_beschieden.imro.xml"),
        gerelateerdInformatieobject=GerelateerdInformatieobjectGegevens(
            VerwijzingGegevens("Bestemmingsplan Hooigracht"),
            BegripGegevens(
                "Refereert aan",
                VerwijzingGegevens(
                    "Begrippenlijst Relatietypen (informatieobject) MDTO"
                ),
            ),
        ),
    )
