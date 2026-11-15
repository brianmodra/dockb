const SVG_NS = "http://www.w3.org/2000/svg";

const SAVE_PATHS = [
  "M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z",
  "M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7",
  "M7 3v4a1 1 0 0 0 1 1h7",
];

/**
 * Build a Lucide `save` icon. The markup is a fixed, trusted constant so the
 * menubar can use it without putting any document data in the DOM. The icon
 * strokes with `currentColor`, inheriting the button's colour.
 */
export function createSaveIcon(): SVGSVGElement {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "save-icon");
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

  for (const d of SAVE_PATHS) {
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d", d);
    svg.append(path);
  }

  return svg;
}
