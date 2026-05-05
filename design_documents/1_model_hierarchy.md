# model hierarchy
The system of models is a hiararcy of classes as so:

## Document
Document has a list of Chapter objects.
## Chapter
Chapter has a list of Paragraph objects.
## Paragraph
Paragraph has a list of Sentence objects.
## Sentence
Sentence has a list of Phrase objects.
# Phrase
Phrase has a list ot Token objects.
# Token
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