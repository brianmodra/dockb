# So far so good...

Now I have the Document model created by the LLM. It was easy. It took me
a lot longer to write this commentary, than it did to write the code and set
the LLM working.

It worked well. The process so far is good, with a caution: make sure
you write good tests.

# What next?

I plan to make the services and then the controllers,
the NLP code that will work out the semantics of the
text (in a queue). Then also the integration with repositories
to Neo4J... and then the front end.

Initially though, the rest of it will need all the
models. I will write the classes with empty functions,
I'll write the tests, and this time use a better prompt.

I started to fill out the Chapter class with empty
functions, and created a very empty Paragraph class,
then realised that teh LLM can create the other classes
for me because they are basically carbon copies.

Similarly, I can get it to create the tests... Hmmm.
I said we should not let the LLM create tests, but my
prompt will tell it to create the classes using the
same ideas as in Document, and then get it to duplicate
the tests for the new classes. They will be the same as
the tests I created. I'm just getting it to do the
duplication.

The following started as a prompt, then became a
design document:
```
The system of models is a hiararcy of classes as so:

Document has a list of Chapter objects.

Chapter has a list of Paragraph objects.

Paragraph has a list of Sentence objects.

Sentence has a list of Phrase objects.

Phrase has a list ot Token objects.

A token is either a word, or punctuation,
or white space, and white space can be any
combination of one or more space, newline, or
tab character.
A Token will be enumerated as either:
- TOKEN_IS_WORD
- TOKEN_IS_PUNCTUATION
- TOKEN_IS_WHITESPACE
and the text of the Token will follow the limitations
imposed by its enumerated type.

A Token does not have a list of any other objects.
```
So I coped that into a file in the design_documents
directory. Then I referenced it in the prompt.
```
Read the file @design_documents/1_model_hierarchy.md
I have already created @src/dockb/models/document.py
and I have created @src/dockb/models/chapter.py but
with empty functions. I have also created 
@src/dockb/models/paragraph.py which does not yet have any
functions.
Fill out @src/dockb/models/paragraph.py with empty functions.
Create also Sentence, and Phrase classes using the similar pattern,
but only with empty functions for now.

Create also a test_chapter.py. test_paragraph.py, test_sentence.py,
and test_phrase.py.Use the same structure as test_document.py.
You can do so because the functions in all the classes are identical.

Don't fill out the logic in the new model classes yet. I want to first
check all the tests, and in fact I may modify them, and the model 
classes.
```
That worked very well. I created an almost empty Token class, then,
because I'm lazy, I asked it to create me the enum class as per
the docs:
```
Read the file @design_documents/1_model_hierarchy.md and take note of
how it explains that a Token has an enumerated type.
Create that enum, inside the unfinmished class file
@src/dockb/models/token.py, modify the class so that it has an enumerated
type, but don't attempt to create any new functions.
```
Then I created a stub Token class with comments, and wrote the test_token.py
and prompted it to fill in the blanks.

This worked very well, took hardly any time, except the time I spent writing up the
description of the Token class. I admit that I changed the design of the Token class
half-way through and asked the LLM to fix up the documentation and the tests.
And I was saying, "Don't let the LLM write tests". However, if you watch closely
what it is creating, it is OK. This is an exception to my rule though, which I am
happy to state later one once I've (hopefully) proven my theory. So far, it's
working out great.