# Character Mentions

## Executive Summary

This note describes how DockB works out which paragraphs of a book mention which characters, and how it remembers the answers so next time the same question is asked, it is easy and quick to answer. The remembered verdicts live as MENTIONS relationships in the graph, in four states that say whether a paragraph was judged, judged to mention nobody, or invalidated by an edit.

The reason it exists: an MCP tool (or any future reader) wants to ask "which paragraphs involve Karakas?" and the honest answer needs to know that "Adams" is sometimes Jael Adams and sometimes Jeremiah's nickname, that "Tobi" is Tobias Mordecai, and that "Mordecai" alone is ambiguous between two characters, Ian and Tobias. A name search alone cannot tell those apart, so deterministic name matching answers what it can and the model judges the rest, asynchronously, while the search reads the settled verdicts straight from the graph.

## 1. The graph: a MENTIONS relationship, and four paragraph states

A mention is stored as a relationship from the paragraph to the character chapter's node, never as a property list:

```
(:Paragraph)-[:MENTIONS {method: "name" | "model", confidence: float}]->(:Chapter)
```

- **A relationship**, because a paragraph can mention several characters and because the search then is a one-hop query.
- **Paragraph granularity**, the unit the tools return, even when a judgement was made from a sentence's context.
- `method` says how the verdict was reached: a deterministic name match, or the model's judgement.

Each paragraph is in exactly one of four states, and every part of the pipeline asks for paragraphs by state:

| State | Meaning | Encoding |
|---|---|---|
| 1 | never evaluated | no `mentions_checked_at` property, no MENTIONS |
| 2 | evaluated, no mentions | `mentions_checked_at` set, no MENTIONS |
| 3 | valid MENTIONS | `mentions_checked_at` set, MENTIONS with `stale` absent or false |
| 4 | invalidated | `mentions_checked_at` set, MENTIONS with `stale: true` |

A paragraph that turns out to mention nobody carries its verdict as **state 2**— the absence of MENTIONS with the stamp set means "checked and none", which is different from "never asked". Stale verdicts are **kept** (marked `stale`) rather than deleted, so state 4 is visible and the old verdict survives until re-judgement replaces it.

**Chapters carry the rollup.** The same MENTIONS relationship runs one level
up, chapter to character — a chapter mentions a character when any of its
paragraphs' valid verdicts do — and is maintained at the same time as the
paragraphs: each paragraph evaluation refreshes its chapter's rollup from the
chapter's valid verdicts, and invalidation (which marks the paragraphs) marks
the chapter's rollup stale with them. The rollup is a view, not a separate
judgement: nothing about a chapter is ever judged that its paragraphs did
not.

## 2. The name set, and the two judgement tiers

A character's **name set** is every string that can count as naming them: `first_name`, `surname`, `first_name + surname`, the full name (first name, middle names, surname joined with spaces), and each nickname. For Jeremiah Edgar Adams (nicknames: Adams, Jer, Jer-bear) that is: *Jeremiah*, *Adams*, *Jer*, *Jer-bear*, *Jeremiah Adams*, *Jeremiah Edgar Adams*.

When the only evidence is **ambiguous** — a name shared by two or more of the document's characters ("Mordecai" could be Tobias or Ian; "Adams" is Jael's surname and Jeremiah's nickname), then after using Tier 1 logic, Tier 2 will be tried, and if it is still not 100% certain, then Tier 3.

**Tier 1 — deterministic.** A paragraph mentions a character when one of the name set's entries appears in it as whole words, matched against the graph's `PROPN` tokens. This settles every unambiguous case and never calls the model.

**Tier 2 — deterministic context.** Within a candidate sentence, the token
sequence may complete a *longer* name-set entry of another character: "Jael"
before "Adams", or "Jeremiah Edgar" before it. At each position of the
sentence, the **longest adjacent-run match** wins, and the defeated shorter
match (the nickname "Adams") creates no verdict for the character it would
have named. A shared name with no longer run to complete it stays unresolved.
Possessive clitics are ignored when matching ("Jael's" names Jael); titles
(Mr, Dr, Inspector) do not disambiguate a shared surname — both characters
answer to "Mr Adams" — so they are left for tier 3.

**Tier 3 — NER, then the model.** First a NER pass (spaCy's entity spans,
already computed by the model the save pipeline loads) runs on the candidate
sentence: a `PERSON` span whose text exactly equals one candidate's name-set
entry resolves that character — deterministically, with no model call. NER is
never a rejector: a name the small model fails to tag as a person ("Tobi",
"Jer-bear" — fiction is exactly where it misses) must not conclude "not a
mention", so everything else falls through. The remainder — shared names with
no completing span, pronouns — are sent to OpenAI in one batched prompt
(numbered sentences, the character's names stated once, JSON verdicts back:
`{"1": true, "2": false, ...}`), and each verdict is written as
`method: "model"`. The key is `OPENAI_API_KEY` from the environment; a missing
key, a network failure, or an unparseable answer is **benign**: the paragraph
simply stays un-evaluated and is retried by the next trigger.

## 3. What invalidates a verdict

| Event | Effect |
|---|---|
| A save changes a paragraph's text | The save's diff already names the changed paragraphs; their verdicts become state 4 and are recomputed. Deleted paragraphs' MENTIONS die with the node. |
| A character's identity changes (name parts, nicknames) | The document's mentions become state 4 — ambiguity is document-wide: Jeremiah losing the nickname "Adams" changes whether "Adams" is ambiguous for Jael. |
| A character chapter is deleted | Its node dies; MENTIONS pointing at it die with it. Nothing dangles. |
| A save that changed nothing relevant, or a restart | Nothing: the verdict is in the database and survives. |

## 4. What triggers an evaluation

- **A manuscript chapter save** enqueues an async **MentionsJob** (the existing job queue, after the CommitJob, because it reads the tokens the commit persisted) scoped to that chapter: it evaluates the chapter's state 1 and state 4 paragraphs.
- **A character chapter save that changed the identity properties** enqueues a **document-wide** MentionsJob (the auto-fix: the ambiguity set is document-wide, so the scope is too).
- **The sweep CLI** — `dockb mentions sweep <document-title-or-id>` — is the operator's manual, once-per-book backfill (and the retry after an outage).
  Default: the document's state 1 and 4 paragraphs, resumable by construction (each paragraph is stamped as it is judged, so an interrupted sweep just continues). `--full`: re-evaluate every paragraph, ignoring existing MENTIONS. It prints per-chapter state counts before, and anything left pending after; it does not run at startup and is never automatic.

## 5. How a search uses it

`find_paragraphs` (the MCP tool; it also takes `include_characters`, which
brings the character chapters' own paragraphs into the search) compiles its
whole criteria tree into one Cypher query (`services/criteria_cypher.py` and
`repositories/paragraph_search_repository.py`): every paragraph's text is
reconstructed in the database, and a character criterion is answered there —
state 2 and 3 paragraphs from their cached verdicts (the MENTIONS
relationships), state 1 and 4 paragraphs by **tier 1 inline** whole-word name
matching. The full evaluation, including tier 2 and tier 3, is enqueued as the
async job whenever the tree reads a character leaf and unevaluated paragraphs
remain, so the next search sees the model's verdicts. A search therefore never
waits on the model, never materializes the manuscript into Python, and its
results self-improve.

## 6. Phase 2 work for later

- **Precision on homographs**: a character nicknamed "Rose" matches the flower. Tier 3 weeds out the obvious ones; a real person-resolution (spaCy NER or the model with the whole document's cast in context) is a later refinement and only touches the pipeline's judgement step.
- **Sentence-level MENTIONS** if a caller ever needs to know *which sentence* of a paragraph carries the mention; the pipeline judges sentences already.
