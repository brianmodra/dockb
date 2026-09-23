import { AppLayout } from "./layout/layout";

export function mountShell(root: HTMLElement): AppLayout {
  root.replaceChildren();
  const layout = new AppLayout();
  root.append(layout.element);
  return layout;
}