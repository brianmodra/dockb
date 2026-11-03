/** The chapter header line: the front matter's identity, shown read-only atop the editor. */

export interface ChapterFrontMatterFields {
  title?: string;
  category?: string;
  pov?: string;
  firstName?: string;
  middleNames?: string[];
  surname?: string;
  nicknames?: string[];
  age?: string;
  location?: string;
}

/**
 * The header-relevant fields of a chapter file's front matter.
 *
 * The editor carries no YAML parser, and the fields it must show are simple
 * `key: value` lines — strings, integers, and bracketed `[a, b]` lists — so a
 * line-level read of the front-matter block is enough. Anything the raw view
 * shows in full; this only feeds the un-editable header line.
 */
export function frontMatterFields(buffer: string): ChapterFrontMatterFields {
  if (!buffer.startsWith("---")) {
    return {};
  }
  const lines = buffer.split("\n").slice(1);
  const fields: ChapterFrontMatterFields = {};
  for (const line of lines) {
    if (line.startsWith("---")) {
      break;
    }
    const separator = line.indexOf(":");
    if (separator === -1) {
      continue;
    }
    const key = line.slice(0, separator).trim();
    const value = line.slice(separator + 1).trim();
    if (key === "title" || key === "category" || key === "pov") {
      fields[key] = value || undefined;
    } else if (key === "first_name") {
      fields.firstName = value || undefined;
    } else if (key === "surname") {
      fields.surname = value || undefined;
    } else if (key === "age") {
      fields.age = value || undefined;
    } else if (key === "location") {
      fields.location = value || undefined;
    } else if (key === "middle_names") {
      fields.middleNames = parseList(value);
    } else if (key === "nicknames") {
      fields.nicknames = parseList(value);
    }
  }
  return fields;
}

function parseList(value: string): string[] | undefined {
  const inner = value.replace(/^\[/, "").replace(/\]$/, "").trim();
  if (inner === "") {
    return [];
  }
  return inner.split(",").map((entry) => entry.trim());
}

/** The character chapter's one prose line, from whatever name parts are set. */
export function characterHeaderText(fields: ChapterFrontMatterFields): string {
  const name = [fields.firstName, ...(fields.middleNames ?? []), fields.surname].filter((part) => part).join(" ");
  let line = name;
  if (fields.nicknames?.length) {
    line = `${line}${line ? ", " : ""}known as ${fields.nicknames.join(", ")}`;
  }
  if (fields.age) {
    line = `${line}${line ? " — " : ""}${fields.age}`;
  }
  if (fields.location) {
    line = `${line}${line ? ", " : ""}${fields.location}`;
  }
  return line;
}

/** The manuscript chapter's one prose line: the title, and whose eyes it is seen through. */
export function manuscriptHeaderText(fields: ChapterFrontMatterFields): string {
  return fields.pov ? `${fields.title}, from the point of view of ${fields.pov}` : (fields.title ?? "");
}
