const SVG_NS = "http://www.w3.org/2000/svg";

const SPARKLES_PATHS = [
  "M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z",
  "M20 2v4",
  "M22 4h-4",
];

/**
 * Build a Lucide `sparkles` icon for the AI chat box corner. The markup is a
 * fixed, trusted constant with no document data. The icon strokes with
 * `currentColor`, coloured by the `.chat-sparkle` rule in `styles.css`.
 */
export function createSparklesIcon(): SVGSVGElement {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "chat-sparkle");
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

  for (const d of SPARKLES_PATHS) {
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d", d);
    svg.append(path);
  }

  const circle = document.createElementNS(SVG_NS, "circle");
  circle.setAttribute("cx", "4");
  circle.setAttribute("cy", "20");
  circle.setAttribute("r", "2");
  svg.append(circle);

  return svg;
}
