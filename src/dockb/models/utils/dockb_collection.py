"""Ordered collection of DockbModel objects keyed by ID with insertion order."""

from __future__ import annotations

import weakref
from collections import OrderedDict
from collections.abc import Iterator, Sequence
from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema


class DockbModelBase:  # pylint: disable=too-few-public-methods
    """Lightweight base interface for items in a DockbCollection."""

    id: str
    _parent: DockbModelBase | None = None

    def get_parent(self) -> DockbModelBase | None:
        """Return the parent model, or None."""
        return self._parent

    def set_parent(self, parent: DockbModelBase | None) -> None:
        """Set the parent model. No-op by default for root models."""
        self._parent = parent


class InsertionMode(Enum):
    """Where to insert an item in the collection."""

    FIRST = "first"
    LAST = "last"
    AFTER = "after"


T = TypeVar("T", bound=DockbModelBase)


class DockbCollection(Generic[T]):
    """
    Ordered collection of DockbModel objects.

    - Keyed internally by model.id (like OrderedDict)
    - Preserves insertion order (like a list)
    - Supports append, get, clear, len, enumerate, indexing
    """

    def __init__(self) -> None:
        self._data: OrderedDict[str, T] = OrderedDict()
        self._parent: weakref.ReferenceType[Any] | None = None

    def set_parent(self, parent: Any) -> None:
        """Set the parent model that contains this collection, and propagate to items."""
        self._parent = weakref.ref(parent)
        for item in self._data.values():
            item.set_parent(parent)

    @property
    def parent(self) -> Any | None:
        """Return the parent model that contains this collection, or None."""
        return self._parent() if self._parent else None

    # -------------------------
    # Mutation methods
    # -------------------------

    def append(self, item: T) -> None:
        """
        Add or update an item, preserving insertion order.
        """
        key = item.id

        # Upsert without breaking order
        if key in self._data:
            self._data[key] = item
        else:
            self._data[key] = item

        if self._parent is not None:
            item.set_parent(self.parent)

    def extend(self, items: Sequence[T]) -> None:
        """Add multiple items to the collection, preserving insertion order."""
        for item in items:
            self.append(item)

    def clear(self) -> None:
        """Remove all items from the collection, un-parenting each."""
        for item in self._data.values():
            item.set_parent(None)
        self._data.clear()

    def delete(self, key: str) -> bool:
        """Remove the item with the given ID. Returns True if found and deleted, False otherwise."""
        if key in self._data:
            item = self._data.pop(key)
            item.set_parent(None)
            return True
        return False

    def items(self) -> Iterator[T]:
        """Return an iterator over the items in insertion order."""
        return iter(self._data.values())

    def insert(self, item: T, insertion_mode: InsertionMode, after: str | None = None) -> None:
        """
        Insert an item in the list.

        insertion_mode is either "FIRST" (make this new item the first in the list)
        "LAST" (append it to the list), or "AFTER", insert it after another one.
        after is a the key of another item which this one will be inserted after.
        """
        if insertion_mode == InsertionMode.FIRST:
            new_data: OrderedDict[str, T] = OrderedDict()
            new_data[item.id] = item
            new_data.update(self._data)
            self._data = new_data
        elif insertion_mode == InsertionMode.LAST:
            self.append(item)
            return
        elif insertion_mode == InsertionMode.AFTER:
            if after is None or after not in self._data:
                raise KeyError(f"Key {after!r} not found in collection")
            new_data = OrderedDict()
            for key, value in self._data.items():
                new_data[key] = value
                if key == after:
                    new_data[item.id] = item
            self._data = new_data

        if self._parent is not None:
            item.set_parent(self.parent)

    def count(self) -> int:
        """Return the number of items in the collection."""
        return len(self._data)

    # -------------------------
    # Lookup
    # -------------------------

    def get(self, key: str) -> T | None:
        """Return the item with the given ID, or None if not found."""
        return self._data.get(key)

    # -------------------------
    # Python protocol support
    # -------------------------

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Iterator[T]:
        return iter(self._data.values())

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __delitem__(self, key: str) -> None:
        item = self._data.pop(key)
        item.set_parent(None)

    def __getitem__(self, index: int) -> T:
        """
        List-style access by insertion index.
        """
        if not isinstance(index, int):
            raise TypeError("Index must be an integer")

        key = list(self._data.keys())[index]
        return self._data[key]

    def __setitem__(self, index: int | slice, value: T | Sequence[T]) -> None:
        if isinstance(index, slice):
            if index != slice(None):
                raise NotImplementedError("Only full slice assignment is supported")
            self.clear()
            if isinstance(value, Sequence):
                for item in value:
                    self.append(item)
            return
        raise NotImplementedError("Single item assignment by index is not supported")

    def __repr__(self) -> str:
        return f"DockbCollection({list(self._data.values())})"

    def __eq__(self, other: Any) -> bool:
        """Check equality with another DockbCollection or a list of items."""
        if isinstance(other, DockbCollection):
            return list(self) == list(other)
        if isinstance(other, list):
            return list(self) == other
        return False

    # -------------------------
    # Pydantic Integration
    # -------------------------

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        """Tells Pydantic how to validate a list into a DockbCollection."""
        origin = getattr(source_type, "__origin__", None)
        if origin is not None:
            args = getattr(source_type, "__args__", ())
            inner_type = args[0] if args else Any
        else:
            inner_type = Any

        inner_schema = core_schema.any_schema() if inner_type is Any else handler.generate_schema(inner_type)

        return core_schema.no_info_after_validator_function(
            cls.from_list,
            core_schema.list_schema(inner_schema),
            serialization=core_schema.plain_serializer_function_ser_schema(list),
        )

    @classmethod
    def from_list(cls, items: Sequence[T]) -> DockbCollection[T]:
        """Helper to create a collection from a validated list."""
        instance = cls()
        for item in items:
            instance.append(item)
        return instance
