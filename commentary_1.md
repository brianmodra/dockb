# How I made this project using AI

## Why?

In my team in my day job, we use Cursor and Claude
(depending on personal preferences).
I prefer Cursor, and we have `.cursor/skills` set up so that it can read
tickets, refine them, access GitHub, work on tickets, and review tickets.

It all works very well, and it's a lot of fun, but it uses a lot of
tokens, it's expensive, and we are all chewing our fingernails - what
will it be like when costs go up?

## Introduction

The process of software development has been disrupted by tools like
Copilot, Claude, and Cursor. I also got myself a key and used it with GPT-5,
connected to my IDE to see just how expensive it got.
I chewed up $10 in the space of a week...

Then I found OpenCode, which I can use in pay-as-you-go mode,
using their free Big Pickle model.

Using these tools, just watch the agent going through the motions of lots
of internal dialog. That chews tokens. We use them inefficiently.
I have a theory, and I decided to test it: hence this blog.

### Theory?

Don't let the LLM write the tests, or we'll spiral down a vortex
of foolishness.

First write the tests and basic class structure.

This way all the creative work - the architecture, the design, and
the logic will be specified up front.

I.e. "coax the LLM along so it writes good code."

### Don't drink too much HAIpe.

I don't address any of these tools as an actual person with
"please" or "thankyou".

A tool in a machine does not have a soul, is not
conscious, and despite the hype, is not even smart.

But LLMs are useful. Very useful when it comes to languages - and
computer code is a language.

I don't personalise my work with a name like "Claude", which,
by the way means "lame" or "crippled".

## Let's get into it

I started with the Document class, and a test for the class.
The documentation and description of the class will be written
into the test, because the tests will become the "documentation"
for the project. Look at the tests if you want to know how it
works.

I wrote an [AGENT.md](Agent.md) file.

I created a base class:
``` python
class DockbModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
```
a stub class "Chapter" with nothing in it (which I'll expand later.)
``` python
class Chapter(DockbModel):
    id: str
```
and an exception class:
```python
class EditTextRangeError(Exception):
    def __init__(self, message: str, start: int, end:int):
        super(message)
        self.start = start
        self.end = end
```

Then I created a model "Document", which at this stage is not much more than
a stub itself: [src/dockb/models/document.py](https://github.com/brianmodra/dockb/blob/064b094379c9e9966b1734b10ae317ae5c3806b5/src/dockb/models/document.py)

And here is the test (as it started) [tests/models/test_document.py](https://github.com/brianmodra/dockb/blob/064b094379c9e9966b1734b10ae317ae5c3806b5/tests/dockb/models/test_document.py)

This is all the coding and documentation I did before I put the LLM to work.

Following is the prompt I used:

```
I have written a test file for the Document
model: @tests/dockb/models/test_document.py Most fail at present,
because I have not written the body of the function
apply_append_text in @src/dockb/models/document.py .
```
Then I accidentally pressed ENTER, and opencoder just jumped into it.
So that was a very simple prompt. However, it should have been very
obvious what it needed to do.

It fixed a bug I'd written into the exception class (I was calling super()
as if it was super().__init__()).

There was a bug in my test, and it added some automation into the function
which I don't want, so I will fix the text and remove that logic.

Here is the code it created:
[src/dockb/models/document.py](https://github.com/brianmodra/dockb/blob/ce2af56dc5da172925a2f166289bfc3fda6f6faa/src/dockb/models/document.py)

The error was not on the part of Big Pickle, it was my error.
For completeness, here's the test and the class after I fixed them:

[tests/models/test_document.py](https://github.com/brianmodra/dockb/blob/8d80a60ad25de9786e78637c908960450e91fb9c/tests/dockb/models/test_document.py)
[src/dockb/models/document.py](https://github.com/brianmodra/dockb/blob/8d80a60ad25de9786e78637c908960450e91fb9c/src/dockb/models/document.py)
