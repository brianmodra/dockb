# Restructure

When I started this, I left a comment in the Document model class:
```python
# The entire document is stored in the text parameter. (This may change later.)
```
The question is, "Which model class will be the point at which the text is
no longer stored, and where the semantic structure alone stores the text?"

I had a few options:
1. Only the Sentence model
2. Only the Token model
3. Only permanently in the Token, temporarily everywhere else.

I chose 3.
I.e. that during an apply_... function call, the text is first rebuilt from the children,
edited, and then removed again after the semantic representation has been rebuilt.

For the purpose of NLP, the tokens are important (and they will be expanded with more
properties.) For the purpose of NLP, the only hierarchy of the document I need to store is
Document -> Chapter -> Paragraph -> Sentence -> Token. Phrase is unnecessary. So I will
remove it.
I used teh following prompt:
```
In the hierachy of the model classes, we currently have:
Document has Chapters,
Chapters have Paragraphs,
Paragraphs have Sentences,
Sentences have Phrases,
Phrases have Tokens.

I want you to change the hierachy to:
Document has Chapters,
Chapters have Paragraphs,
Paragraphs have Sentences,
Sentences have Tokens.

Change the classes (specifically the Sentence class) so that Phrases are skipped
from the hierarchy.

I want to remove the Phrase class and its tests and all associated documentation
i.e. remove:
@tests/dockb/models/test_phrase.py
@src/dockb/models/phrase.py
and edit @design_documents/1_model_hierarchy.md
```
