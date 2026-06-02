import pytest

from dockb.models.base import DockbModel
from dockb.models.utils.dockb_collection import DockbCollection, DockbModelBase, InsertionMode


class FakeModel(DockbModel):
    def get_text(self) -> str:
        return ""

    def set_text(self, text: str) -> None:
        self.dirty = True

    def clear_semantics(self) -> None:
        pass

    def delete_child(self, child_id: str) -> bool:
        return False

    def insert_child(self, child: DockbModelBase, insertion_mode: InsertionMode, after: str | None = None) -> None:
        pass


class FakeCollectionModel(DockbModel):
    items: DockbCollection[FakeModel] = DockbCollection()

    def get_text(self) -> str:
        return ""

    def set_text(self, text: str) -> None:
        self.dirty = True

    def clear_semantics(self) -> None:
        pass

    def delete_child(self, child_id: str) -> bool:
        return False

    def insert_child(self, child: DockbModelBase, insertion_mode: InsertionMode, after: str | None = None) -> None:
        pass


@pytest.fixture
def collection() -> DockbCollection[FakeModel]:
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
        return collection["key"]


def test_repr(collection):
    item = FakeModel()
    collection.append(item)
    assert "DockbCollection" in repr(collection)


def test_assign_list_to_empty_collection(collection):
    items = [FakeModel() for _ in range(3)]
    collection[:] = items
    assert len(collection) == 3
    assert list(collection) == items


def test_assign_list_replaces_existing_items(collection):
    collection.append(FakeModel())
    collection.append(FakeModel())
    new_items = [FakeModel() for _ in range(4)]
    collection[:] = new_items
    assert len(collection) == 4
    assert list(collection) == new_items


def test_extend_adds_multiple_items(collection):
    items = [FakeModel() for _ in range(3)]
    collection.extend(items)
    assert len(collection) == 3
    assert list(collection) == items


def test_extend_preserves_existing_items(collection):
    collection.append(FakeModel())
    new_items = [FakeModel() for _ in range(2)]
    collection.extend(new_items)
    assert len(collection) == 3
    assert list(collection)[0] is collection[0]
    assert list(collection)[1:] == new_items


def test_eq_collection_same_items():
    items = [FakeModel() for _ in range(3)]
    c1: DockbCollection[FakeModel] = DockbCollection()
    c2: DockbCollection[FakeModel] = DockbCollection()
    c1.extend(items)
    c2.extend(items)
    assert c1 == c2


def test_eq_collection_different_items():
    c1: DockbCollection[FakeModel] = DockbCollection()
    c1.append(FakeModel())
    c2: DockbCollection[FakeModel] = DockbCollection()
    c2.append(FakeModel())
    assert c1 != c2


def test_eq_collection_vs_list():
    items = [FakeModel() for _ in range(3)]
    collection: DockbCollection[FakeModel] = DockbCollection()
    collection.extend(items)
    assert collection == items


def test_eq_collection_vs_list_different():
    collection: DockbCollection[FakeModel] = DockbCollection()
    collection.append(FakeModel())
    assert collection != [FakeModel()]


def test_eq_collection_vs_non_collection():
    collection: DockbCollection[FakeModel] = DockbCollection()
    collection.append(FakeModel())
    assert collection != "not a list"
    assert collection != 123


def test_pydantic_validates_list_to_collection():
    model = FakeCollectionModel(items=[{"id": "1"}, {"id": "2"}])  # type: ignore[arg-type]
    assert isinstance(model.items, DockbCollection)
    assert len(model.items) == 2
    assert all(isinstance(item, FakeModel) for item in model.items)


def test_pydantic_serializes_collection_to_list():
    items = [FakeModel() for _ in range(2)]
    collection: DockbCollection[FakeModel] = DockbCollection()
    collection.extend(items)
    model = FakeCollectionModel(items=collection)
    data = model.model_dump()
    assert isinstance(data["items"], list)
    assert len(data["items"]) == 2


def test_collection_knows_parent():
    class FakeModelWithCollection(DockbModel):
        items: DockbCollection[FakeModel] = DockbCollection()

        def get_text(self) -> str:
            return ""

        def set_text(self, text: str) -> None:
            self.dirty = True

        def clear_semantics(self) -> None:
            pass

        def delete_child(self, child_id: str) -> bool:
            return False

        def insert_child(self, child: DockbModelBase, insertion_mode: InsertionMode, after: str | None = None) -> None:
            pass

    doc = FakeModelWithCollection()
    assert doc.items.parent is doc


def test_model_gets_parented_when_added_to_collection():
    parent = FakeCollectionModel()
    child = FakeModel()
    parent.items.append(child)
    assert child.get_parent() == parent


def test_delete_clears_parent():
    parent = FakeCollectionModel()
    child = FakeModel()
    parent.items.append(child)
    assert child.get_parent() == parent
    parent.items.delete(child.id)
    assert child.get_parent() is None


def test_delitem_clears_parent():
    parent = FakeCollectionModel()
    child = FakeModel()
    parent.items.append(child)
    assert child.get_parent() == parent
    del parent.items[child.id]
    assert child.get_parent() is None


def test_clear_clears_parent_on_all_items():
    parent = FakeCollectionModel()
    child1 = FakeModel()
    child2 = FakeModel()
    parent.items.append(child1)
    parent.items.append(child2)
    assert child1.get_parent() == parent
    assert child2.get_parent() == parent
    parent.items.clear()
    assert child1.get_parent() is None
    assert child2.get_parent() is None


def test_delete_removes_item_by_id(collection):
    item = FakeModel()
    collection.append(item)
    assert collection.delete(item.id)
    assert item.id not in collection
    assert len(collection) == 0


def test_delete_returns_false_for_missing_key(collection):
    assert not collection.delete("nonexistent")


def test_delitem_removes_item_by_id(collection):
    item = FakeModel()
    collection.append(item)
    del collection[item.id]
    assert item.id not in collection
    assert len(collection) == 0


def test_delitem_raises_keyerror_for_missing_key(collection):
    with pytest.raises(KeyError):
        del collection["nonexistent"]


def test_insertion_as_the_new_first_element(collection):
    item1 = FakeModel()
    collection.append(item1)
    item2 = FakeModel()
    collection.append(item2)
    item3 = FakeModel()
    collection.append(item3)

    assert len(collection) == 3
    items_before = list(collection.items())
    assert items_before[0] == item1
    assert items_before[1] == item2
    assert items_before[2] == item3

    item4 = FakeModel()
    collection.insert(item4, InsertionMode.FIRST)

    assert len(collection) == 4
    items_after = list(collection.items())
    assert items_after[0] == item4
    assert items_after[1] == item1
    assert items_after[2] == item2
    assert items_after[3] == item3


def test_insertion_as_the_last_element(collection):
    item1 = FakeModel()
    collection.append(item1)
    item2 = FakeModel()
    collection.append(item2)
    item3 = FakeModel()
    collection.append(item3)

    item4 = FakeModel()
    collection.insert(item4, InsertionMode.LAST)

    assert len(collection) == 4
    items_after = list(collection.items())
    assert items_after[0] == item1
    assert items_after[1] == item2
    assert items_after[2] == item3
    assert items_after[3] == item4


def test_insertion_in_the_middle(collection):
    item1 = FakeModel()
    collection.append(item1)
    item2 = FakeModel()
    collection.append(item2)
    item3 = FakeModel()
    collection.append(item3)

    item4 = FakeModel()
    collection.insert(item4, InsertionMode.AFTER, item2.id)

    assert len(collection) == 4
    items_after = list(collection.items())
    assert items_after[0] == item1
    assert items_after[1] == item2
    assert items_after[2] == item4
    assert items_after[3] == item3


def test_insertion_after_the_last(collection):
    item1 = FakeModel()
    collection.append(item1)
    item2 = FakeModel()
    collection.append(item2)
    item3 = FakeModel()
    collection.append(item3)

    item4 = FakeModel()
    collection.insert(item4, InsertionMode.AFTER, item3.id)

    assert len(collection) == 4
    items_after = list(collection.items())
    assert items_after[0] == item1
    assert items_after[1] == item2
    assert items_after[2] == item3
    assert items_after[3] == item4


def test_insertion_after_the_non_existent_key(collection):
    item1 = FakeModel()
    collection.append(item1)
    item2 = FakeModel()
    collection.append(item2)
    item3 = FakeModel()
    collection.append(item3)
    item3 = FakeModel()
    collection.append(item3)

    item4 = FakeModel()
    with pytest.raises(KeyError):
        collection.insert(item4, InsertionMode.AFTER, "this key does not exist")
    with pytest.raises(KeyError):
        collection.insert(item4, InsertionMode.AFTER, "")
    with pytest.raises(KeyError):
        collection.insert(item4, InsertionMode.AFTER, None)
