import pytest

from mdto import ValidationError
from mdto.gegevensgroepen import *


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
