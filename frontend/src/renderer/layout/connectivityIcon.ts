const SVG_NS = "http://www.w3.org/2000/svg";

export function createConnectivityIcon(online: boolean): SVGElement {
  const icon = document.createElementNS(SVG_NS, "svg");
  icon.dataset.testid = online ? "connectivity-online-icon" : "connectivity-offline-icon";
  icon.classList.add("connectivity-icon", online ? "connectivity-icon--online" : "connectivity-icon--offline");
  icon.setAttribute("viewBox", "0 0 24 24");
  icon.setAttribute("width", "18");
  icon.setAttribute("height", "18");
  icon.setAttribute("fill", "none");
  icon.setAttribute("stroke", online ? "#2563eb" : "#dc2626");
  icon.setAttribute("stroke-width", "2");
  icon.setAttribute("stroke-linecap", "round");
  icon.setAttribute("stroke-linejoin", "round");

  if (online) {
    icon.append(
      svgElement("circle", { cx: "12", cy: "12", r: "10" }),
      svgElement("path", { d: "M12 2a14.5 14.5 0 0 0 0 20" }),
      svgElement("path", { d: "M12 2a14.5 14.5 0 0 1 0 20" }),
      svgElement("path", { d: "M2 12h20" }),
    );
  } else {
    icon.append(
      svgElement("path", { d: "m19 5 3 3" }),
      svgElement("path", { d: "m2 22 3-3" }),
      svgElement("path", { d: "M6 18 4 20" }),
      svgElement("path", { d: "M9 15 7.5 16.5a2.12 2.12 0 0 1-3-3L6 12" }),
      svgElement("path", { d: "m15 9 1.5-1.5a2.12 2.12 0 0 1 3 3L18 12" }),
      svgElement("path", { d: "m2 2 20 20" }),
    );
  }
  return icon;
}

function svgElement(name: string, attributes: Record<string, string>): SVGElement {
  const element = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attributes)) {
    element.setAttribute(key, value);
  }
  return element;
}
