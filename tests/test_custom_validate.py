import pytest

from mdto import ValidationError, DateValidationError
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
        "99-10",  # year must have four digits
        "2001-9",  # months must be zero padded
        "2001-13",  # no 13th month
        "2001-09-9",  # days must be zero padded
        "2020-10+25:00",  # invalid TZ
        "2020-10Z01:00",  # invalid TZ
        "2001-10-12T12:05:70",  # invalid seconds
        "2001-10-12T12:05:1",  # invalid seconds
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
    ],
)
def test_valid_durations(duration_str):
    assert valid_duration(duration_str)


# fmt: off
@pytest.mark.parametrize(
    "duration_str",
    [
        "P",              # just 'P' is not enough
        "P12",            # no time indication provided
        "P1YM",           # 'M' alone after 'Y' is not valid (missing number)
        "1Y2M",           # missing leading 'P'
        "P10W20Y",        # out of order
        "-P10Y",          # negative durations are unsupported since they don't make semantic sense within MDTO
    ]
)
# fmt: on
def test_invalid_durations(duration_str):
    assert not valid_duration(duration_str)


def test_invalid_dekking_in_tijd_gegevens():
    """An end date that lies before a start date should raise."""
    begindatum = "2012-02-20"
    einddatum  = "2012-02-19" # this is logically impossible
    dekking = DekkingInTijdGegevens(
        dekkingInTijdType=BegripGegevens("nvt", VerwijzingGegevens("nvt")),
        dekkingInTijdBegindatum=begindatum,
        dekkingInTijdEinddatum=einddatum,
    )

    with pytest.raises(ValidationError) as err:
        dekking.validate()

    err = str(err.value)
    assert begindatum in err
    assert einddatum in err

def test_invalid_termijn_gegevens():
    """Test if invalid TermijnGegevens objects raise. For rules, see
    https://www.nationaalarchief.nl/archiveren/mdto/termijnEinddatum."""

    # A looptijd without a start date is logically incoherent
    termijn = TermijnGegevens(termijnLooptijd="P20Y")
    with pytest.raises(ValidationError, match="termijnEinddatum.*empty"):
        termijn.validate()

    begindatum = "2012-02-20"
    einddatum  = "2012-02-19"  # this is logically impossible
    termijn = TermijnGegevens(
        termijnStartdatumLooptijd=begindatum, termijnEinddatum=einddatum
    )
    with pytest.raises(ValidationError) as err:
        termijn.validate()

    err = str(err.value)
    assert begindatum in err
    assert einddatum in err

def test_date_validation_error_message():
    """Check if DateValidationError message contains the essential info"""
    checksum = ChecksumGegevens(
        checksumAlgoritme=BegripGegevens("nvt", VerwijzingGegevens("nvt")),
        checksumWaarde="abc123",
        checksumDatum="2024-01-15",  # missing time component
    )
    with pytest.raises(DateValidationError) as err:
        checksum.validate()

    err = str(err.value)
    assert "2024-01-15" in err        # should show offending value
    assert "checksumDatum" in err     # should show incorrect field
    assert "%Y-%m-%dT%H:%M:%S" in err # should show accepted format
