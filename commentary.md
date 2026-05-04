# How I made this project using AI

## Introduction

The process of software development has been disrupted by tools like
Copilot, Cluade, and Cursor. I also got myself a key and used it with GPT-5,
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
and a stub class "Chapter" with nothing in it (which I'll expand later.)
``` python
class Chapter(DockbModel):
    id: str
```

Then I created a model "Document", which at this stage is not much more than
a stub itself: [src/dockb/models/document.py](https://github.com/brianmodra/dockb/blob/5b19a1cf918d9814d0930e659cd66eca45afebf5/src/dockb/models/document.py)

And here is the test (as it started) [tests/models/test_document.py](https://github.com/brianmodra/dockb/blob/5b19a1cf918d9814d0930e659cd66eca45afebf5/tests/dockb/models/test_document.py)

This is all the coding and documentation I did before I put the LLM to work.