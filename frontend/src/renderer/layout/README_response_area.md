# Response area and response syntax

## Executive Summary

This module renders interactive prompts and answers inside the message panel's response strip. It
serves four flows through the same strip and function registry: the model's structured reply to a
chat prompt, which pairs lines of text with buttons that open a named chapter and highlight its
sentences; the editor's own prompt when the writer opens a menu over selected text (by right-click
or Enter), which offers buttons to change the selection's inline formatting and, for a
whole-paragraph selection, its quote layout; the corrections for a proofreading squiggle (opened by
right-click or Enter), which offer its replacements and Add to dictionary; and the signed-in
user's menu, opened from the menubar username, which offers Sign out and Settings. The selection,
squiggle, and user menus are keyboard-navigable — focus moves to the first button, arrow keys move
the highlight, Enter activates it, and Escape closes the menu and returns focus to the editor. In
every flow, outside or selected text never enters the DOM as markup, and each button passes
plain-data arguments to a registered editor function. Any new editor menu belongs here too, in the
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

## Menu keyboard navigation

The selection, squiggle, and user menus share one keyboard model, implemented in
`AppLayout.showMenu`/`closeMenu` and `ResponseArea.showMenu`. When a menu appears, focus moves to
its first button — highlighted, not clicked, exactly as a mouse hover highlights it. The left and
right arrow keys move the highlight between buttons, clamped at each end; Enter activates the
highlighted button; and Escape, or activating any button, closes the menu and returns focus to the
editor. An AI chat reply is *not* a menu: its buttons neither take focus nor react to the arrow
keys, so the writer can keep typing in the chat box.

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

## `quote` — whole-paragraph quote actions in the strip

The selected-text menu adds **Quote para "reading"** and **Quote para "writing"** — filtered to the
one that would actually change the paragraph — only when the selection covers a whole paragraph (or
all but one character of it). Each button's args carry the target `layout` as `{ kind, variant }`,
so a quoted paragraph is always `kind: "quoted"` with a `reading`/`writing` variant and the normal
layout is `{ kind: "normal", variant: "" }`. Because the button click happens later, `quote`
identifies the paragraphs by their canonical ids (falling back to their document-order index when
an unsaved paragraph has no id yet, so merely opening the menu never dirties the buffer) rather
than by document positions that an intervening edit would shift. Choosing a button applies the
layout in one transaction and closes the menu; changing the selection or loading another chapter
while a menu is open closes it as well, while an AI reply in the strip stays open across chapter
loads and highlights.

## `format` — selected-text formatting in the strip

Opening the menu over selected WYSIWYG text (right-click, or Enter with a selection) asks
`What do you want to do with this text: "…"` with a 40-character snippet, then offers the formatting
buttons — **Italic**, **Bold**, **Underline**, **Monospace**, **Normal font**, **Large**, **Small**,
**Normal size**, and **Clear formatting** — and, when the selection is a whole paragraph, the two
quote buttons (above). Each formatting button's args are `{ changes }`, a partial `FormatAttrs`
object (`style`, `weight`, `family`, `size`). The editor merges those changes into the selection's
existing format and applies one `format` mark in one transaction; **Normal font** clears the
`style`/`weight`/`family` overrides (leaving the size), **Normal size** sets `size` to `1em`, and
**Clear formatting** resets everything. `applyFormat` re-checks every value before touching the
buffer, because the args come from the response strip as plain data, and refuses sizes that are not
a positive `em` value.

## `proofreading-replace` / `proofreading-fix-pair` / `proofreading-add-word` — a squiggle's corrections in the strip

Right-clicking a proofreading squiggle — a WYSIWYG severity squiggle or a raw lint marker — reuses
the strip a third way: a first line names the word and its message, then at most five replacement
buttons, a **Fix “ … ”** button when the diagnostic carries a quote pair, and **Add to dictionary**.
Pressing Enter with the caret inside a squiggle opens the same menu (WYSIWYG only; the raw lint
menu is right-click only). `ProofreadingController` keeps the open diagnostic, so the buttons carry
only the chosen replacement, the pair, or the word itself. Applying a replacement edits the buffer
in one transaction and re-checks the paragraph; a pair fix rewrites the flagged quote and its
partner to matching curly quotes in one transaction and re-checks; adding a word posts it to *this
document's* glossary (`POST /api/documents/{id}/glossary`) and re-checks, and a glossary failure is
reported to the message log while the strip stays open for another try. Changing the selection,
loading another chapter, submitting a new AI prompt, or pressing Escape closes the menu, the last
returning focus to the editor.

**Any editor menu belongs in the response area.** The strip is the renderer's one surface
for asking "what do you want to do with this?" — one styling, one teardown rule, one place the
writer has already learned — so a new menu reuses it instead of spawning a floating popover with
its own dismissal handling.

## `user-sign-out` / `user-settings` — the user's menu in the strip

The signed-in username in the menubar is a button: clicking it shows **Sign out** and **Settings**
in the strip (`AppLayout.showUserMenu`), as a keyboard-navigable menu like the others. **Sign out**
runs the same unsaved-buffer-then-logout flow the old File → Sign out entry did; **Settings** opens
the user-settings modal (the "Enable raw markdown mode" checkbox). Escape closes the menu and
returns focus to the editor, exactly as with the other menus.

## Security

The reply arrives from the model, i.e. from outside the editor. It never enters the DOM as
markup: labels, text and arg values are set through `textContent`/property assignment only, and
no `eval`, template injection or dynamic HTML touches the response path.
