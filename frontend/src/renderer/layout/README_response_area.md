# Response area and response syntax

## Executive Summary

This module renders the model's answer to an editor prompt inside the message panel. A reply is
more than prose: it can carry lines of text and clickable controls that open the paragraph they
name, so the module parses the response syntax, renders it without letting outside text into the
DOM as markup, and passes a control's plain-data arguments to a named editor function. When the
server attaches its manuscript tools to a chat turn it also constrains the model to that syntax,
so a plain answer arrives as a single text line; without them, or on a refusal, the reply falls
back to plain text.

## The panel strip

The message panel stacks the message log, the response area, and the chat box. When a prompt is
submitted (`main.ts` → `AppLayout.beginResponse`), the chat box collapses and the strip shows a
one-line busy spinner until the reply arrives. Charging a reply (`AppLayout.showResponse`) sizes
the strip to the response — larger than the panel and the strip scrolls instead — and the chat
box comes back beneath it, empty and focused for the next prompt. A failed prompt
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

Right-clicking selected WYSIWYG text reuses the same response strip: `selectionActionObjects`
builds a prompt line `What do you want to do with this <state> text: "<snippet>"` (`unquoted`,
`quoted as read`, or `quoted as written`, with the collapsed text truncated after 40 characters
plus `…`) followed by the two buttons from `Remove quote`, `Quote read`, and `Quote written` that
do not match the current state. Each button calls `quote` with `{ quote_type, paragraph_ids,
paragraph_indexes, start, end, text }`; `quote` clears the strip and delegates to
`EditPanel.applyQuote`, which marks or clears the touched paragraphs by id (or index when an
unsaved paragraph has no id yet) and logs why if the editor is in raw mode.

## Security

The reply arrives from the model, i.e. from outside the editor. It never enters the DOM as
markup: labels, text and arg values are set through `textContent`/property assignment only, and
no `eval`, template injection or dynamic HTML touches the response path.
