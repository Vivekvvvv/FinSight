"""`backend.utils.pydantic_numeric` 的行为约束。"""

from typing import Annotated, Optional

import pytest
from pydantic import Field, ValidationError

from backend.utils.pydantic_numeric import (
    RejectBooleanNumbers,
    is_numeric_annotation,
    numeric_input_keys,
)


class _Sample(RejectBooleanNumbers):
    name: str = "AAPL"
    count: int = 1
    ratio: float = 1.0
    optional_count: Optional[int] = None
    piped_count: int | None = None
    annotated_count: Annotated[int, Field(ge=0)] = 0
    flag: bool = False
    aliased: int = Field(default=0, alias="outer_alias")


@pytest.mark.parametrize(
    "annotation",
    [int, float, Optional[int], Optional[float], int | None, Annotated[int, Field(ge=0)]],
)
def test_is_numeric_annotation_accepts_numeric_shapes(annotation):
    assert is_numeric_annotation(annotation) is True


@pytest.mark.parametrize("annotation", [bool, str, Optional[bool], Optional[str], list[int], dict])
def test_is_numeric_annotation_rejects_non_numeric_shapes(annotation):
    assert is_numeric_annotation(annotation) is False


def test_numeric_input_keys_covers_fields_and_aliases():
    keys = numeric_input_keys(_Sample)

    assert {"count", "ratio", "optional_count", "piped_count", "annotated_count"} <= keys
    assert "outer_alias" in keys, "别名也要挡，否则按别名传 bool 就绕过了"
    assert "flag" not in keys
    assert "name" not in keys


@pytest.mark.parametrize(
    "field",
    ["count", "ratio", "optional_count", "piped_count", "annotated_count"],
)
def test_boolean_is_rejected_for_numeric_fields(field):
    with pytest.raises(ValidationError):
        _Sample(**{field: True})


def test_boolean_is_rejected_through_alias():
    with pytest.raises(ValidationError):
        _Sample(outer_alias=True)


def test_real_numbers_and_boolean_flags_still_work():
    instance = _Sample(count=3, ratio=2.5, optional_count=7, flag=True, outer_alias=9)

    assert (instance.count, instance.ratio, instance.optional_count) == (3, 2.5, 7)
    assert instance.flag is True
    assert instance.aliased == 9


def test_non_dict_payload_passes_through_untouched():
    """model_validate 收到非 dict 时不该炸，交给 Pydantic 自己报错。"""
    with pytest.raises(ValidationError):
        _Sample.model_validate(["not", "a", "dict"])


def test_numeric_keys_are_cached_per_model():
    first = numeric_input_keys(_Sample)
    second = numeric_input_keys(_Sample)

    assert first is second
