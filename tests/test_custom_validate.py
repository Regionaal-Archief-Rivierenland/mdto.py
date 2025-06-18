import pytest

from mdto import ValidationError
from mdto.gegevensgroepen import *
from mdto.helpers import valid_mdto_datetime, valid_duration


def test_validate_recursive(shared_informatieobject):
    """Test validation in deeply nested structure."""
    shared_informatieobject.bewaartermijn = TermijnGegevens(
        termijnTriggerStartLooptijd=BegripGegevens(
            "V",
            # IdentificatieGegevens is the incorrect child
            IdentificatieGegevens("nvt", "nvt"),
        )
    )

    with pytest.raises(
        ValidationError, match=r"\w+(\.\w+)+:\s+expected type \w+, got \w+"
    ):
        shared_informatieobject.validate()


def test_validate_sequence_type_checking(shared_informatieobject):
    """Test validation of sequence type checking."""

    shared_informatieobject.identificatie = [
        shared_informatieobject.identificatie,
        VerwijzingGegevens("foo"),
    ]
    with pytest.raises(
        ValidationError,
        match=r"\w+(\.\w+)+:\s+list items must be \w+, but found \w+, \w+",
    ):
        shared_informatieobject.validate()

    # reset informatieobject back to normal
    shared_informatieobject.identificatie = shared_informatieobject.identificatie[0]
    shared_informatieobject.naam = ["foo", "bar"]
    with pytest.raises(
        ValidationError,
        match=r"\w+(\.\w+)+:\s+got type \w+, but field does not accept sequences",
    ):
        shared_informatieobject.validate()


def test_validate_url(shared_informatieobject):
    """Test URL validation."""
    shared_informatieobject.raadpleeglocatie = RaadpleeglocatieGegevens(
        raadpleeglocatieOnline="hppts://www.example.com"  # misspelling
    )

    with pytest.raises(
        ValidationError,
        match=r"\w+(\.\w+)+:\s+url .* is malformed",
    ):
        shared_informatieobject.validate()


@pytest.mark.parametrize(
    "date_str",
    [
        "2001",
        "2020-10Z",
        "2001-10-12T12:05:11",
        "2001-10+02:00",
    ],
)
def test_valid_dates(date_str):
    assert valid_mdto_datetime(date_str)


@pytest.mark.parametrize(
    "date_str",
    [
        "2001-13",  # no 13th month
        "99-10",  # year must have four digits
        "2020-10+25:00",  # invalid TZ
        "2001-10-12T12:05:70",  # invalid seconds
    ],
)
def test_invalid_dates(date_str):
    assert not valid_mdto_datetime(date_str)

@pytest.mark.parametrize(
    "duration_str",
    [
        "P3Y6M4DT12H30M5S",
        "P0.5Y",
        "P10W",
    ]
)
def test_valid_durations(duration_str):
    assert valid_duration(duration_str)

@pytest.mark.parametrize(
    "duration_str",
    [
        "P",              # just 'P' is not enough
        "P12",            # no time indication providedt
        "P1YM",           # 'M' alone after 'Y' is not valid (missing number)
        "1Y2M",           # missing leading 'P'
        "P10W20Y",        # out of order
    ]
)
def test_invalid_durations(duration_str):
    assert not valid_duration(duration_str)
