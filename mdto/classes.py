import dataclasses
from dataclasses import dataclass
from typing import Any, List, TextIO, Union, get_args, get_origin

import lxml.etree as ET

# allow running directly from interpreter
try:
    from . import helpers
except ImportError:
    import helpers

# globals
MDTO_MAX_NAAM_LENGTH = 80


class ValidationError(TypeError):
    """Custom formatter for MDTO validation errors"""

    def __init__(self, field_path: List[str], msg: str):
        super().__init__(f"{'.'.join(field_path)}:\n\t{msg}")
        self.field_path = field_path
        self.msg = msg


# TODO: update name and docstring to be more descriptive? Now, this class does more than just serialize
# or maybe refactor?
class Serializable:
    """Provides is_valid() and to_xml() methods for converting MDTO dataclasses
    to valid MDTO XML."""

    def validate(self) -> None:
        """Validate the object's fields against the MDTO schema. Additional
        validation logic can be incorporated by extending this method in a
        subclass.

        Note:
           Typing information is infered based on type hints.

        Raises:
            ValidationError: field violates typing constraints of MDTO schema
        """
        for field in dataclasses.fields(self):
            field_name = field.name
            field_value = getattr(self, field_name)
            field_type = field.type
            optional_field = field.default is None

            cls_name = self.__class__.__name__
            _ValidationError = (
                lambda m: ValidationError([cls_name, field_name], m)
                if cls_name in ["Informatieobject", "Bestand"]
                else ValidationError([field_name], m)
            )

            # optional fields may be None
            if optional_field and field_value is None:
                continue

            # check if field is listable based on type hint
            if get_origin(field_type) is Union:
                expected_type = get_args(field_type)[0]
                listable = True
            else:
                expected_type = field_type
                listable = False

            if isinstance(field_value, (list, tuple, set)):
                if not listable:
                    raise _ValidationError(
                        f"got type {type(field_value).__name__}, but field does not accept sequences"
                    )

                if not all(isinstance(item, expected_type) for item in field_value):
                    raise _ValidationError(
                        f"list items must be {expected_type.__name__}, "
                        f"but found {', '.join(set(type(i).__name__ for i in field_value))}"
                    )
            elif not isinstance(field_value, expected_type):
                raise _ValidationError(
                    f"expected type {expected_type.__name__}, got {type(field_value).__name__}"
                )
            elif isinstance(field_value, Serializable):
                # catch errors recursively to reconstruct full field path in error message
                try:
                    field_value.validate()
                except ValidationError as deeper_error:
                    path = (
                        [cls_name, field_name]
                        if cls_name in ["Informatieobject", "Bestand"]
                        else [field_name]
                    )
                    raise ValidationError(
                        path + deeper_error.field_path,
                        deeper_error.msg,
                    ) from None  # Suppress the original traceback
            else:
                # primitive singleton
                # empty lists, empty strings, etc. are not allowed.
                # (We're actually a little stricter than MDTO on this point)
                # None is allowed, but only for optional elements (see above)
                if field_value is None or len(str(field_value)) == 0:
                    raise _ValidationError("field value must not be empty or None")

    def _mdto_ordered_fields(self) -> List:
        """Sort dataclass fields by their order in the MDTO XSD.

        This method should be overridden when the order of fields in
        a dataclass does not match the order required by the MDTO XSD.

        Such mismatches occur because Python only allows optional arguments
        at the _end_ of a function's signature, while schemas such as the
        MDTO XSD allow optional attributes to appear anywhere.
        """
        return dataclasses.fields(self)

    def to_xml(self, root: str) -> ET.Element:
        """Serialize MDTO gegevensgroep to XML tree.

        Args:
            root (str): name of the new root tag

        Returns:
            ET.Element: XML representation of object with new root tag
        """
        root_elem = ET.Element(root)
        # get dataclass fields, but in the order required by the MDTO XSD
        fields = self._mdto_ordered_fields()

        # process all fields in dataclass
        for field in fields:
            field_name = field.name
            field_value = getattr(self, field_name)
            # serialize field name and value, and add result to root element
            self._process_dataclass_field(root_elem, field_name, field_value)

        # return the tree
        return root_elem

    def _process_dataclass_field(
        self, root_elem: ET.Element, field_name: str, field_value: Any
    ):
        """Recursively process a dataclass field, and append its XML
        representation to `root_elem`."""

        # skip empty fields
        if field_value is None:
            return

        # convert field_value to an iterable (if not already)
        if not isinstance(field_value, (list, tuple, set)):
            field_value = (field_value,)

        # serialize sequence of primitives or *Gegevens objects
        for val in field_value:
            if isinstance(val, Serializable):
                root_elem.append(val.to_xml(field_name))
            else:
                new_sub_elem = ET.SubElement(root_elem, field_name)
                new_sub_elem.text = str(val)

    @classmethod
    def _from_elem(cls, elem: ET.Element):
        """Private helper method stub.

        Is used internally in from_xml to construct a gegevensgroep from a ET.Element.
        This stub implementation is dynamically implemented at runtime.
        """
        pass


@dataclass
class IdentificatieGegevens(Serializable):
    """https://www.nationaalarchief.nl/archiveren/mdto/identificatieGegevens

    Args:
        identificatieKenmerk (str): Een kenmerk waarmee een object geïdentificeerd kan worden
        identificatieBron (str): Herkomst van het kenmerk
    """

    identificatieKenmerk: str
    identificatieBron: str


@dataclass
class VerwijzingGegevens(Serializable):
    """https://www.nationaalarchief.nl/archiveren/mdto/verwijzingsGegevens

    Args:
        verwijzingNaam (str): Naam van het object waarnaar verwezen wordt
        verwijzingIdentificatie (Optional[IdentificatieGegevens]): Identificatie van object waarnaar verwezen wordt
    """

    verwijzingNaam: str
    verwijzingIdentificatie: IdentificatieGegevens = None

    def validate(self):
        """Warn about long names."""
        super().validate()
        if len(self.verwijzingNaam) > MDTO_MAX_NAAM_LENGTH:
            helpers.logging.warning(
                f"VerwijzingGegevens.verwijzingNaam: {self.verwijzingNaam} exceeds recommended length of {MDTO_MAX_NAAM_LENGTH}"
            )


@dataclass
class BegripGegevens(Serializable):
    """https://www.nationaalarchief.nl/archiveren/mdto/begripGegevens

    Args:
        begripLabel (str): De tekstweergave van het begrip
        begripBegrippenlijst (VerwijzingGegevens): Verwijzing naar een beschrijving van de begrippen
        begripCode (Optional[str]): De code die aan het begrip is toegekend
    """

    begripLabel: str
    begripBegrippenlijst: VerwijzingGegevens
    begripCode: str = None

    def _mdto_ordered_fields(self) -> List:
        """Sort dataclass fields by their order in the MDTO XSD."""
        fields = super()._mdto_ordered_fields()
        # swap order of begripBegrippenlijst and begripCode
        return fields[:-2] + (fields[2], fields[1])


@dataclass
class TermijnGegevens(Serializable):
    """https://www.nationaalarchief.nl/archiveren/mdto/termijnGegevens

    Args:
        termijnTriggerStartLooptijd (Optional[BegripGegevens]): Gebeurtenis waarna de looptijd van de termijn start
        termijnStartdatumLooptijd (Optional[str]): Datum waarop de looptijd is gestart
        termijnLooptijd (Optional[str]): Hoeveelheid tijd waarin de termijnEindDatum bereikt wordt
        termijnEinddatum (Optional[str]): Datum waarop de termijn eindigt
    """

    termijnTriggerStartLooptijd: BegripGegevens = None
    termijnStartdatumLooptijd: str = None
    termijnLooptijd: str = None
    termijnEinddatum: str = None


@dataclass
class ChecksumGegevens(Serializable):
    """https://www.nationaalarchief.nl/archiveren/mdto/checksum

    Note:
        When building Bestand objects, it's recommended to call the convience
        function `bestand_from_file()` instead.  And if you just need to update
        a Bestand object's checksum, you should use `create_checksum()`.
    """

    checksumAlgoritme: BegripGegevens
    checksumWaarde: str
    checksumDatum: str


@dataclass
class BeperkingGebruikGegevens(Serializable):
    """https://www.nationaalarchief.nl/archiveren/mdto/beperkingGebruik

    Args:
        beperkingGebruikType (BegripGegevens): Typering van de beperking
        beperkingGebruikNadereBeschrijving (Optional[str]): Beschrijving van de beperking
        beperkingGebruikDocumentatie (Optional[VerwijzingGegevens]): Verwijzing naar een tekstdocument met
            daarin een beschrijving van de beperking
        beperkingGebruikTermijn (Optional[TermijnGegevens]): Termijn waarbinnen de beperking van toepassing is
    """

    beperkingGebruikType: BegripGegevens
    beperkingGebruikNadereBeschrijving: str = None
    beperkingGebruikDocumentatie: VerwijzingGegevens | List[VerwijzingGegevens] = None
    beperkingGebruikTermijn: TermijnGegevens = None


@dataclass
class DekkingInTijdGegevens(Serializable):
    """https://www.nationaalarchief.nl/archiveren/mdto/dekkingInTijd

    Args:
        dekkingInTijdType (BegripGegevens): Typering van de periode waar het informatieobject betrekking op heeft
        dekkingInTijdBegindatum (str): Begindatum van de periode waar het informatieobject betrekking op heeft
        dekkingInTijdEinddatum (Optional[str]): Einddatum van de periode waar het informatieobject betrekking op heeft
    """

    dekkingInTijdType: BegripGegevens
    dekkingInTijdBegindatum: str
    dekkingInTijdEinddatum: str = None

    def validate(self) -> None:
        super().validate()

        supported_formats = "\n".join(
            f"\t\t• {fmt}" for fmt, _ in helpers.date_fmts
        )
        _ValidationError = lambda date, field: ValidationError(
            ["informatieobject", "dekkingInTijd", field],
            f"Date '{date}' is incorrectly formatted or non-existant; {field} supports:\n\n"
            f"{supported_formats}\n\n"
            "\tEach format may include timezone info, e.g. '+01:00' or 'Z'"
        )

        if not helpers.valid_mdto_date(self.dekkingInTijdBegindatum):
            raise _ValidationError(self.dekkingInTijdBegindatum, "dekkingInTijdBegindatum")

        if self.dekkingInTijdEinddatum and not helpers.valid_mdto_date(self.dekkingInTijdEinddatum):
            raise _ValidationError(self.dekkingInTijdEinddatum, "dekkingInTijdEinddatum")

@dataclass
class EventGegevens(Serializable):
    """https://www.nationaalarchief.nl/archiveren/mdto/event

    Args:
        eventType (BegripGegevens): Aanduiding van het type event
        eventTijd (Optional[str]): Tijdstip waarop het event heeft plaatsgevonden
        eventVerantwoordelijkeActor (Optional[VerwijzingGegevens]): Actor die verantwoordelijk was voor het event
        eventResultaat (Optional[str]): Beschrijving van het resultaat van het event
    """

    eventType: BegripGegevens
    eventTijd: str = None
    eventVerantwoordelijkeActor: VerwijzingGegevens = None
    eventResultaat: str = None

    def validate(self) -> None:
        super().validate()
        if self.eventTijd and not helpers.valid_mdto_datetime(self.eventTijd):
            # FIXME: I guess that the proper path may not always include a informatieobject
            supported_formats = "\n".join(
                f"\t\t• {fmt}" for fmt, _ in helpers.datetime_fmts
            )
            raise ValidationError(
                [
                    "informatieobject",
                    "event",
                    "eventTijd",
                ],
                f"Datetime '{self.eventTijd}' is incorrectly formatted or non-existant; eventTijd supports:\n\n"
                f"{supported_formats}\n\n"
                "\tEach format may include timezone info, e.g. '+01:00' or 'Z'"
            )


@dataclass
class RaadpleeglocatieGegevens(Serializable):
    """https://www.nationaalarchief.nl/archiveren/mdto/raadpleeglocatie

    Args:
        raadpleeglocatieFysiek (Optional[VerwijzingGegevens])): Fysieke raadpleeglocatie van het informatieobject
        raadpleeglocatieOnline (Optional[str]): Online raadpleeglocatie van het informatieobject; moet een valide URL zijn
    """

    raadpleeglocatieFysiek: VerwijzingGegevens | List[VerwijzingGegevens] = None
    raadpleeglocatieOnline: str | List[str] = None

    def validate(self) -> None:
        """Check if raadpleeglocatieOnline is a RFC 3986 compliant URI."""
        super().validate()
        if not helpers.validate_url_or_urls(self.raadpleeglocatieOnline):
            raise ValidationError(
                # FIXME: maybe this path should be generated on the fly?
                [
                    "informatieobject",
                    "raadpleeglocatie",
                    "raadpleeglocatieOnline",
                ],
                f"url {self.raadpleeglocatieOnline} is malformed",
            )


@dataclass
class GerelateerdInformatieobjectGegevens(Serializable):
    """https://www.nationaalarchief.nl/archiveren/mdto/gerelateerdInformatieobjectGegevens

    Args:
        gerelateerdInformatieobjectVerwijzing (VerwijzingGegevens): Verwijzing naar het gerelateerde informatieobject
        gerelateerdInformatieobjectTypeRelatie (BegripGegevens): Typering van de relatie
    """

    gerelateerdInformatieobjectVerwijzing: VerwijzingGegevens
    gerelateerdInformatieobjectTypeRelatie: BegripGegevens


@dataclass
class BetrokkeneGegevens(Serializable):
    """https://www.nationaalarchief.nl/archiveren/mdto/betrokkeneGegevens

    Args:
        betrokkeneTypeRelatie (BegripGegevens): Typering van de betrokkenheid van de actor bij het informatieobject
        betrokkeneActor (VerwijzingGegevens): Persoon of organisatie die betrokken is bij het informatieobject
    """

    betrokkeneTypeRelatie: BegripGegevens
    betrokkeneActor: VerwijzingGegevens


# TODO: document constructing from the Object class directly?
@dataclass
class Object(Serializable):
    """https://www.nationaalarchief.nl/archiveren/mdto/object

    This class serves as the parent class to Informatieobject and
    Bestand. There is no reason to use it directly.

    MDTO objects that derive from this class inherit a from_xml() and
    save() method, which can be used to read/write these objects
    to/from XML files.
    """

    identificatie: IdentificatieGegevens | List[IdentificatieGegevens]
    naam: str

    def __post_init__(self):
        # adds possibility to associate MDTO objects with files
        self._file: str | None = None

    def to_xml(self, root: str) -> ET.ElementTree:
        """Transform Object into an XML tree with the following structure:

        ```xml
        <MDTO xmlns=…>
            <root> <!-- e.g. bestand -->
                …
            </root>
        </MDTO>
        ```
        Returns:
            ET.ElementTree: XML tree representing the Object
        """

        # construct attributes of <MDTO>
        xsi_ns = "http://www.w3.org/2001/XMLSchema-instance"
        nsmap = {
            None: "https://www.nationaalarchief.nl/mdto",  # default namespace (i.e. xmlns=https...)
            "xsi": xsi_ns,
        }

        # create <MDTO>
        mdto = ET.Element("MDTO", nsmap=nsmap)

        # set schemaLocation attribute of <MDTO>
        mdto.set(
            f"{{{xsi_ns}}}schemaLocation",
            "https://www.nationaalarchief.nl/mdto https://www.nationaalarchief.nl/mdto/MDTO-XML1.0.1.xsd",
        )

        # convert all dataclass fields to their XML representation
        children = super().to_xml(root)
        mdto.append(children)

        tree = ET.ElementTree(mdto)
        # use tabs as indentation (this matches what MDTO does)
        ET.indent(tree, space="\t")
        return tree

    def validate(self):
        """Warn about long names."""
        super().validate()
        if len(self.naam) > MDTO_MAX_NAAM_LENGTH:
            helpers.logging.warning(
                f"{self.__class__.__name__}.naam: {self.naam} exceeds recommended length of {MDTO_MAX_NAAM_LENGTH}"
            )

    def save(
        self,
        file_or_filename: str | TextIO,
        lxml_args: dict = {
            "xml_declaration": True,
            "pretty_print": True,
            "encoding": "UTF-8",
        },
    ) -> None:
        """Save object to an XML file, provided it satifies the MDTO schema.

        Args:
            file_or_filename (str | TextIO): Path or file-like object to write object's XML representation to
            lxml_args (Optional[dict]): Extra keyword arguments to pass to lxml's write() method.
              Defaults to `{xml_declaration=True, pretty_print=True, encoding="UTF-8"}`.

        Note:
            For a complete list of options for lxml's write method, see
            https://lxml.de/apidoc/lxml.etree.html#lxml.etree._ElementTree.write

        Raises:
            ValidationError: Raised when the object voilates the MDTO schema
        """
        # lxml wants files in binary mode, so pass along a file's raw byte stream
        if hasattr(file_or_filename, "write"):
            file_or_filename = file_or_filename.buffer.raw

        # validate before serialization to ensure correctness
        # (doing this in to_xml would be slow, and perhaps unexpected)
        self.validate()

        xml = self.to_xml()
        xml.write(file_or_filename, **lxml_args)

    @classmethod
    def from_xml(cls, mdto_xml: TextIO | str):
        """Construct a Informatieobject/Bestand object from a MDTO XML file.

        Example:

        ```python
        # read informatieobject from file
        archiefstuk = Informatieobject.from_xml("Voorbeeld Archiefstuk Informatieobject.xml")

        # edit the informatieobject
        archiefstuk.naam = "Verlenen kapvergunning Flipje's Erf 15 Tiel"

        # override the original informatieobject XML
        archiefstuk.save("Voorbeeld Archiefstuk Informatieobject.xml")
        ```

        Note:
            The parser tolerates some schema violations. Specfically, it will
            _not_ error if elements are out of order, or if a required
            element is missing. It _will_ error if tags are not potential
            children of a given element.

            This follows Postel's law: we accept invalid MDTO, but only
            "send" strictly valid MDTO (at least with `.save()`). This
            tolerance allows mdto.py to modify and correct invalid files.

        Raises:
            ValueError, KeyError: XML violates MDTO schema (though some
             violations are tolerated; see above)

        Args:
            mdto_xml (TextIO | str): The MDTO XML file to construct a Bestand/Informatieobject from.
             The path to this file is stored in instances' `._file` attribute for future reference.

        Returns:
            Bestand | Informatieobject: A new MDTO object
        """
        # read XML file
        tree = ET.parse(mdto_xml)
        root = tree.getroot()
        children = list(root[0])

        # store XML file path for later reference
        path = mdto_xml.name if hasattr(mdto_xml, "write") else str(mdto_xml)

        # check if object type matches informatieobject/bestand
        object_type = root[0].tag.removeprefix("{https://www.nationaalarchief.nl/mdto}")

        cls_name = cls.__name__.lower()
        # mostly needed for test to pass; should this be documented?
        if cls_name == "object":
            if object_type == "informatieobject":
                obj = Informatieobject._from_elem(children)
            elif object_type == "bestand":
                obj = Bestand._from_elem(children)
            else:
                raise ValueError(
                    f"Unknown first child <{object_type}> in {mdto_xml}; "
                    "first child must either be <informatieobject> or <bestand>"
                )
        elif cls_name != object_type:
            raise ValueError(
                f"Unexpected first child <{object_type}> in {mdto_xml}: "
                f"expected <{cls_name}>"
            )
        else:
            obj = cls._from_elem(children)

        obj._file = path
        return obj

    def verwijzing(self) -> VerwijzingGegevens:
        """
        Create a VerwijzingGegevens object that references the Informatieobject/Bestand.
        Useful to populate `heeftRepresentatie` or `isOnderdeelVan`.

        Returns:
            VerwijzingGegevens: reference with the Informatieobject/Bestand's name and ID
        """
        return VerwijzingGegevens(self.naam, self.identificatie)


# TODO: place more restrictions on taal?
@dataclass
class Informatieobject(Object, Serializable):
    """https://www.nationaalarchief.nl/archiveren/mdto/informatieobject

    Example:

    ```python
    informatieobject = Informatieobject(IdentificatieGegevens(…), naam="Kapvergunning", …)

    # write object to file
    informatieobject.save("Informatieobject-368-Kapvergunning.xml")
    ```

    Args:
        identificatie (IdentificatieGegevens | List[IdentificatieGegevens]): Identificatiekenmerk
        naam (str): Aanduiding waaronder het object bekend is
        archiefvormer (VerwijzingGegevens | List[VerwijzingGegevens]): Maker/ontvanger
        beperkingGebruik (BeperkingGebruikGegevens | List[BeperkingGebruikGegevens]): Beperking op het gebruik
        waardering (BegripGegevens): Waardering volgens een selectielijst
        aggregatieniveau (Optional[BegripGegevens]): Aggregatieniveau
        classificatie (Optional[BegripGegevens | List[BegripGegevens]]): Classificatie volgens een classificatieschema
        trefwoord (Optional[str | List[str]]): Trefwoord
        omschrijving (Optional[str | List[str]]): Inhoudelijke omschrijving
        raadpleeglocatie(Optional[RaadpleeglocatieGegevens | List[RaadpleeglocatieGegevens]]): Raadpleeglocatie
        dekkingInTijd (Optional[DekkingInTijdGegevens | List[DekkingInTijdGegevens]]): Betreffende periode/tijdstip
        dekkingInRuimte (Optional[VerwijzingGegevens | List[VerwijzingGegevens]]): Betreffende plaats/locatie
        taal (Optional[str | List[str]]): Taal van het object
        event (Optional[EventGegevens | List[EventGegevens]]): Gerelateerde gebeurtenis
        bewaartermijn (Optional[TermijnGegevens]): Termijn waarin het object bewaard dient te worden
        informatiecategorie (Optional[BegripGegevens]): Informatiecategorie waar de bewaartermijn op gebaseerd is
        isOnderdeelVan (Optional[VerwijzingGegevens | List[VerwijzingGegevens]]): Bovenliggend object
        bevatOnderdeel (Optional[VerwijzingGegevens | List[VerwijzingGegevens]]): Onderliggend object
        heeftRepresentatie (Optional[VerwijzingGegevens | List[VerwijzingGegevens]]): Bijbehorend Bestand object
        aanvullendeMetagegevens (Optional[VerwijzingGegevens | List[VerwijzingGegevens]]): Aanvullende metagegevens
        gerelateerdInformatieobject (Optional[GerelateerdInformatieobjectGegevens | List[GerelateerdInformatieobjectGegevens]]): Gerelateerd object
        betrokkene (Optional[BetrokkeneGegevens | List[BetrokkeneGegevens]]): Persoon/organisatie betrokken bij
          ontstaan en gebruik van dit object
        activiteit (Optional[VerwijzingGegevens | List[VerwijzingGegevens]]): Activiteit waarbij dit object
          is gemaakt/ontvangen
    """

    archiefvormer: VerwijzingGegevens | List[VerwijzingGegevens]
    beperkingGebruik: BeperkingGebruikGegevens | List[BeperkingGebruikGegevens]
    waardering: BegripGegevens
    aggregatieniveau: BegripGegevens = None
    classificatie: BegripGegevens | List[BegripGegevens] = None
    trefwoord: str | List[str] = None
    omschrijving: str | List[str] = None
    raadpleeglocatie: RaadpleeglocatieGegevens | List[RaadpleeglocatieGegevens] = None
    dekkingInTijd: DekkingInTijdGegevens | List[DekkingInTijdGegevens] = None
    dekkingInRuimte: VerwijzingGegevens | List[VerwijzingGegevens] = None
    taal: str | List[str] = None
    event: EventGegevens | List[EventGegevens] = None
    bewaartermijn: TermijnGegevens = None
    informatiecategorie: BegripGegevens = None
    isOnderdeelVan: VerwijzingGegevens | List[VerwijzingGegevens] = None
    bevatOnderdeel: VerwijzingGegevens | List[VerwijzingGegevens] = None
    heeftRepresentatie: VerwijzingGegevens | List[VerwijzingGegevens] = None
    aanvullendeMetagegevens: VerwijzingGegevens | List[VerwijzingGegevens] = None
    gerelateerdInformatieobject: (
        GerelateerdInformatieobjectGegevens | List[GerelateerdInformatieobjectGegevens]
    ) = None
    betrokkene: BetrokkeneGegevens | List[BetrokkeneGegevens] = None
    activiteit: VerwijzingGegevens | List[VerwijzingGegevens] = None

    def _mdto_ordered_fields(self) -> List:
        """Sort dataclass fields by their order in the MDTO XSD."""
        sorting_mapping = {
            "identificatie": 0,
            "naam": 1,
            "aggregatieniveau": 2,
            "classificatie": 3,
            "trefwoord": 4,
            "omschrijving": 5,
            "raadpleeglocatie": 6,
            "dekkingInTijd": 7,
            "dekkingInRuimte": 8,
            "taal": 9,
            "event": 10,
            "waardering": 11,
            "bewaartermijn": 12,
            "informatiecategorie": 13,
            "isOnderdeelVan": 14,
            "bevatOnderdeel": 15,
            "heeftRepresentatie": 16,
            "aanvullendeMetagegevens": 17,
            "gerelateerdInformatieobject": 18,
            "archiefvormer": 19,
            "betrokkene": 20,
            "activiteit": 21,
            "beperkingGebruik": 22,
        }

        return [
            field
            for field in sorted(
                dataclasses.fields(self), key=lambda f: sorting_mapping[f.name]
            )
        ]

    def to_xml(self) -> ET.ElementTree:
        """Transform Informatieobject into an XML tree with the following structure:

        ```xml
        <MDTO xmlns=…>
            <informatieobject>
                …
            </informatieobject>
        </MDTO>
        ```

        Note:
           When trying to save a Informatieobject to a file, use `my_informatieobject.save('file.xml')` instead.

        Returns:
            ET.ElementTree: XML tree representing the Informatieobject object
        """
        return super().to_xml("informatieobject")


@dataclass
class Bestand(Object, Serializable):
    """https://www.nationaalarchief.nl/archiveren/mdto/bestand

    Note:
        When creating Bestand objects, it's easier to use the
        `bestand_from_file()` convenience function instead.

    Args:
        identificatie (IdentificatieGegevens | List[IdentificatieGegevens]): Identificatiekenmerk
        naam (str): Aanduiding waaronder dit object bekend is (meestal bestandsnaam)
        omvang (int): Aantal bytes in het bestand
        bestandsformaat (BegripGegevens): Bestandsformaat, bijv. PRONOM of MIME-type informatie
        checksum (ChecksumGegevens): Checksum gegevens van het bestand
        isRepresentatieVan (VerwijzingGegevens): Object waarvan dit bestand een representatie is
        URLBestand (Optional[str]): Actuele verwijzing naar dit bestand als RFC 3986 conforme URI
    """

    omvang: int
    bestandsformaat: BegripGegevens
    checksum: ChecksumGegevens | List[ChecksumGegevens]
    isRepresentatieVan: VerwijzingGegevens
    URLBestand: str = None

    def _mdto_ordered_fields(self) -> List:
        """Sort dataclass fields by their order in the MDTO XSD."""
        fields = super()._mdto_ordered_fields()
        # swap order of isRepresentatieVan and URLbestand
        return fields[:-2] + (fields[-1], fields[-2])

    def to_xml(self) -> ET.ElementTree:
        """
        Transform Bestand into an XML tree with the following structure:

        ```xml
        <MDTO xmlns=…>
            <bestand>
                …
            </bestand>
        </MDTO>
        ```

        Note:
           When trying to save a Bestand object to a file, use `my_bestand.save('file.xml')` instead.

        Returns:
            ET.ElementTree: XML tree representing Bestand object
        """
        return super().to_xml("bestand")

    def validate(self) -> None:
        """Check if URLBestand is a RFC 3986 compliant URI"""
        super().validate()
        if not helpers.validate_url_or_urls(self.URLBestand):
            raise ValidationError(
                ["bestand", "URLBestand"],
                f"url {self.URLBestand} is malformed",
            )


def _construct_deserialization_classmethods():
    """
    Construct the private `_from_elem()` classmethod on all subclasses
    of `Serializable`.

    This constructor executes on module import, and creates helpers
    for the public `from_xml()` classmethods of Informatieobject and
    Bestand.
    """

    def resolve_type(field_type: type):
        """Resolve a type from typing annotations. If Union[...] is
        detected, return the type of the first item."""

        origin = get_origin(field_type)
        if origin is Union:
            args = get_args(field_type)
            return args[0]  # assume first type is what we care about

        return field_type

    def parse_text(elem: ET.Element) -> str:
        return elem.text

    def parse_int(elem: ET.Element) -> int:
        return int(elem.text)

    # measurably faster
    def parse_identificatie(elem: ET.Element) -> IdentificatieGegevens:
        return IdentificatieGegevens(
            elem[0].text,
            elem[1].text,
        )

    def from_elem_factory(cls, mdto_xml_parsers: dict) -> classmethod:
        """Create initialized from_elem functions."""

        def from_elem(inner_cls, elem: ET.Element):
            constructor_args = {field: [] for field in mdto_xml_parsers}

            for child in elem:
                mdto_field = child.tag.removeprefix(
                    "{https://www.nationaalarchief.nl/mdto}"
                )
                parser = mdto_xml_parsers[mdto_field]
                constructor_args[mdto_field].append(parser(child))

            # cleanup class constructor arguments
            for argname, value in constructor_args.items():
                # Replace empty argument lists by None
                if len(value) == 0:
                    constructor_args[argname] = None
                # Replace one-itemed argument lists by their respective item
                elif len(value) == 1:
                    constructor_args[argname] = value[0]

            return inner_cls(**constructor_args)

        return classmethod(from_elem)

    # This loop depends on the order of the gegevensgroep defintions in this file
    for cls in Serializable.__subclasses__():
        parsers = {}
        for field in dataclasses.fields(cls):
            field_name = field.name
            field_type = resolve_type(field.type)

            if field_type is str:
                parsers[field_name] = parse_text
            elif field_type is IdentificatieGegevens:
                parsers[field_name] = parse_identificatie
            elif issubclass(field_type, Serializable):
                # field_type == BegripGegevens, VerwijzingGegevens, etc.
                parsers[field_name] = field_type._from_elem
            elif field_type is int:
                parsers[field_name] = parse_int
            else:
                parsers[field_name] = parse_text

        cls._from_elem = from_elem_factory(cls, parsers)


# construct all _from_elem() classmethods immediately on import
_construct_deserialization_classmethods()
