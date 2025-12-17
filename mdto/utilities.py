# Public functions

from typing import TextIO

from .gegevensgroepen import Object

def open(mdto_xml: TextIO | str) -> Object:
    """The same as calling `Informatieobject.open()` or `Bestand.open()`, but
    without having to know wether the object to be opened is a Bestand or
    Informatieobject.

    Note:
        This is the same as
        ```python
        from mdto.gegevensgroepen import Object
        # informatieobject_of_bestand = Object.open(...)
        ```
    """
    return Object.open(mdto_xml)
