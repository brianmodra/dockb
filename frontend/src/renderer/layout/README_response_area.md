# Response area and response syntax

## Executive Summary

This module renders the model's answer to an editor prompt inside the message panel. It exists
because the reply is more than prose: the model can answer with lines of text and clickable
controls — a control opening the paragraph it names — and a control must reach named editor
functions with plain data, never executable code. This document states the panel's spinner and
sizing behaviour, the reply syntax, the `highlight` function, and the guard that keeps outside
text out of the DOM.

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

## Security

The reply arrives from the model, i.e. from outside the editor. It never enters the DOM as
markup: labels, text and arg values are set through `textContent`/property assignment only, and
no `eval`, template injection or dynamic HTML touches the response path.
