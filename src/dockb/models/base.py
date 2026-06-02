"""Base model class for all dockb document hierarchy objects."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from dockb.models.utils.dockb_collection import DockbModelBase, InsertionMode


class DockbModel(DockbModelBase, BaseModel, ABC):
    """Abstract base class for all document hierarchy models."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    dirty: bool = False
    model_config = ConfigDict(populate_by_name=True)

    def model_post_init(self, __context: Any) -> None:  # pylint: disable=arguments-differ
        super().model_post_init(__context)
        from dockb.models.utils.dockb_collection import DockbCollection  # pylint: disable=import-outside-toplevel

        for field_name in self.__class__.model_fields:
            field_value = getattr(self, field_name, None)
            if isinstance(field_value, DockbCollection):
                field_value.set_parent(self)

    def __setattr__(self, name: str, value: Any) -> None:
        """Prevent direct assignment of lists to DockbCollection fields, and auto-setup parent."""
        from dockb.models.utils.dockb_collection import DockbCollection  # pylint: disable=import-outside-toplevel

        current = self.__dict__.get(name)
        if isinstance(current, DockbCollection) and isinstance(value, list):
            raise ValueError(f"Cannot replace '{name}' directly. " f"Please use '{name}[:] = value' to replace contents.")
        super().__setattr__(name, value)
        if isinstance(value, DockbCollection):
            value.set_parent(self)

    @abstractmethod
    def get_text(self) -> str:
        """Return the full text content of this model."""

    @abstractmethod
    def set_text(self, text: str) -> None:
        """Replace the full text content of this model."""

    @abstractmethod
    def clear_semantics(self) -> None:
        """removes the child hierarchy"""

    @abstractmethod
    def delete_child(self, child_id: str) -> bool:
        """Remove a child model by its ID. Returns True if found and deleted, False otherwise."""

    @abstractmethod
    def insert_child(self, child: DockbModelBase, insertion_mode: InsertionMode, after: str | None = None) -> None:
        """
        Insert a child in the list of children for this model.

        insertion_mode is either "FIRST" (make this new child the first in the list)
        "LAST" (append it to the list), or "AFTER", insert it after another one.
        after is a the ID of another child which this one will be inserted after.
        """
