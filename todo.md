When a character chapter's names are changed, then the document-wide mentions job will need to be automatically started
using an async function because the character chapter save must not be slow.
This should use the existing task running logic (in the single threaded queue) except that the job will be for the whole document rather than
a single chapter. It will use the same type of logic so that if the same character chapter spawns another task while the first (for the same character chapter) is still running, the first
should be cancelled.
Also, any time a character chapter is saved does not mean the document-wide character mentions job should be run, but only if the names of that character were changed.

