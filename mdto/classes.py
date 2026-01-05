import dataclasses
import hashlib
import os
import uuid
import re
from dataclasses import Field, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, List, Self, TextIO, Type, TypeVar, Union, get_args, get_origin

import lxml.etree as ET

from . import helpers

# globals
MDTO_MAX_NAAM_LENGTH = 80

# needed to inform LSPs about @classmethod return types
ObjectT = TypeVar("ObjectT", bound="Object")


class ValidationError(TypeError):
    """Custom formatter for MDTO validation errors"""

    def __init__(self, field_path: list[str], msg: str, src_file: str = None):
        # print associated source file, if given
        if src_file:
            msg += f" (source file: {src_file})"

        super().__init__(f"{'.'.join(field_path)}:\n  {msg}")
        self.field_path = field_path
        self.msg = msg


class DateValidationError(ValidationError):
    """Custom formatter for MDTO date(time) validation errors"""

    def __init__(self, field_path: list[str], date: str, fmts: list[str]):
        fmts.sort()
        # Format bullet list
        supported_fmts = "\n".join(f"  • {fmt}" for fmt in fmts)
        field_name = field_path[-1]
        msg = (
            f"Date '{date}' is incorrectly formatted or non-existent; {field_name} supports:\n\n"
            f"{supported_fmts}\n\n"
            "  Each format may include timezone info, e.g. '+01:00' or 'Z'"
        )
        super().__init__(field_path, msg)


# TODO: update name and docstring to be more descriptive? Now, this class does more than just serialize
# or maybe refactor?
class Serializable:
    """Provides validate() and to_xml() methods for converting MDTO dataclasses
    to valid MDTO XML."""

    def validate(self) -> None:
        """Validate the object's fields against the MDTO schema. Additional
        validation logic can be incorporated by extending this method in a
        subclass.

        Note:
           Typing information is infered based on type hints.

        Raises:
            ValidationError: field violates the MDTO schema
        """
        for field in dataclasses.fields(self):
            field_name = field.name
            field_value = getattr(self, field_name)
            field_type = field.type
            optional_field = field.default is None

            # optional fields may be None
            if optional_field and field_value is None:
                continue

            cls_name = self.__class__.__name__
            _ValidationError = (
                lambda msg: ValidationError([cls_name, field_name], msg, self._srcfile)
                if cls_name in ["Informatieobject", "Bestand"]
                else ValidationError([field_name], msg)
            )

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

    def _mdto_ordered_fields(self) -> list[Field]:
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
            self._serialize_dataclass_field(root_elem, field_name, field_value)

        # return the tree
        return root_elem

    def _serialize_dataclass_field(
        self, root_elem: ET.Element, field_name: str, field_value: Any
    ):
        """Recursively serialize a dataclass field, and append its XML
        representation to `root_elem`."""

        # skip empty fields
        if field_value is None:
            return

        # listify
        if not isinstance(field_value, (list, tuple, set)):
            field_value = (field_value,)

        # serialize sequence of primitives and *Gegevens objects
        for val in field_value:
            if isinstance(val, Serializable):
                root_elem.append(val.to_xml(field_name))
            else:
                # micro-optim: create subelem and .text content in one go
                ET.SubElement(root_elem, field_name).text = str(val)

    def _is_empty(self) -> bool:
        """Check if all values resolve to empty strings or None."""
        values = [getattr(self, f.name) for f in dataclasses.fields(self)]
        return all(v is None or not str(v) for v in values)

    def clean_optional_empty_values(self) -> None:
        """Recursively removes all empty optional fields from the tree.

        This is not done automatically since empty values may reflect
        logic flaws earlier in the pipeline. These possible flaws should
        be scrutinized, rather than silently passed over.

        Example:
            ```python
            >>> informatieobject.dekkingInRuimte = VerwijzingGegevens("", IdentificatieGegevens("", ""))
            >>> informatieobject.clean_optional_empty_values()
            >>> print(informatieobject.dekkingInRuimte)
            None
            ```

        Note:
            Edits objects in-place.
        """

        for field in dataclasses.fields(self):
            field_name = field.name
            field_value = getattr(self, field_name)
            optional_field = field.default is None

            if field_value is None:
                continue

            was_singleton = not isinstance(field_value, (list, tuple, set))
            field_value = [field_value] if was_singleton else field_value

            cleaned = []
            for val in field_value:
                if isinstance(val, Serializable):
                    val.clean_optional_empty_values()
                    # nuke whenever there are no remaining leaves
                    if not val._is_empty():
                        cleaned.append(val)
                else:
                    if val is not None and str(val):
                        cleaned.append(val)

            # ensure previously valid MDTO isn't rendered invalid by
            # emptying a required field
            if len(cleaned) == 0 and not optional_field:
                cleaned = field_value[:1]

            # TODO: maybe log removals?
            if was_singleton:
                setattr(self, field_name, cleaned[0] if cleaned else None)
            else:
                setattr(self, field_name, cleaned)

    @classmethod
    def _from_elem(cls, elem: ET.Element):
        """Private helper method stub.

        Used within open() to construct a gegevensgroep from an ET.Element.
        This stub is dynamically implemented at runtime.
        """
        pass


@dataclass
class IdentificatieGegevens(Serializable):
    """https://nationaalarchief.nl/archiveren/mdto/identificatieGegevens

    Args:
        identificatieKenmerk (str): Een kenmerk waarmee een object geïdentificeerd kan worden
        identificatieBron (str): Herkomst van het kenmerk
    """

    identificatieKenmerk: str
    identificatieBron: str

    @classmethod
    def uuid(cls) -> Self:
        """Create a IdentificatieGegevens containing a UUID4.

        Example:
            ```python
            >>> informatieobject.identificatie = IdentificatieGegevens.uuid()
            >>> print(informatieobject.identificatie)
            IdentificatieGegevens(identificatieKenmerk='4254ae31-7ac128f…',
                                  identificatieBron='UUID4 via mdto.py')
            ```

        Returns:
            IdentificatieGegevens: IdentificatieGegevens containing a UUID4
        """
        return cls(str(uuid.uuid4()), "UUID4 via mdto.py")


@dataclass
class VerwijzingGegevens(Serializable):
    """https://nationaalarchief.nl/archiveren/mdto/verwijzingsGegevens

    Args:
        verwijzingNaam (str): Naam van het object waarnaar verwezen wordt
        verwijzingIdentificatie (Optional[IdentificatieGegevens]): Identificatie van het object waarnaar verwezen wordt
    """

    verwijzingNaam: str
    verwijzingIdentificatie: IdentificatieGegevens = None

    def validate(self) -> None:
        super().validate()
        if len(self.verwijzingNaam) > MDTO_MAX_NAAM_LENGTH:
            helpers.logger.warning(
                f"VerwijzingGegevens.verwijzingNaam: {self.verwijzingNaam} exceeds recommended length of {MDTO_MAX_NAAM_LENGTH}"
            )

    @classmethod
    def gemeente(cls, gemeentenaam_of_tooi_code: str) -> Self:
        """Create a VerwijzingGegevens that references a municipality
        by its official name and code from the TOOI register.

        Accepts either a municipality name (e.g. 'Tiel', 'Gemeente Brielle') or
        a code (e.g. 'gm0218', '0218').

        Example:
            ```python
            >>> tiel = VerwijzingGegevens.gemeente('Tiel')
            >>> tiel.verwijzingIdentificatie
            IdentificatieGegevens('gm0218', 'TOOI register gemeenten compleet')
            # create a reference to a munacipality from its TOOI code instead of name
            >>> alphen = VerwijzingGegevens.gemeente('0484')
            >>> alphen.verwijzingNaam
            Gemeente Alphen aan den Rijn
            ```

        Args:
            gemeentenaam_of_tooi_code: Municipality name (optionally prefixed with "Gemeente")
                                       or four-digit code (optionally prefixed with "gm").

        Returns:
            VerwijzingGegevens: reference to a municipality by its
             official name and code from the TOOI register.

        Raises:
            ValueError: Municipality name or code was not found in the TOOI register.
        """
        tooi_register = helpers.load_tooi_register_gemeenten()

        if match := re.fullmatch(r"(gm)?(\d{4})", gemeentenaam_of_tooi_code.lower()):
            # get name from code
            tooi_code = match.group(2)
            if tooi_naam := tooi_register.get(tooi_code):
                tooi_naam = f"Gemeente {tooi_naam}"
        else:
            # get code from name
            tooi_code = tooi_register.get(
                gemeentenaam_of_tooi_code.lower().removeprefix("gemeente ")
            )
            tooi_naam = gemeentenaam_of_tooi_code

        if tooi_naam and tooi_code:
            return cls(
                tooi_naam,
                IdentificatieGegevens(
                    f"gm{tooi_code}", "TOOI register gemeenten compleet"
                ),
            )

        raise ValueError(
            f"Name or code '{gemeentenaam_of_tooi_code}' not found in 'TOOI register gemeenten compleet'. "
            "For a list of possible values, see https://identifier.overheid.nl/tooi/set/rwc_gemeenten_compleet"
        )


@dataclass
class BegripGegevens(Serializable):
    """https://nationaalarchief.nl/archiveren/mdto/begripGegevens

    Args:
        begripLabel (str): De tekstweergave van het begrip
        begripBegrippenlijst (VerwijzingGegevens): Verwijzing naar een beschrijving van de begrippen
        begripCode (Optional[str]): De code die aan het begrip is toegekend
    """

    begripLabel: str
    begripBegrippenlijst: VerwijzingGegevens
    begripCode: str = None

    def _mdto_ordered_fields(self) -> list[Field]:
        """Sort dataclass fields by their order in the MDTO XSD."""
        fields = super()._mdto_ordered_fields()
        # swap order of begripBegrippenlijst and begripCode
        return (fields[0], fields[2], fields[1])


@dataclass
class TermijnGegevens(Serializable):
    """https://nationaalarchief.nl/archiveren/mdto/termijnGegevens

    Args:
        termijnTriggerStartLooptijd (Optional[BegripGegevens]): Gebeurtenis waarna de looptijd van de termijn start
        termijnStartdatumLooptijd (Optional[str]): Datum waarop de looptijd is gestart, in `YYYY-MM-DD` formaat
        termijnLooptijd (Optional[str]): Hoeveelheid tijd waarin de termijnEindDatum bereikt wordt, bijv. `P20Y`
        termijnEinddatum (Optional[str]): Datum waarop de termijn eindigt, bijv. `2029-10-10`
    """

    termijnTriggerStartLooptijd: BegripGegevens = None
    termijnStartdatumLooptijd: str = None
    termijnLooptijd: str = None
    termijnEinddatum: str = None

    def validate(self) -> None:
        # FIXME: get a way to retrieve a more complete path?
        super().validate()

        if self.termijnStartdatumLooptijd and not helpers.valid_mdto_date_precise(
            self.termijnStartdatumLooptijd
        ):
            raise DateValidationError(
                ["termijnStartdatumLooptijd"],
                self.termijnStartdatumLooptijd,
                ["%Y-%m-%d"],
            )

        if self.termijnEinddatum and not helpers.valid_mdto_date(self.termijnEinddatum):
            raise DateValidationError(
                ["termijnEinddatum"],
                self.termijnEinddatum,
                [f for f, _ in helpers.date_fmts],
            )

        if self.termijnLooptijd and not helpers.valid_duration(self.termijnLooptijd):
            raise ValidationError(
                ["termijnLooptijd"],
                f"'{self.termijnLooptijd}' is not a valid duration. See "
                "https://www.w3.org/TR/xmlschema-2/#duration for more information.",
            )


@dataclass
class ChecksumGegevens(Serializable):
    """https://nationaalarchief.nl/archiveren/mdto/checksum

    Note:
        When building Bestand objects, it's recommended to call the convience
        function `Bestand.from_file()` instead. To simply compute a new checksum of a given file,
        see `ChecksumGegevens.from_file(...)`.

    Example:

        ```python
        bestand = Bestand.generate(...)
        # assign a new checksum
        bestand.checksum = Checksum.from_file("foo.txt")
        ```

    Args:
        checksumAlgoritme (BegripGegevens): Naam van het algoritme dat is gebruikt om de checksum te maken
        checksumWaarde (str): Waarde van de checksum
        checksumDatum (str): Datum waarop de checksum gemaakt is
    """

    checksumAlgoritme: BegripGegevens
    checksumWaarde: str
    checksumDatum: str

    def validate(self) -> None:
        super().validate()

        if not helpers.valid_mdto_datetime_precise(self.checksumDatum):
            raise DateValidationError(
                # FIXME: having ["Bestand", "checksum", "checksumDatum"] here leads to weird error
                # messages in Object.validate() (i.e. .validate() calls in parent classes).
                # The shortened version is also kind of weird tho, because you have no parent information. (you now only get that if you call .validate on a Bestand)
                ["checksumDatum"],
                self.checksumDatum,
                ["%Y-%m-%dT%H:%M:%S"],
            )

    @classmethod
    def from_file(
        cls, file_or_filename: TextIO | str, algorithm: str = "sha256"
    ) -> Self:
        """Convience function for creating ChecksumGegegevens objects.

        Takes a file-like object or path to file, and then computes the requisite
        checksum metadata (i.e.  `checksumAlgoritme`, `checksumWaarde`, and
        `checksumDatum`) from that file.

        Example:

            ```python
            pdf_checksum = ChecksumGegevens.from_file('document.pdf')
            # create ChecksumGegevens with a 512 bits instead of a 256 bits checksum
            jpg_checksum = ChecksumGegevens.from_file('scan-003.jpg', algorithm="sha512")
            ```

        Args:
            file_or_filename (TextIO | str): file-like object to generate checksum data for
            algorithm (Optional[str]): checksum algorithm to use; defaults to sha256.
             For valid values, see https://docs.python.org/3/library/hashlib.html

        Returns:
            ChecksumGegevens: checksum metadata for `file_or_filename`
        """
        infile = helpers.process_file(file_or_filename)

        verwijzingBegrippenlijst = VerwijzingGegevens(
            verwijzingNaam="Begrippenlijst ChecksumAlgoritme MDTO"
        )

        checksumAlgoritme = BegripGegevens(
            begripLabel=algorithm.upper(), begripBegrippenlijst=verwijzingBegrippenlijst
        )

        # file_digest() expects a file in binary mode, hence `infile.buffer.raw`
        checksumWaarde = hashlib.file_digest(infile.buffer.raw, algorithm).hexdigest()

        checksumDatum = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        return cls(checksumAlgoritme, checksumWaarde, checksumDatum)


@dataclass
class BeperkingGebruikGegevens(Serializable):
    """https://nationaalarchief.nl/archiveren/mdto/beperkingGebruik

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
    """https://nationaalarchief.nl/archiveren/mdto/dekkingInTijd

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

        if not helpers.valid_mdto_date(self.dekkingInTijdBegindatum):
            raise DateValidationError(
                ["Informatieobject", "dekkingInTijd", "dekkingInTijdBegindatum"],
                self.dekkingInTijdBegindatum,
                [f for f, _ in helpers.date_fmts],
            )

        if self.dekkingInTijdEinddatum and not helpers.valid_mdto_date(
            self.dekkingInTijdEinddatum
        ):
            raise DateValidationError(
                ["Informatieobject", "dekkingInTijd", "dekkingInTijdEinddatum"],
                self.dekkingInTijdEinddatum,
                [f for f, _ in helpers.date_fmts],
            )


@dataclass
class EventGegevens(Serializable):
    """https://nationaalarchief.nl/archiveren/mdto/event

    Args:
        eventType (BegripGegevens): Het type event
        eventTijd (Optional[str]): Datum + tijdstip waarop event plaatsvond, bijv. 2001-10-12T12:05:11
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
            raise DateValidationError(
                ["Informatieobject", "event", "eventTijd"],
                self.eventTijd,
                [f for f, _ in helpers.datetime_fmts],
            )


@dataclass
class RaadpleeglocatieGegevens(Serializable):
    """https://nationaalarchief.nl/archiveren/mdto/raadpleeglocatie

    Args:
        raadpleeglocatieFysiek (Optional[VerwijzingGegevens])): Fysieke raadpleeglocatie van het informatieobject
        raadpleeglocatieOnline (Optional[str]): Online raadpleeglocatie van het informatieobject; moet een valide URL zijn
    """

    raadpleeglocatieFysiek: VerwijzingGegevens | List[VerwijzingGegevens] = None
    raadpleeglocatieOnline: str | List[str] = None

    def validate(self) -> None:
        super().validate()

        # listify
        urls = (
            [self.raadpleeglocatieOnline]
            if isinstance(self.raadpleeglocatieOnline, str)
            else self.raadpleeglocatieOnline
            or []  # handle raadpleeglocatieOnline is None
        )

        for u in urls:
            if not helpers.valid_url(u):
                raise ValidationError(
                    # FIXME: maybe this path should be generated on the fly?
                    [
                        "informatieobject",
                        "raadpleeglocatie",
                        "raadpleeglocatieOnline",
                    ],
                    f"url {u} is malformed",
                )


@dataclass
class GerelateerdInformatieobjectGegevens(Serializable):
    """https://nationaalarchief.nl/archiveren/mdto/gerelateerdInformatieobjectGegevens

    Args:
        gerelateerdInformatieobjectVerwijzing (VerwijzingGegevens): Verwijzing naar het gerelateerde informatieobject
        gerelateerdInformatieobjectTypeRelatie (BegripGegevens): Typering van de relatie
    """

    gerelateerdInformatieobjectVerwijzing: VerwijzingGegevens
    gerelateerdInformatieobjectTypeRelatie: BegripGegevens


@dataclass
class BetrokkeneGegevens(Serializable):
    """https://nationaalarchief.nl/archiveren/mdto/betrokkeneGegevens

    Args:
        betrokkeneTypeRelatie (BegripGegevens): Typering van de betrokkenheid van de actor bij het informatieobject
        betrokkeneActor (VerwijzingGegevens): Persoon of organisatie die betrokken is bij het informatieobject
    """

    betrokkeneTypeRelatie: BegripGegevens
    betrokkeneActor: VerwijzingGegevens


# TODO: document constructing from the Object class directly?
@dataclass
class Object(Serializable):
    """https://nationaalarchief.nl/archiveren/mdto/object

    This class serves as the parent class to Informatieobject and
    Bestand. There is no reason to use it directly.

    MDTO objects that derive from this class inherit a open() and
    save() method, which can be used to read/write these objects
    to/from XML files.
    """

    identificatie: IdentificatieGegevens | List[IdentificatieGegevens]
    naam: str

    def __post_init__(self):
        # adds possibility to associate MDTO objects with files
        self._srcfile: str | None = None
        """adds possibility to associate MDTO objects with files"""

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
        return tree

    def validate(self) -> None:
        super().validate()
        if len(self.naam) > MDTO_MAX_NAAM_LENGTH:
            helpers.logger.warning(
                f"{self.__class__.__name__}.naam: '{self.naam}' exceeds recommended length of {MDTO_MAX_NAAM_LENGTH}"
            )

    def save(
        self,
        file_or_filename: str | TextIO,
        minify: bool = False,
        lxml_kwargs: dict = {},
    ) -> None:
        """Save object to a XML file, provided it satifies the MDTO schema.

        The XML is pretty printed by default; use `minify=True` to reverse this.

        Args:
            file_or_filename (str | TextIO): Path or file-like object to write
             object's XML representation to
            minify (Optional[bool]): the reverse of pretty printing; makes the XML
             as small as possible by removing the XML declaration and any optional
             whitespace
            lxml_kwargs (Optional[dict]): optional dict of keyword arguments that
             can be used to override the args passed to lxml's `write()`.

        Note:
            For a complete list of arguments of lxml's write method, see
            https://lxml.de/apidoc/lxml.etree.html#lxml.etree._ElementTree.write

        Raises:
            ValidationError: Object voilates the MDTO schema
        """
        # lxml wants files in binary mode, so pass along a file's raw byte stream
        if hasattr(file_or_filename, "write"):
            file_or_filename = file_or_filename.buffer.raw

        # validate before serialization to ensure correctness
        # (doing this in to_xml would be slow, and perhaps unexpected)
        self.validate()
        xml = self.to_xml()

        if not minify:
            # match MDTO voorbeeld bestanden in terms of whitespace
            ET.indent(xml, space="\t")

        lxml_defaults = {
            "xml_declaration": not minify,
            "pretty_print": not minify,
            "encoding": "UTF-8",
        }

        # `|` is a union operator; it merges two dicts, with right-hand side taking precedence
        xml.write(file_or_filename, **(lxml_defaults | lxml_kwargs))

    @classmethod
    def open(cls: Type[ObjectT], mdto_xml: TextIO | str) -> ObjectT:
        """Construct a Informatieobject/Bestand object from a MDTO XML file.

        Example:

        ```python
        # read informatieobject from file
        archiefstuk = Informatieobject.open("Voorbeeld Archiefstuk Informatieobject.xml")

        # edit the informatieobject
        archiefstuk.naam = "Verlenen kapvergunning Flipje's Erf 15 Tiel"

        # override the original informatieobject XML
        archiefstuk.save("Voorbeeld Archiefstuk Informatieobject.xml")
        ```

        Note:
            The parser tolerates some schema violations. Specifically, it will
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
             The path to this file is stored in the `._srcfile` attribute for future reference.

        Returns:
            Bestand | Informatieobject: A new MDTO object
        """
        # read XML file
        tree = ET.parse(mdto_xml)
        root = tree.getroot()
        children = list(root[0])

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

        # store original file path for later reference
        # TODO: normalize this so that it will always store an absolute path?
        obj._srcfile = mdto_xml.name if hasattr(mdto_xml, "write") else str(mdto_xml)
        return obj

    def verwijzing(self) -> VerwijzingGegevens:
        """
        Create a VerwijzingGegevens object that references this Informatieobject/Bestand.
        Useful to populate `heeftRepresentatie`, `isOnderdeelVan`, and `bevatOnderdeel`.

        Returns:
            VerwijzingGegevens: reference with the Informatieobject/Bestand's name and ID
        """
        return VerwijzingGegevens(self.naam, self.identificatie)


@dataclass
class Informatieobject(Object, Serializable):
    """https://nationaalarchief.nl/archiveren/mdto/informatieobject

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

    def _mdto_ordered_fields(self) -> List[Field]:
        """Sort dataclass fields by their order in the MDTO XSD."""
        f = super()._mdto_ordered_fields()
        # fmt: off
        return (
            f[0],   # identificatie
            f[1],   # naam
            f[5],   # aggregatieniveau
            f[6],   # classificatie
            f[7],   # trefwoord
            f[8],   # omschrijving
            f[9],   # raadpleeglocatie
            f[10],  # dekkingInTijd
            f[11],  # dekkingInRuimte
            f[12],  # taal
            f[13],  # event
            f[4],   # waardering
            f[14],  # bewaartermijn
            f[15],  # informatiecategorie
            f[16],  # isOnderdeelVan
            f[17],  # bevatOnderdeel
            f[18],  # heeftRepresentatie
            f[19],  # aanvullendeMetagegevens
            f[20],  # gerelateerdInformatieobject
            f[2],   # archiefvormer
            f[21],  # betrokkene
            f[22],  # activiteit
            f[3],   # beperkingGebruik
        )
        # fmt: on

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

    def validate(self) -> None:
        super().validate()
        if self.taal and not helpers.valid_langcode(self.taal):
            raise ValidationError(
                ["Informatieobject", "taal"],
                f"'{self.taal}' is not a valid RFC3066 language code. "
                "See https://en.wikipedia.org/wiki/IETF_language_tag for more information.",
            )


@dataclass
class Bestand(Object, Serializable):
    """https://nationaalarchief.nl/archiveren/mdto/bestand

    Note:
        When creating Bestand objects, it's *almost always* easier to use the
        `Bestand.from_file()` class method instead.

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

    def _mdto_ordered_fields(self) -> List[Field]:
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
        super().validate()
        if self.URLBestand and not helpers.valid_url(self.URLBestand):
            raise ValidationError(
                ["Bestand", "URLBestand"],
                f"url {self.URLBestand} is malformed",
            )

    @classmethod
    def from_file(
        cls,
        file: TextIO | str,
        isrepresentatievan: VerwijzingGegevens | TextIO | str,
        use_mimetype: bool = False,
    ) -> Self:
        """Convenience function for creating a Bestand object from a file, such
        as a PDF.

        This function differs from calling Bestand() directly in that it
        infers most information for you (checksum, PRONOM info, etc.) by
        inspecting `file`. `<identificatie>` is set to a UUID.

        Args:
            file (TextIO | str): the file the Bestand object represents
            isrepresentatievan (TextIO | str | VerwijzingGegevens): a XML
              file containing an informatieobject, or a
              VerwijzingGegevens referencing an informatieobject.
              Used to construct <isRepresentatieVan>.
            use_mimetype (Optional[bool]): populate `<bestandsformaat>`
              with mimetype instead of PRONOM info

        Example:
         ```python

         verwijzing_obj = VerwijzingGegevens("vergunning.mdto.xml")
         bestand = Bestand.from_file(
              "vergunning.pdf",
              isrepresentatievan=verwijzing_obj  # or pass the actual file
         )

         # change identificatiekenmerk, if desired (defaults to a UUID)
         bestand.identificatie = ...

         bestand.save("vergunning.pdf.bestand.mdto.xml")
         ```

        Raises:
            RuntimeError: PRONOM or mimetype detection failed.

        Returns:
            Bestand: new Bestand object
        """
        file = helpers.process_file(file)

        # set <naam> to basename
        naam = os.path.basename(file.name)
        omvang = os.path.getsize(file.name)
        checksum = ChecksumGegevens.from_file(file)

        if not use_mimetype:
            bestandsformaat = helpers.pronominfo(file.name)
        else:
            bestandsformaat = helpers.mimetypeinfo(file.name)

        # file or file path?
        if isinstance(isrepresentatievan, (str, Path)) or hasattr(
            isrepresentatievan, "read"
        ):
            informatieobject_file = helpers.process_file(isrepresentatievan)
            # Construct verwijzing from informatieobject file
            verwijzing_obj = helpers.detect_verwijzing(informatieobject_file)
            informatieobject_file.close()
        elif isinstance(isrepresentatievan, VerwijzingGegevens):
            verwijzing_obj = isrepresentatievan
        else:
            raise TypeError(
                "isrepresentatievan must either be a path, file, or a VerwijzingGegevens object."
            )

        file.close()

        return cls(
            IdentificatieGegevens.uuid(),
            naam,
            omvang,
            bestandsformaat,
            checksum,
            verwijzing_obj,
        )


def _construct_deserialization_classmethods():
    """
    Construct the private `_from_elem()` classmethod on all subclasses
    of `Serializable`.

    This constructor executes on module import, and creates helpers
    for the public `open()` classmethods of Informatieobject and
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

    def from_elem_factory(mdto_xml_parsers: dict) -> classmethod:
        """Create initialized from_elem functions."""

        def from_elem(cls, elem: ET.Element):
            """Convert XML elements (`elem`) to MDTO classes (`cls`)"""

            # it may seem like pre computing this is faster, but it is not
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

            return cls(**constructor_args)

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

        cls._from_elem = from_elem_factory(parsers)


# construct all _from_elem() classmethods immediately on import
_construct_deserialization_classmethods()
