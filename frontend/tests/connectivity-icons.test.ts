import { describe, expect, it } from "vitest";
import { createConnectivityIcon } from "../src/renderer/layout/connectivityIcon";

describe("connectivity icons", () => {
  it("draws a blue globe while online", () => {
    const icon = createConnectivityIcon(true);
    expect(icon.dataset.testid).toBe("connectivity-online-icon");
    expect(icon.classList.contains("connectivity-icon--online")).toBe(true);
    expect(icon.getAttribute("stroke")).toBe("#2563eb");
    expect(icon.querySelector("circle")).not.toBeNull();
  });

  it("draws a red unplug while offline", () => {
    const icon = createConnectivityIcon(false);
    expect(icon.dataset.testid).toBe("connectivity-offline-icon");
    expect(icon.classList.contains("connectivity-icon--offline")).toBe(true);
    expect(icon.getAttribute("stroke")).toBe("#dc2626");
    expect(icon.querySelector("circle")).toBeNull();
  });
});
