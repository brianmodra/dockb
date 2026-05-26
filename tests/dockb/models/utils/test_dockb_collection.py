import pytest

from dockb.models.base import DockbModel
from dockb.models.utils.dockb_collection import DockbCollection


class FakeModel(DockbModel):
    def get_text(self) -> str:
        return ""

    def set_text(self, text: str) -> None:
        self.dirty = True

    def clear_semantics(self) -> None:
        pass


@pytest.fixture
def collection() -> DockbCollection:
    return DockbCollection()


def test_append_and_len(collection):
    item = FakeModel()
    collection.append(item)
    assert len(collection) == 1


def test_append_preserves_insertion_order(collection):
    items = [FakeModel() for _ in range(3)]
    for item in items:
        collection.append(item)

    assert list(collection) == items


def test_append_upserts_existing_key_without_duplicating(collection):
    item1 = FakeModel()
    item2 = FakeModel()
    # Force same id to simulate upsert
    item2.id = item1.id

    collection.append(item1)
    collection.append(item2)

    assert len(collection) == 1
    assert collection.get(item1.id) is item2


def test_get_returns_item_by_id(collection):
    item = FakeModel()
    collection.append(item)
    assert collection.get(item.id) is item


def test_get_returns_none_for_missing_key(collection):
    assert collection.get("nonexistent") is None


def test_clear_removes_all_items(collection):
    collection.append(FakeModel())
    collection.append(FakeModel())
    collection.clear()
    assert len(collection) == 0


def test_count_matches_len(collection):
    collection.append(FakeModel())
    collection.append(FakeModel())
    assert collection.count() == 2
    assert collection.count() == len(collection)


def test_iter_yields_items_in_order(collection):
    items = [FakeModel() for _ in range(3)]
    for item in items:
        collection.append(item)
    assert list(collection) == items


def test_contains_with_existing_id(collection):
    item = FakeModel()
    collection.append(item)
    assert item.id in collection


def test_contains_with_missing_id(collection):
    assert "nonexistent" not in collection


def test_getitem_by_integer_index(collection):
    items = [FakeModel() for _ in range(3)]
    for item in items:
        collection.append(item)
    assert collection[0] is items[0]
    assert collection[1] is items[1]
    assert collection[2] is items[2]
    assert collection[-1] is items[2]


def test_getitem_raises_for_non_integer_index(collection):
    collection.append(FakeModel())
    with pytest.raises(TypeError, match="Index must be an integer"):
        collection["key"]


def test_repr(collection):
    item = FakeModel()
    collection.append(item)
    assert "DockbCollection" in repr(collection)
