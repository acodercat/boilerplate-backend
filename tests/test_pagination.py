import pytest
from sqlalchemy import select

from app.common.pagination import paginate
from app.models import User


@pytest.mark.parametrize(
    ("page", "page_size", "expected"),
    [
        (1, 20, "LIMIT 20 OFFSET 0"),
        (3, 10, "LIMIT 10 OFFSET 20"),
        (0, 10, "LIMIT 10 OFFSET 0"),
        (-5, 0, "LIMIT 1 OFFSET 0"),
    ],
)
def test_paginate_clamps_and_offsets(page, page_size, expected):
    sql = str(
        paginate(select(User), page, page_size).compile(compile_kwargs={"literal_binds": True})
    )
    assert sql.endswith(expected)
