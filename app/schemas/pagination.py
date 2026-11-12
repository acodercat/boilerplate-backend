from pydantic import BaseModel


class PaginationMeta(BaseModel):
    total: int
    page: int
    page_size: int


class PaginatedResponse[ItemT](BaseModel):
    items: list[ItemT]
    meta: PaginationMeta
