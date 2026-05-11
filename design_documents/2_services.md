# Services

Although the model classes have apply_... functions, most of the work to manipulate
the models will be done in the services classes.

## High level summary

A service function will directly call the associated model class(es) to do quick
changes, for example the apply_... functions. These make quick changes and leave the model
object is a "dirty" state - meaning that it as yet needs more work.

By "more work", I mean for example tokenisation, which is slow.
This sort of slow work will be done in a queue (asyncio.Queue).
The queue will have only one worker task, and jobs added to the queue will be processed
in a FIFO manner.

When a model is edited via an apply_... function, its dirty flag will be set to True.
Then the service function will create two jobs.
The first job added to the queue will be to delete the existing semantics associated with
the model object.
The second job will be to re-create the semantics.

This second job could potentially have a problem, because these service
functions will be in response to async calls from the front end as the user is typing away
and creating lots of edit requests in fairly quick succession.
Any of these currently queued, or in progress, could be creating semantics which will be
invalidated by the latest edit.
So if they are queued, they should be cancelled, and if they one is currently running,
it should be stopped.

## Jobs, worker tasks, and the JobQueue

See the file @tests/dockb/services/semantics/README.md
