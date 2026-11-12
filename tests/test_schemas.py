import pytest
from pydantic import ValidationError

from app.schemas.user import UserUpdate


def test_user_update_omitted_field_is_unset():
    assert UserUpdate.model_validate({}).model_dump(exclude_unset=True) == {}


def test_user_update_refuses_explicit_null():
    with pytest.raises(ValidationError):
        UserUpdate.model_validate({"name": None})
