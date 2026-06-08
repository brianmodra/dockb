# model hierarchy
The system of models is a hierarchy of classes as follows:

## Document
Document has a list of Chapter objects.
## Chapter
Chapter has a list of Paragraph objects.
## Paragraph
Paragraph has a list of Sentence objects.
## Sentence
Sentence has a list of Token objects.
# Token
A token is either a word or punctuation,
or white space, and white space can be any
combination of one or more spaces, newlines, or
tab character.
A Token will be enumerated as either:
- NUMBER
- WORD
- PUNCTUATION
- EXTENDED
  and the text of the Token will follow the limitations
  imposed by its enumerated type.

A Token does not have a list of any other objects.

A Token can contain trailing whitespace.

When we invoke Language.__call__() using a Language callable from spacy
and call it with a string of text (the sentence), it returns a Doc object which can be
iterated to get all the tokens in it. These are of type spacy.tokens.Token.
Our Token class (dockb.models.Token) is quite similar, except it exists in our
hierarchy, not spacy's.

See the SentenceTokenizer.tokenize method in  @src/dockb/services/semantics/sentence_tokenizer.py
