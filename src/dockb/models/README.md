# model hierarchy

## Executive Summary

This note is the map of DockB's text model. A document holds chapters, a chapter holds paragraphs, a paragraph holds sentences, and a sentence holds tokens. Read it to see how a manuscript is split into pieces the rest of the system can store and edit.

A token is a word, punctuation, or whitespace carrying its own inline formatting. A paragraph also carries a structured layout (normal or quoted, reading or writing) and temporary formatting runs that are folded onto tokens when the text is tokenized. The classes themselves live in this directory; this file only names the hierarchy.

The system of models is a hierarchy of classes as follows:

## Document
Document has a list of Chapter objects.
## Chapter
Chapter has a list of Paragraph objects.
## Paragraph
Paragraph has a list of Sentence objects.

A paragraph's layout is `layout_kind` (`normal` or `quoted`) plus
`layout_variant` (`reading` or `writing` for a quote, empty for normal).
`format_runs` is a transient list of character-range formatting runs over the
paragraph text; hydration slices it onto the paragraph's sentences, and
tokenization folds each sentence's runs onto whole tokens.
## Sentence
Sentence has a list of Token objects.

`format_runs` is transient: it carries formatting for a sentence that has not
yet been tokenized, then is cleared once the runs are applied.
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

A Token also stores inline formatting: `style` (italic, underline, normal),
`weight` (bold, normal), `family` (monospace), and `size` (an `em` value).
An empty value means the token inherits; an explicit `normal` overrides an
inherited style. Formatting is whole-token, and a run that touches a token's
trailing whitespace covers that token too.

When we invoke Language.__call__() using a Language callable from spacy
and call it with a string of text (the sentence), it returns a Doc object which can be
iterated to get all the tokens in it. These are of type spacy.tokens.Token.
Our Token class (dockb.models.Token) is quite similar, except it exists in our
hierarchy, not spacy's.

See the SentenceTokenizer.tokenize method in  @src/dockb/services/semantics/sentence_tokenizer.py
