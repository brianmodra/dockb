# Editing Design

How will the Front End (FE) send editing requests to the Back End (BE), and how will the BE
support those editing requests?

# Editing sentences

This is the simplest case. Sentences that are edited in the FE will be sent back as whole
sentences to replace the existing sentence.

# Editing Paragraphs

The FE could combine two sentences, or insert a sentence between two existing ones, or split a sentence
into two sentences.

While the user is editing, they likely will be adding incomplete sentences, and they could appeare in a form
(as they type), which is quite different to what the user has in their mind.

For example, if the existing paragraph is:

"The cat sat on the mat. The dog looked at the cat.
Something was about to happen, and it probably would not work out well for the cat."

The user could be intending to add the following between the last two sentences:

"The dog's lips curled, letting out a low growl that mirrored his malevolent stare."

As the user starts typing, the last sentence would become:

"The dog's Something was about to happen, and it probably would not work out well for the cat."

This is unfortunate, but there is no way to avoid it, unless we purposefully delay tokenisation.
This may be a solution later on once this editor gets tested in real life situations, but for now,
we will just live with this.

Up until the point when the user adds a punctuation character to end the sentence, there is no
change to the paragraph - only to the sentence.

However, the new sentence is figured out in the BE, not the FE. From the FE's perspective the sentence
is just a longer one (containing a full stop). The BE will split it into two sentences, and will change
the parent paragraph. The BE will then tell the FE that there is a new sentence before the previous one
and that the text of the long one is changed.

A change to a paragraph is when it gains or loses sentences.

Similarly, a change to a chapter is only when it gains or loses paragraphs.

## Dirty flags

When a model gains children, or loses children, it's not set to dirty,
because the gain or loss is a change to the semantic hierarchy, but it is a complete hierarchy.

## Inserting Children

The model classes need support for inserting children.
The DockbBase has an abstract method insert_child, with an "after" parameter.
