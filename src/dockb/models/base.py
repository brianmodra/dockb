"""Base model class for all dockb document hierarchy objects."""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from dockb.models.utils.dockb_collection import DockbModelBase, InsertionMode

logger = logging.getLogger(__name__)


class OnDeletedListener(ABC):  # pylint: disable=too-few-public-methods
    """Listener interface for model deletion events."""

    @abstractmethod
    def on_deleted(self, model: DockbModelBase) -> bool:
        """
        Gets called when a model is un-parented and scheduled for deletion.
        This method should return True if it handled the event and no other
        listener should be called,
        or False if it either did not handle it, or in any case wants another
        listener to be able to handle the event.
        """


class DataState(Enum):
    """
    The state of a model relative to its database equivalent.
    """

    SYNC = "sync"
    NEW = "new"
    CHANGED = "changed"
    DELETED = "deleted"
    _ = ""  # The "Nothing" state


class DockbModel(DockbModelBase, BaseModel, ABC):
    """Abstract base class for all document hierarchy models."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str = ""
    dirty: bool = False
    state: DataState = DataState._
    _listeners: list[OnDeletedListener] = PrivateAttr(default_factory=list)
    model_config = ConfigDict(populate_by_name=True)

    def model_post_init(self, __context: Any) -> None:  # pylint: disable=arguments-differ
        super().model_post_init(__context)
        from dockb.models.utils.dockb_collection import DockbCollection  # pylint: disable=import-outside-toplevel

        for field_name in self.__class__.model_fields:
            field_value = getattr(self, field_name, None)
            if isinstance(field_value, DockbCollection):
                field_value.set_parent(self)

    def add_on_deleted_listener(self, listener: OnDeletedListener) -> None:
        """Register a listener to be notified when this model is deleted."""
        self._listeners.append(listener)

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

    def set_text(self, text: str) -> None:
        """Replace the full text content of this model."""
        self.dirty = True
        self.text = text
        self.on_changed()

    @abstractmethod
    def clear_semantics(self) -> None:
        """Removes the child hierarchy"""

    @abstractmethod
    def insert_child(self, child: DockbModelBase, insertion_mode: InsertionMode, after: str | None = None) -> None:
        """
        Insert a child in the list of children for this model.

        insertion_mode is either "FIRST" (make this new child the first in the list)
        "LAST" (append it to the list), or "AFTER", insert it after another one.
        after is the ID of another child after which this one will be inserted.
        """

    def append_child(self, child: DockbModelBase) -> None:
        """
        Appends a child to the end of the list of children for this model.
        """
        self.insert_child(child, InsertionMode.LAST)
        self.on_changed()

    def on_deleted(self) -> None:
        """Called when this model is removed from its parent."""
        if self.state == DataState.NEW:
            self.state = DataState._
        else:
            self.state = DataState.DELETED
        for listener in self._listeners:
            if listener.on_deleted(self):
                break

    def on_changed(self) -> None:
        """Called when this model's semantic hierarchy is changed."""
        match self.state:
            case DataState.SYNC:
                self.state = DataState.CHANGED
            case DataState.NEW:
                pass
            case DataState.CHANGED:
                pass
            case DataState.DELETED:
                # This could be a bug, warn about it.
                logger.warning("A previously DELETED model object is being changed")
                self.state = DataState.CHANGED
            case DataState._:
                self.state = DataState.NEW
