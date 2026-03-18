import pytest

from mdto.gegevensgroepen import *

# Tests related to cleaning optional empty values


def test_nested_cleaning():
    """Test cleaning of nested structures."""

    nested_obj = BegripGegevens(
        "test", VerwijzingGegevens("test", IdentificatieGegevens("", None))
    )
    nested_obj.clean_optional_empty_values()
    assert nested_obj.begripBegrippenlijst.verwijzingIdentificatie is None


def test_clean_only_optional(shared_informatieobject):
    """Required fields should be cleaned, but never completely emptied. This
    ensures that previously valid MDTO isn't rendered invalid.
    """

    empty_id = IdentificatieGegevens("", "")
    shared_informatieobject.identificatie = [empty_id] * 3
    shared_informatieobject.clean_optional_empty_values()
    assert shared_informatieobject.identificatie is not None
    # note: cleaning is assumed not to delistify
    assert len(shared_informatieobject.identificatie) == 1


def test_clean_list(shared_informatieobject):
    """Only clean non-empty list items."""
    shared_informatieobject.identificatie = [
        IdentificatieGegevens("", ""),
        IdentificatieGegevens("test123", "test123"),
        IdentificatieGegevens("", ""),
    ]
    shared_informatieobject.clean_optional_empty_values()
    assert len(shared_informatieobject.identificatie) == 1
