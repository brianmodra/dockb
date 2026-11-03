import { describe, expect, it } from "vitest";
import { characterHeaderText, frontMatterFields, manuscriptHeaderText } from "../src/renderer/layout/characterHeader";

const frontMatter = (fields: Record<string, string>): string =>
  "---\n" + Object.entries(fields).map(([key, value]) => `${key}: ${value}`).join("\n") + "\n---\n\nBody.\n";

describe("frontMatterFields", () => {
  it("reads the simple fields off the front matter", () => {
    const fields = frontMatterFields(
      frontMatter({ title: "Karakas", category: "Character", first_name: "Kiral", age: "34", location: "York", pov: "Karakas" }),
    );
    expect(fields.title).toBe("Karakas");
    expect(fields.category).toBe("Character");
    expect(fields.firstName).toBe("Kiral");
    expect(fields.age).toBe("34");
    expect(fields.location).toBe("York");
    expect(fields.pov).toBe("Karakas");
  });

  it("reads bracketed lists", () => {
    const fields = frontMatterFields(
      frontMatter({ middle_names: "[Edgar, John]", nicknames: "[Adams, Jer]" }),
    );
    expect(fields.middleNames).toEqual(["Edgar", "John"]);
    expect(fields.nicknames).toEqual(["Adams", "Jer"]);
  });

  it("reads block-style lists (one dash per line)", () => {
    const buffer = [
      "---",
      "first_name: Jeremiah",
      "surname: Adams",
      "nicknames:",
      "- Adams",
      "- Jer",
      "- Jer-bear",
      "midle_names:",
      "- Edgar",
      "age: 32",
      "location: Brisbane",
      "---",
      "",
      "Body.",
      "",
    ].join("\n");
    const fields = frontMatterFields(buffer);
    expect(fields.firstName).toBe("Jeremiah");
    expect(fields.surname).toBe("Adams");
    expect(fields.nicknames).toEqual(["Adams", "Jer", "Jer-bear"]);
    expect(fields.middleNames).toEqual(["Edgar"]);
    expect(fields.age).toBe("32");
    expect(fields.location).toBe("Brisbane");
  });

  it("leaves the fields undefined when the front matter is absent", () => {
    expect(frontMatterFields("Body without front matter.\n").title).toBeUndefined();
  });
});

describe("characterHeaderText", () => {
  it("joins first, middle, and surname into one prose line", () => {
    const fields = frontMatterFields(
      frontMatter({ first_name: "Kiral", middle_names: "[Edgar, John]", surname: "Karakas" }),
    );
    expect(characterHeaderText(fields)).toBe("Kiral Edgar John Karakas");
  });

  it("appends the nicknames in parentheses, the age, and the location", () => {
    const fields = frontMatterFields(
      frontMatter({
        first_name: "Jeremiah",
        surname: "Adams",
        nicknames: "[Adams, Jer, Jer-bear]",
        age: "32",
        location: "Brisbane",
      }),
    );
    expect(characterHeaderText(fields)).toBe("Jeremiah Adams (Adams, Jer, Jer-bear) - 32, Brisbane");
  });

  it("omits the pieces that are absent", () => {
    expect(characterHeaderText(frontMatterFields(frontMatter({ first_name: "Liz" })))).toBe("Liz");
    expect(characterHeaderText(frontMatterFields(frontMatter({ age: "12" })))).toBe("12");
    expect(characterHeaderText(frontMatterFields(frontMatter({ title: "Nameless" })))).toBe("");
  });
});

describe("manuscriptHeaderText", () => {
  it("names the chapter and its point of view", () => {
    const fields = frontMatterFields(frontMatter({ title: "Opening 1", pov: "Karakas" }));
    expect(manuscriptHeaderText(fields)).toBe("Opening 1, from the point of view of Karakas");
  });

  it("names just the chapter when there is no POV", () => {
    const fields = frontMatterFields(frontMatter({ title: "Opening 1" }));
    expect(manuscriptHeaderText(fields)).toBe("Opening 1");
  });
});
