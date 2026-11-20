import { describe, expect, it, vi } from "vitest";
import { Connectivity } from "../src/renderer/state/connectivity";

describe("Connectivity", () => {
  it("starts online", () => {
    expect(new Connectivity({ enabled: true }).isOnline()).toBe(true);
  });

  it("reports online changes and ignores a change to the current state", async () => {
    const onChange = vi.fn();
    const connectivity = new Connectivity({ enabled: true, onChange });

    await connectivity.setOnline(false);
    await connectivity.setOnline(false);
    await connectivity.setOnline(true);

    expect(connectivity.isOnline()).toBe(true);
    expect(onChange).toHaveBeenCalledTimes(2);
    expect(onChange).toHaveBeenNthCalledWith(1, false);
    expect(onChange).toHaveBeenNthCalledWith(2, true);
  });

  it("notifies subscribers with the current state and lets them unsubscribe", async () => {
    const connectivity = new Connectivity({ enabled: true });
    const listener = vi.fn();
    const unsubscribe = connectivity.subscribe(listener);
    expect(listener).toHaveBeenCalledWith(true);

    await connectivity.setOnline(false);
    expect(listener).toHaveBeenLastCalledWith(false);

    unsubscribe();
    await connectivity.setOnline(true);
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it("can replace its change listener", async () => {
    const original = vi.fn();
    const replacement = vi.fn();
    const connectivity = new Connectivity({ enabled: true, onChange: original });
    connectivity.setOnChange(replacement);

    await connectivity.setOnline(false);

    expect(original).not.toHaveBeenCalled();
    expect(replacement).toHaveBeenCalledWith(false);
  });
});
