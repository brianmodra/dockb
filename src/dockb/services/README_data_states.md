# Data States

The "data state" is a model object's state relative to the database.

## NEW State

The "new" state is when the model was created in memory, it has become part of a semantic hierarchy,
but has not been added to the database yet.

## SYNC State

This is when the model does exist in the database, but it has not been changed or deleted.

## CHANGED State

This is the case when something in the model has changed relative to how it is stored in the database.
"Change" will include a change in hierarchy (e.g. more or less children, or a different child,
or a different parent). How would a child be re-parented? As an example, when a sentence which was at
the start of a paragraph is moved to the end of the preceding paragraph.
Change will not be flagged when one of the children is changed, but still remains in the same position
in the hierarchy.

## DELETED State

When a model exists in the database, but it has been un-parented in memory, then it will have the 
state of "deleted".

Note that when a model object is unparented, it likely will have a reference count of zero,
which means it may be garbage collected. This would be a bug, because we'd never know to delete it from
the database. Hence, when the data state of a model changes, the model needs to be added to a list
of objects to be deleted.

## Nothing state

This is the initial value of the state of a model object, and it is also its state
if its state was NEW and it got un-parented. When un-parented, a model would
normally become DELETED, but if it was previously NEW, then it will become Nothing,
because it does not need to be deleted from the database - it does not exist in the
database.
The Nothing state in code is "_"

## Data State Deleted List

This list obviously can't be part of the models themselves. It is completely abstracted
from the models. The models 

## The data state enum

These data states are represented by an enum called DataState and defined in the
@src/dockb/models/base.py file.

## Automatically setting the state

When a model is un-parented, then its state will become DELETED, unless it was
previously NEW, in which it becomes _ (Nothing)

In any of the cases below which represent semantic hierarchy changes,
its state becomes CHANGED, unless it was previously NEW, in which case it remains NEW.
- it is reparented
- any of its children are removed
- one or more children are added
- the order of its children are changed

A model becomes NEW when it has been created and receives data, either text or children.


