const SVG_NS = "http://www.w3.org/2000/svg";

const MARKDOWN_PATHS = ["M6 15V9l3 3 3-3v6", "M17 9v6", "m15 13 2 2 2-2"];

const A_LARGE_SMALL_PATHS = [
  "m15 16 2.536-7.328a1.02 1.02 1 0 1 1.928 0L22 16",
  "M15.697 14h5.606",
  "m2 16 4.039-9.69a.5.5 0 0 1 .923 0L11 16",
  "M3.304 13h6.392",
];

function baseIcon(className: string): SVGSVGElement {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", className);
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", "1em");
  svg.setAttribute("height", "1em");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  return svg;
}

/**
 * Build the Lucide `markdown` icon (an "M" over a down arrow, in a rounded box)
 * shown in WYSIWYG mode. Fixed, trusted markup with no document data.
 */
export function createMarkdownIcon(): SVGSVGElement {
  const svg = baseIcon("mode-icon");

  const rect = document.createElementNS(SVG_NS, "rect");
  rect.setAttribute("width", "20");
  rect.setAttribute("height", "14");
  rect.setAttribute("x", "2");
  rect.setAttribute("y", "5");
  rect.setAttribute("rx", "2");
  svg.append(rect);

  for (const d of MARKDOWN_PATHS) {
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d", d);
    svg.append(path);
  }

  return svg;
}

/**
 * Build the Lucide `a-large-small` icon (an "Aa" glyph) shown in raw mode.
 * Fixed, trusted markup with no document data.
 */
export function createALargeSmallIcon(): SVGSVGElement {
  const svg = baseIcon("mode-icon");

  for (const d of A_LARGE_SMALL_PATHS) {
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d", d);
    svg.append(path);
  }

  return svg;
}
