# Job

Base class for ReconstructJob and DeleteJob

A Job is an object that can be enqueued into the JobQueue. As the JobQueue steps
through the queued jobs, it will create a worker task for each one, execute it, and then
remove it from the queue.

A job also has a cancel function, which will mark the job as CANCELLED, and iuf it was running at the time,
stop it as quickly and cleanly as possible.

A Job will maintain its own status as: QUEUED, RUNNING, DONE, CANCELLED, or FAILED
A Job will only be run in the queue if its status == QUEUED.

A Job will also have a run function which will do the work, and this run function will be passed to
the create_task function of the JobQueue's asyncio.Queue.
A timeout number of seconds, so that when it is executed, if it is taking too long, then it will be cancelled.
It will store its own id, an uuid, unique and created at construct time.
It will store the result after it is executed.
If there was an error when executing, it will store that.
It will also store the worker task created for it by the JobQueue.

# DeleteJob and ReconstructJob

DeleteJob is for the deletion of semantics, and ReconstructJob is for the reconstruction of semantics.

The objects of these classes will be enqueued to the JobQueue,
and the worker task will be created for the run function of the Job object.

DeleteJob objects will never be cancelled. The DeleteJobs cancel function will throw NotImplemented.

# JobQueue

The JobQueue has an enqueue function to enqueue a Job object, and these Job objects will be
stored in the asyncio.Queue[str] queue.
In addition, it maintains a reconstruct_jobs Dict of ReconstructJob model_ids.
The JobQueue also has a cancel function for cancelling a Job by its uuid. This function will call the
Job object's cancel function.
(When Jobs are in the queue, and come up for execution. if they are status == CANCELLED, then they will be skipped
and removed from the queue.)

Each Job object will be assigned a unique uuid on construction, and this uuid will be the job_id used
when it is added to the asyncio.Queue (using put_nowait(job_id)).
A ReconstructJob will also record the uuid of the model object it is for.
This model uuid will be used when it is added to the reconstruct_jobs Dict. Before being added to the Dict, if there
is an existing entry in the Dict with the same model uuid, then that Job will be cancelled, and
then the new one will be added to the Dict and the queue.
