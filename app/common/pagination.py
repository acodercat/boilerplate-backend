from typing import Any

from sqlalchemy import Select


def paginate[StatementT: Select[Any]](query: StatementT, page: int, page_size: int) -> StatementT:
    """Apply offset/limit pagination. Pages and page sizes below 1 are clamped to 1.

    Build the list's filter once and apply it to both the count query and
    the row query, so the total can never drift from the page.
    """
    page = max(page, 1)
    page_size = max(page_size, 1)
    return query.offset((page - 1) * page_size).limit(page_size)
