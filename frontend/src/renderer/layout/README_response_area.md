# Response area and response syntax

## Executive Summary

This module renders interactive prompts and answers inside the message panel's response strip. It
serves three flows through the same strip and function registry: the model's structured reply to a
chat prompt, which pairs lines of text with buttons that open a named chapter and highlight its
sentences; the editor's own prompt when the writer right-clicks selected text, which offers
buttons to mark or clear the touched paragraphs' quote type; and the corrections for a
right-clicked proofreading squiggle, which offer its replacements and Add to dictionary. In every
flow, outside or selected text never enters the DOM as markup, and each button passes plain-data
arguments to a registered editor function. Any new right-click menu belongs here too, in the
strip — never in a floating popover.

When the server attaches its manuscript tools to a chat turn it constrains the model to the
response syntax, so a plain answer arrives as a single text line; without them, or on a refusal,
the reply falls back to the message log and restores the chat box.

## The panel strip

The message panel stacks the message log, the response area, and the chat box. When a prompt is
submitted (`main.ts` → `AppLayout.beginResponse`), the chat box collapses and the strip shows a
one-line busy spinner — the Lucide `loader-circle` icon from `spinner.ts`'s `createSpinner()`,
animated by the shared `spinning-loader` CSS — until the reply arrives. Any other part of the
renderer can reuse `createSpinner()` for its own busy state. Reply buttons carry the shared
`btn btn--secondary` classes so they share the rounded, coloured button styling in `styles.css`.
Charging a reply (`AppLayout.showResponse`) sizes the strip to the response — larger than the
panel and the strip scrolls instead — and the chat box comes back beneath it, empty and focused
for the next prompt. A failed prompt
(`AppLayout.cancelResponse`) drops the strip and restores the chat box; the failure is reported
into the message log as any other error.

## Response syntax

The model's reply is JSON of one of two shapes — a bare array, or an object carrying `"response"`:

```json
{
  "response": [
    { "text": "Hello world!" },
    { "button": { "label": "Highlight sentence", "function": "highlight",
                  "args": { "chapter_id": "...", "paragraph_id": "...", "sentence_id": "..." } } }
  ]
}
```

- `"text"` — a string, displayed as its own line, which may wrap.
- `"button"` — a control with `label` (the caption), `function` (a *name* looked up in the
  registry of available functions) and `args` (an optional JSON value passed to it as data).

`parseResponseReply` accepts a reply only when it parses to that shape: every array member must
be an object carrying a `text` string or a `button` object with string `label` and string
`function`. Anything else parses as null and `main.ts` falls back to appending the raw reply to
the message log and restoring the chat box (`cancelResponse`), so the spinner does not linger
after a plain-prose answer. A button naming no registry function renders disabled.

When the server attaches its MCP tool to a chat turn, it constrains the reply with the Responses
API's strict structured outputs to the object form above, so a plain answer arrives as a single
`text` item. The bare-array form is still accepted because a reply without MCP is unconstrained,
and a refusal or malformed reply still falls back to plain text.

## The function registry

`AppLayoutOptions.responseFunctions` maps the names a reply may name to functions that receive
the button's `args` value. The renderer supplies it; the args are data, so a reply can never run
code. Names and their functions are specified with the functions themselves.

## `highlight` — the registry's first function

`highlight` — its args are `{ "chapter_id": "...", "paragraph_id": "...",
"sentence_indices": [0, ...] }`; the chapter and paragraph ids are required, and
`sentence_indices` hold the 0-based positions of the tool-marked sentences
within the paragraph (an empty or missing list shows the whole paragraph). It
opens the named chapter in the editor when it isn't open already (saving the
dirty open buffer first, exactly a chapter-row click would), scrolls the
paragraph into view, and selects the named sentences as one span as if the
mouse had dragged over them. No second chapter read ever happens: the positions
come from the search tool's marks. While the model is busy the message panel
grows just enough to show the submitted prompt's lines and the spinner; when
the reply arrives it grows to fit the whole reply, capped at half the window
with the strip scrolling beyond that. A button missing either required id, or a
raw-mode editor (the canonical file text, where sentences don't exist as
selections) reports why it did nothing in the message log instead of silently
staying put.

## `quote` — selected-text quote actions in the strip

Right-clicking selected WYSIWYG text reuses the response strip to ask what to do with the
selection (`unquoted`, `quoted as read`, or `quoted as written`, with a 40-character snippet) and
shows the two buttons from `Remove quote`, `Quote read`, and `Quote written` that would change it.
Because the button click happens later, `quote` identifies the paragraphs by their canonical ids
(falling back to their document-order index when an unsaved paragraph has no id yet, so merely
right-clicking never dirties the buffer) rather than by document positions that an intervening edit
would shift. Choosing a button applies the quote type in one transaction and clears the strip;
changing the selection or loading another chapter while the quote prompt is open clears the strip
as well, while an AI reply in the strip stays open across chapter loads and highlights.

## `proofreading-replace` / `proofreading-fix-pair` / `proofreading-add-word` — a squiggle's corrections in the strip

Right-clicking a proofreading squiggle — a WYSIWYG severity squiggle or a raw lint marker — reuses
the strip a third way: a first line names the word and its message, then at most five replacement
buttons, a **Fix “ … ”** button when the diagnostic carries a quote pair, and **Add to dictionary**.
`ProofreadingController` keeps the right-clicked diagnostic, so the buttons carry only the chosen
replacement, the pair, or the word itself. Applying a replacement edits the buffer in one transaction
and re-checks the paragraph; a pair fix rewrites the flagged quote and its partner to matching curly
quotes in one transaction and re-checks; adding a word posts it to *this document's*
glossary (`POST /api/documents/{id}/glossary`) and re-checks, and a glossary failure is reported to the
message log while the strip stays open for another try. Changing the selection, loading another chapter,
or submitting a new AI prompt clears the strip, exactly as with the quote prompt; Escape and outside
clicks do not close it.

**Any right-click menu belongs in the response area.** The strip is the renderer's one surface
for asking "what do you want to do with this?" — one styling, one teardown rule, one place the
writer has already learned — so a new menu reuses it instead of spawning a floating popover with
its own dismissal handling.

## Security

The reply arrives from the model, i.e. from outside the editor. It never enters the DOM as
markup: labels, text and arg values are set through `textContent`/property assignment only, and
no `eval`, template injection or dynamic HTML touches the response path.
