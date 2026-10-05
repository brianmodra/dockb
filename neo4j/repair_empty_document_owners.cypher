// One-time data repair to run BEFORE `make migrate` on any database holding
// documents created before accounts owned them.
//
// Document ownership is expressed by the *absence* of the `owner` property: an
// unowned document belongs to nobody and is reachable only through
// `dockb users assign`, which matches on that absence. An empty-string owner is
// therefore just a spelling of "nobody" that has to be normalized away, because
// `document_title_key_per_owner` indexes an empty string as a real value -- two
// legacy documents sharing a title would then collide at ("", "opening") and the
// V003 constraint could not be created.
//
// Safe to run repeatedly: it only touches documents that have no owner.
MATCH (d:Document)
WHERE d.owner IS NULL OR d.owner = ''
REMOVE d.owner;