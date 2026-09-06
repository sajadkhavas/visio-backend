from uuid import uuid4

import pytest
from apps.catalog.api_views import parse_product_ids
from rest_framework.exceptions import ValidationError


def test_catalog_product_ids_accept_valid_uuid_csv_and_deduplicate() -> None:
    first = uuid4()
    second = uuid4()

    result = parse_product_ids(f"{first},{second},{first}")

    assert result == [first, second]


def test_catalog_product_ids_reject_invalid_uuid() -> None:
    with pytest.raises(ValidationError, match="valid UUID"):
        parse_product_ids("not-a-uuid")


def test_catalog_product_ids_reject_more_than_48_values() -> None:
    raw = ",".join(str(uuid4()) for _ in range(49))

    with pytest.raises(ValidationError, match="At most 48"):
        parse_product_ids(raw)
