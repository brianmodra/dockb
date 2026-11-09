const SVG_NS = "http://www.w3.org/2000/svg";

const LOADER_CIRCLE_PATH = "M21 12a9 9 0 1 1-6.219-8.56";

/**
 * Build a spinning Lucide `loader-circle` icon. The markup is a fixed, trusted
 * constant — no document or model data enters it — so any part of the renderer
 * can drop one in to show that work is in progress. The icon strokes with
 * `currentColor` so it inherits the surrounding text colour, and the
 * `spinning-loader` class carries the CSS animation.
 */
export function createSpinner(): SVGSVGElement {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "spinning-loader");
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

  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", LOADER_CIRCLE_PATH);
  svg.append(path);

  return svg;
}
