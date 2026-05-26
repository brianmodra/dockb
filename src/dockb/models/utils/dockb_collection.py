from collections import OrderedDict
from collections.abc import Iterator

from dockb.models.base import DockbModel


class DockbCollection:
    """
    Ordered collection of DockbModel objects.

    - Keyed internally by model.id (like OrderedDict)
    - Preserves insertion order (like a list)
    - Supports append, get, clear, len, enumerate, indexing
    """

    def __init__(self) -> None:
        self._data: OrderedDict[str, DockbModel] = OrderedDict()

    # -------------------------
    # Mutation methods
    # -------------------------

    def append(self, item: DockbModel) -> None:
        key = item.id

        # Upsert without breaking order
        if key in self._data:
            self._data[key] = item
        else:
            self._data[key] = item

    def clear(self) -> None:
        self._data.clear()

    def count(self) -> int:
        return len(self._data)

    # -------------------------
    # Lookup
    # -------------------------

    def get(self, key: str) -> DockbModel | None:
        return self._data.get(key)

    # -------------------------
    # Python protocol support
    # -------------------------

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Iterator[DockbModel]:
        return iter(self._data.values())

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __getitem__(self, index: int) -> DockbModel:
        """
        List-style access by insertion index.
        """
        if not isinstance(index, int):
            raise TypeError("Index must be an integer")

        key = list(self._data.keys())[index]
        return self._data[key]

    def __repr__(self) -> str:
        return f"DockbCollection({list(self._data.values())})"
