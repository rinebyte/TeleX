from typing import TypedDict


class GroupData(TypedDict):
    id: int
    title: str
    username: str
    members: int


class SavedGroup(TypedDict):
    id: int
    title: str
    username: str | None
    joined_at: str
