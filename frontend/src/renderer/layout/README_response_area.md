# Response area and response syntax

## Executive Summary

This module renders the model's answer to an editor prompt inside the message panel. It exists
because the reply is more than prose: the model can answer with lines of text and clickable
controls, and a control must reach named editor functions with plain data — never executable
code. This document states the reply syntax and what the panel shows while the answer is awaited.

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
the message log. A button naming no registry function renders disabled.

## The function registry

`AppLayoutOptions.responseFunctions` maps the names a reply may name to functions that receive
the button's `args` value. The renderer supplies it; the args are data, so a reply can never run
code. Names and their functions are specified with the functions themselves.

## Security

The reply arrives from the model, i.e. from outside the editor. It never enters the DOM as
markup: labels, text and arg values are set through `textContent`/property assignment only, and
no `eval`, template injection or dynamic HTML touches the response path.
