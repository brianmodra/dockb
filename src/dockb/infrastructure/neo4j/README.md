# Database sessions

This package has a SessionFactory, and UnitOfWork class, and also a Repository base class/mixin
for repository classes in @src/dockb/repositories

## SessionFactory

This owns the neo4j.Driver and produces Session instances, hiding connection details.
It will be created once at app startup with graphite:// URI, auth, and pool config.
It provides a create_session() method returning a context manager so callers get automatic return-to-pool:
The factory creates real sessions. The repository layer never touches the driver.

The SessionFactory will be constructed soon after startup of the app, and it will be closed when
the app shuts down.
The SessionFactory will be passed to the ...Service class which services incoming requests from the
FE via ...Controller, so that when the AsyncReconstructor is run, the UnitOfWork can gets a Session. 

## ...Controller and ...Service

This document uses "...Controller" and "...Service" to mean the DocumentController and associated DocumentService,
ChapterController, ChapterService, ParagraphController, ParagraphService, SentenceController and SentenceService.

## Repository Base Class / Mixin

Avoids repeating the same save() dispatch if dirty → raise logic.
In the repository classes then the only things that vary are:
- The concrete model type
- Whether a parent ID is required (Document: none; Sentence/Paragraph/Chapter: one)
- The Cypher query strings (\_NEW_CYPHER, \_CHANGED_CYPHER, \_DELETE_CYPHER)
- The child serialization method (\_child_to_dict vs \_token_to_dict)

## UnitOfWork

Groups model saves into a single Neo4j transaction, so partial failure rolls everything back.
Maps model type → repository instance (e.g. {Sentence: SentenceRepository(...)}).
The register(model) adds a model to the unit of work.
Opens a session via SessionFactory, wraps all repo.save() calls in a transaction, commits on success.
If any save fails, the transaction is rolled back and tracked changes are discarded.
The UoW holds a list of models whose state == DELETED, ensuring they aren't garbage-collected before the Cypher runs.

During re-parenting, if a Sentence moves from Paragraph A to Paragraph B, the UoW must save both paragraphs
(A loses a child, B gains one) and the sentence itself (its parent changed). Each paragraph is registered with
its own chapter\_id. The sentence is registered with the new paragraph\_id.
This all happens in one transaction, ensuring consistency.

A UnitOfWork will effectively delimit the start and end/commit of a transaction, and the granularity of
that will match a single request from the ...Controller via the ...Service.

### UnitOfWork combined with AsynchronousReconstructor and the dirty flag

Things get complicated because the reconstruction must be done before saving to the database, and:
- reconstruction takes time
- saving to database takes time
(This is done asynchronously on purpose because these time-consuming things should not block the editor,
and editing requests should return quickly back to the FE.)

Due to these asynchronous jobs not being super-quick, it's quite likely that another editing request will
come in for the same model objects while in progress. This could make one of the models dirty again.
If this happens during a reconstruct, that is OK - the reconstruct is interrupted and stopped, replaced with
a new reconstruct job.
However, if it happens while saving to the database, then it will throw.

If the UnitOfWork is constructed by the ...Service when an edit request comes in, and committed when all the jobs
related to the edit have completed, then the UnitOfWork can commit, and afterwards be freed up.
If it gets interrupted by an exception, then we have a problem.
The dirty model can't just be skipped because transactions often will contain many models that must be
committed together.
If one of the models is dirty, then we have to handle it carefully.
Note that as the JobQueue is single threaded, then if the UnitOfWork commit was called from that thread,
and no other mutating database accesses are ever done from any other threads (which is the case),
then we can be certain that no other database modifications could be in progress.

Rather than create the UnitOfWork per ...Service function, we have a UnitOfWorkFactory, which
has a get\_unit\_of\_work() function. That does not necessarily return a new one each time, but as needed.
In fact it will always return the same UnitOfWork until that UnitOfWork's commit completes.
UnitOfWorkFactory will also have a SyncReconstructor which it can provide to the UnitOfWork
when it constructs them. The UnitOfWork will use the SyncReconstructor when its flush_pending() method is called.
UnitOfWorkFactory will also have a SessionFactory, DocCache, and nlp.

The ...Service function will synchronously:
1. construct a CommitJob.
2. All the modified models will be added to the CommitJob as it works on them
3. make modifications to the models (this will cause jobs to be added to the JobQueue, and models to be dirty)
4. It will then add the CommitJob to the queue. 
5. Then it will return

What will happen asynchronously:
1. models will have the semantics reconstructed
2. each job will run.
3. while this is happening, it is possible that one of the models will get zapped by another edit and become dirty
4. finally the CommitJob will be run, it will:
    1. call the UnitOfWorkFactory to get\_unit\_of\_work()
	2. add all the models to the UnitOfWork.
	3. The UnitOfWork will check if any of the models in it are dirty.
	If so, it will throw, which will be caught by the CommitJob which will return and let the JobQueue continue processing
	4. UnitOfWork will issue Cypher commands - if any throw, then return and let the JobQueue continue
	5. UnitOfWork will commit (and this will signal the UnitOfWorkFactory to construct a new UnitOfWork next time
	get\_unit\_of\_work() is called.)
	The next time a CommitJob calls get\_unit\_of\_work(), it will get a new one.

If the CommitJob had exited early (due to UnitOfWork throwing), then the UnitOfWork will retain the models and they will
get committed next time - by the next CommitJob.

However, what if there is not another CommitJob?
The JobQueue will sense that nothing is happening in it after a short period of time, maybe 0.5 second.
When its idle timer triggers, it will call the on\_idle() method on a listener, and the listener
will check the UnitOfWorkFactory - calling its get_current\_unit\_of\_work().
The get_current\_unit\_of\_work() function will return None if the previous one was committed successfully.
If it is not None, then that pending UnitOfWork will have its flush_pending() method called,
which will synchronously reconstruct any dirty models, and then commit.
The "listener" in this case is the IdleFlushListener, which will be created from a factory.

### Deleted-model validation in commit() vs flush_pending()

The following rules apply to the `UnitOfWork` class only.

`commit()` applies **strict** validation to the `_deleted` list — if a model's
state has changed since `register()` was called, or if it is still dirty, the
commit raises `ValueError`. This ensures the caller (e.g. a `CommitJob`) catches
stale registrations early.

`flush_pending()` applies **lenient** rules: it skips models whose state no
longer matches `DELETED` (they may have been resurrected by a subsequent edit),
and saves even dirty models to the database (deletion is unconditional). When a
model is skipped from `_deleted` because its state has changed, `flush_pending()`
**auto-promotes** it to the correct list (`_new` or `_changed`) based on its
current `DataState`, ensuring it is not silently dropped.

`flush_pending()` never calls the reconstructor on DELETED models — reconstruction
is meaningless for deletion. It handles `_deleted` directly, clears the list,
then delegates `_new` and `_changed` to `commit()`.

| Scenario | `commit()` | `flush_pending()` |
|---|---|---|
| DELETED, not dirty | Saves via repo | Saves via repo |
| DELETED, dirty | Raises `ValueError` | Saves via repo (lenient) |
| State changed to CHANGED | Raises `ValueError` | Skips, auto-promotes to `_changed` |
| State changed to NEW | Raises `ValueError` | Skips, auto-promotes to `_new` |
