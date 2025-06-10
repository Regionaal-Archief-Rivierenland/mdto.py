# mdto.py

[![unit test badge](https://github.com/Regionaal-Archief-Rivierenland/mdto.py/actions/workflows/pytest.yml/badge.svg)](https://github.com/Regionaal-Archief-Rivierenland/mdto.py/actions)
[![codecov](https://codecov.io/gh/Regionaal-Archief-Rivierenland/mdto.py/graph/badge.svg?token=9VW5IT370J)](https://codecov.io/gh/Regionaal-Archief-Rivierenland/mdto.py)

`mdto.py` is een Python library die helpt bij het aanmaken, aanpassen, en controleren van [MDTO XML](https://www.nationaalarchief.nl/archiveren/mdto/xml-schema) bestanden. Denk bijvoorbeeld aan het automatisch genereren van technische metagegevens, of wat in MDTO het objectsoort [Bestand](https://www.nationaalarchief.nl/archiveren/mdto/metagegevensschema#collapse-102796) wordt genoemd:

``` xml
<MDTO xmlns="https://www.nationaalarchief.nl/mdto" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="https://www.nationaalarchief.nl/mdto https://www.nationaalarchief.nl/mdto/MDTO-XML1.0.1.xsd">
    <bestand>
        <identificatie>
            <identificatieKenmerk>Bestand-345c-4379</identificatieKenmerk>
            <identificatieBron>Corsa</identificatieBron>
        </identificatie>
        <naam>bouwtekening-003.jpg</naam>
        <omvang>1089910</omvang>
        <bestandsformaat>
            <begripLabel>JPEG File Interchange Format</begripLabel>
            <begripCode>fmt/43</begripCode>
            <begripBegrippenlijst>
                <verwijzingNaam>PRONOM-register</verwijzingNaam>
            </begripBegrippenlijst>
        </bestandsformaat>
        <checksum>
            <checksumAlgoritme>
                <begripLabel>SHA-256</begripLabel>
                <begripBegrippenlijst>
                    <verwijzingNaam>Begrippenlijst ChecksumAlgoritme MDTO</verwijzingNaam>
                </begripBegrippenlijst>
            </checksumAlgoritme>
            <checksumWaarde>857ee09fb53f647b16b1f96aba542ace454cd6fc52c9844d4ddb8218c5d61b6c</checksumWaarde>
            <checksumDatum>2024-02-15T16:15:33</checksumDatum>
        </checksum>
        <URLBestand>https://www.example.com/bouwtekening-003.jpg</URLBestand>
        <isRepresentatieVan>
            <verwijzingNaam>Bouwtekening Flipje's erf 27</verwijzingNaam>
            <verwijzingIdentificatie>
                <identificatieKenmerk>Informatieobject-4661a-5a3526</identificatieKenmerk>
                <identificatieBron>Corsa</identificatieBron>
                ...
```

Naast gebruiksvriendelijkheid, streeft `mdto.py` ook een 100% correcte implementatie van het MDTO XML-schema te zijn. Deze correctheid wordt geverifieerd door de output van `mdto.py` met de MDTO XSD en voorbeeldbestanden te vergelijken (zie [tests/](tests/)).

# 💿 Installatie

## Afhankelijkheden

* Python 3.11 of nieuwer

## Systeem-brede installatie

``` shell
git clone https://github.com/Regionaal-Archief-Rivierenland/mdto.py
cd mdto.py
sudo pip install . # Windows gebruikers kunnen "sudo" hier weglaten
```

## Installatie in een virtual environment

<details>
<summary>Windows</summary>

``` shell
git clone https://github.com/Regionaal-Archief-Rivierenland/mdto.py
cd mdto.py
python -m venv mdto_env
mdto_env\Scripts\activate
pip install .
```
</details>

<details>
<summary>Linux/WSL/*nix</summary>

``` shell
git clone https://github.com/Regionaal-Archief-Rivierenland/mdto.py
cd mdto.py/
python -m venv mdto_env
source mdto_env/bin/activate
pip install .
```
</details>

# 📖 `mdto.py` als Python library

## XML bestanden bouwen

De primaire doelstellingen van `mdto.py` is het versimpelen van het bouwen van MDTO XMLs via Python. Om enkele voorbeelden te geven:

``` python
from mdto.gegevensgroepen import *  # importeer VerwijzingGegevens, BegripGegevens, BegripGegevens, etc.

# maak identificatiekenmerk element
informatieobject_id = IdentificatieGegevens("Informatieobject-4661a", "Proza (OCW-DMS)")

# maak waardering element
waardering = BegripGegevens(begripLabel="Tijdelijk te bewaren",
                            begripCode="V",
                            begripBegrippenlijst=VerwijzingGegevens("Begrippenlijst Waarderingen MDTO"))

# maak beperkingGebruik element
# beperkingGebruikType verwacht een begrip label (bijv. 'Auteurswet'), en een verwijzing naar een begrippenlijst
beperkingType = BegripGegevens("Auteurswet", VerwijzingGegevens("Gemeente Den Haag zaaksysteem begrippenlijst"))
beperkingGebruik = BeperkingGebruikGegevens(beperkingGebruikType=beperkingType)

# maak informatieobject op basis van deze gegevens
informatieobject = Informatieobject(identificatie = informatieobject_id,
                 naam = "Verlenen kapvergunning Hooigracht 21 Den Haag",
                 waardering = waardering,
                 archiefvormer = VerwijzingGegevens("'s-Gravenhage"),
                 beperkingGebruik = beperkingGebruik)

# schrijf informatieobject naar een XML bestand
informatieobject.save("informatieobject-4661a.mdto.xml")
```

`mdto.py` zorgt dat al deze informatie in de juiste volgorde in de XML terechtkomt — resulterende bestanden zijn altijd 100% valide MDTO.

In tegenstelling tot Python's ingebouwde XML library [`xml.etree`](https://docs.python.org/3/library/xml.etree.elementtree.html) kun je het bovenstaand `informatieobject` gemakkelijk inspecteren en veranderen, bijvoorbeeld via `print()`:

``` python-console
>>> print(informatieobject)
Informatieobject(naam='Verlenen kapvergunning Hooigracht 21 Den Haag',  identificatie=IdentificatieGegevens(identificatieKenmerk='Informatieobject-4661a, identificatieBron='Proza (OCW-DMS)', ...)
>>> informatieobject.naam = informatieobject.naam.upper() # waardes zijn gemakkelijk aan te passen
>>> print(informatieobject.naam)
'VERLENEN KAPVERGUNNING HOOIGRACHT 21 DEN HAAG'
```

> [!TIP]
> Je kan op een vergelijkbare manier Bestand objecten bouwen via de `Bestand()` class. Het is vaak echter simpeler om hiervoor de _convience_ functie `bestand_from_file()` te gebruiken, omdat deze veel gegevens, zoals PRONOM informatie en checksums, automatisch voor je aanmaakt:
>
> ```python
> import mdto
> from mdto.gegevensgroepen import *
>
> # verwijzing naar bijbehorend informatieobject
> obj_verwijzing = VerwijzingGegevens("Verlenen kapvergunning Hooigracht")
>
> bestand = mdto.bestand_from_file(
>         file="vergunning.pdf",  # bestand waarvoor technische metagegevens moeten worden aangemaakt
>         identificatie=Identificatiegegevens("34c5-4379-9f1a-5c378", "Proza (DMS)"),
>         isrepresentatievan=obj_verwijzing
>      )
>
> # Sla op als XML bestand
> bestand.save("vergunning.bestand.mdto.xml")
> ```
>
> Het opgeslagen XML bestand bevat vervolgens de correcte waardes voor `<omvang>`, `<bestandsformaat>`, `<checksum>` , en `<isRepresentatieVan>`.

## XML bestanden inlezen

`mdto.py` kan ook MDTO bestanden inlezen en naar Python MDTO objecten omzetten via de `from_xml` functie.

Stel bijvoorbeeld dat je alle checksums van Bestand XML bestanden wilt updaten:

``` python
import mdto
from pathlib import Path

# Aangenomen dat je mapstructuur er zo uitziet:
# mdto_collectie/
# ├── Kapvergunning/
# │   ├── 19880405KapvergunningHoogracht.bestand.mdto.xml
# │   ├── 19880405KapvergunningHoogracht.mdto.xml
# │   └── 19880405KapvergunningHoogracht.pdf
# └── Verslag/
#     ├── 19880409Verslag.bestand.mdto.xml
#     ├── 19880409Verslag.mdto.xml
#     └── 19880409Verslag.pdf


# itereer door alle Bestand XMLs:
for bestand_path in Path(".").rglob("*.bestand.mdto.xml"):
    bestand = mdto.from_xml(bestand_path)

    # vind naam + path van het te updaten bestand
    filename = bestand.naam  # in de regel bevat <naam> de bestandsnaam
    filepath = bestand_path.parent / filename

    # maak een nieuwe checksum
    bestand.checksum = mdto.create_checksum(filepath)

    # schrijf geüpdatet Bestand object terug naar de oorspronkelijke XML file
    bestand.save(bestand_path)
```

## Autocompletion & documentatie in je teksteditor/IDE

`mdto.py` bevat docstrings, zodat teksteditors/IDEs je kunnen ondersteunen met documentatie popups en vensters. Handig als je even niet meer wat een MDTO element precies doet.

[doc-popup.webm](https://github.com/Regionaal-Archief-Rivierenland/mdto/assets/10417027/de41c4e5-900d-48c3-b04b-57dc703e201e)

Autocompletition werkt natuurlijk ook:

[autocompletion-cast.webm](https://github.com/Regionaal-Archief-Rivierenland/mdto/assets/10417027/da6ffff7-132e-481c-b3a0-fd1674fd5da7)

<!-- TODO: sectie/link naar het gebruik van mdto.py (of: het toekomstige programma 'bestand') in een commandline omgeving -->
