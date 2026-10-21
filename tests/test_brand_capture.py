import pandas as pd

from data_quality import brand_aware_name


def test_brand_is_prefixed_when_the_name_omits_it():
    # Flipp sends name="Frozen Turkey", brand="Butterball" as separate fields.
    # Without the brand, every store's "Frozen Turkey" collapses into one
    # history no matter whose bird it is.
    assert brand_aware_name("Frozen Turkey", "Butterball") == "Butterball Frozen Turkey"


def test_brand_already_present_is_not_repeated():
    assert brand_aware_name("Butterball Frozen Turkey", "Butterball") == "Butterball Frozen Turkey"
    assert brand_aware_name("BUTTERBALL FROZEN TURKEY", "butterball") == "BUTTERBALL FROZEN TURKEY"


def test_missing_or_useless_brand_leaves_the_name_alone():
    assert brand_aware_name("Frozen Turkey", None) == "Frozen Turkey"
    assert brand_aware_name("Frozen Turkey", "") == "Frozen Turkey"
    assert brand_aware_name("Frozen Turkey", "nan") == "Frozen Turkey"


def test_name_is_returned_unchanged_when_blank_brand_and_name():
    assert brand_aware_name("", "Butterball") == "Butterball"
