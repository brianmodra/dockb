const SVG_NS = "http://www.w3.org/2000/svg";

const SHOULDERS_PATH = "M20 21a8 8 0 0 0-16 0";

/**
 * Build a Lucide `user-round` icon: a circle head over a rounded shoulder arc.
 * The markup is a fixed, trusted constant so the menubar can use it without
 * putting any document data in the DOM. It strokes with `currentColor`.
 */
export function createUserRoundIcon(): SVGSVGElement {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "user-icon");
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

  const head = document.createElementNS(SVG_NS, "circle");
  head.setAttribute("cx", "12");
  head.setAttribute("cy", "8");
  head.setAttribute("r", "5");
  svg.append(head);

  const shoulders = document.createElementNS(SVG_NS, "path");
  shoulders.setAttribute("d", SHOULDERS_PATH);
  svg.append(shoulders);

  return svg;
}
