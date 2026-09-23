export function mountShell(root: HTMLElement): void {
  root.replaceChildren();
  const shell = document.createElement("div");
  shell.dataset.testid = "app-shell";
  const menubar = document.createElement("div");
  menubar.dataset.testid = "menubar";
  shell.append(menubar);
  root.append(shell);
}