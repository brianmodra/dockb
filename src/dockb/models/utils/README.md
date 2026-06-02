# List + Dictionary combined with particular dockb features

The main collection class is DockbCollection, but it makes
special use of the DockbModelBase class to keep track of the parent of a model
object.

## DockbModelBase

This has an id (string) and every model (e.g. Sentence) inherits from it.
It stores a weakref-friendly private `_parent` (DockbModelBase) variable,
exposed via `get_parent()` / `set_parent()` methods. Subclasses can override
these to return a tighter type (e.g. `Chapter.get_parent() -> Document | None`).

By default `set_parent()` is a concrete no-op, so root models (like Document)
simply ignore parenting attempts without error.

## Automatic parenting

DockbCollection.append() propagates the collection's parent to the appended
item via `item.set_parent(parent)`.

DockbCollection.set_parent() propagates to all existing items in the
collection when a parent is set, so parenting works retroactively for items
that were added before the collection had a parent.

DockbModel.__setattr__ intercepts DockbCollection field assignments during
construction and calls set_parent() on the collection automatically. This
replaces the older model_post_init loop.
