export interface LanguageOption {
  code: string;
  label: string;
}

export const LANGUAGES: LanguageOption[] = [
  { code: "en-US", label: "English (US)" },
  { code: "en-GB", label: "English (UK)" },
  { code: "en-AU", label: "English (AU)" },
  { code: "en-CA", label: "English (CA)" },
  { code: "de", label: "Deutsch" },
  { code: "fr", label: "Français" },
  { code: "es", label: "Español" },
  { code: "it", label: "Italiano" },
  { code: "pt", label: "Português" },
  { code: "nl", label: "Nederlands" },
  { code: "sv", label: "Svenska" },
  { code: "pl", label: "Polski" },
];

export interface LanguageSettingsOptions {
  current?: string;
}

export function openLanguageSettings(options: LanguageSettingsOptions = {}): Promise<string | null> {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.dataset.testid = "modal";

    const dialog = document.createElement("div");
    dialog.className = "modal-dialog";

    const title = document.createElement("h2");
    title.className = "modal-title";
    title.dataset.testid = "modal-title";
    title.textContent = "Language";
    dialog.append(title);

    let selected: string | null = options.current ?? null;

    const apply = document.createElement("button");
    apply.type = "button";
    apply.className = "modal-button is-primary";
    apply.dataset.testid = "language-settings-apply";
    apply.textContent = "Apply";
    apply.disabled = selected === null;

    const list = document.createElement("div");
    list.className = "language-settings-list";
    for (const lang of LANGUAGES) {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "language-settings-item";
      item.dataset.testid = "language-settings-item";
      item.dataset.lang = lang.code;
      item.textContent = lang.label;
      if (lang.code === selected) {
        item.classList.add("language-settings-item--current");
        item.setAttribute("aria-current", "true");
      }
      item.addEventListener("click", () => {
        selected = lang.code;
        for (const other of list.querySelectorAll(".language-settings-item--current")) {
          other.classList.remove("language-settings-item--current");
          other.removeAttribute("aria-current");
        }
        item.classList.add("language-settings-item--current");
        item.setAttribute("aria-current", "true");
        apply.disabled = false;
      });
      list.append(item);
    }
    dialog.append(list);

    const close = (result: string | null): void => {
      overlay.remove();
      window.removeEventListener("keydown", onKeydown);
      resolve(result);
    };

    apply.addEventListener("click", () => {
      if (selected !== null) {
        close(selected);
      }
    });

    const buttons = document.createElement("div");
    buttons.className = "modal-buttons";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "modal-button";
    cancel.dataset.testid = "language-settings-cancel";
    cancel.textContent = "Cancel";
    cancel.addEventListener("click", () => close(null));
    buttons.append(cancel, apply);
    dialog.append(buttons);

    overlay.addEventListener("mousedown", (event) => {
      if (event.target === overlay) {
        close(null);
      }
    });

    function onKeydown(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        close(null);
      }
    }
    window.addEventListener("keydown", onKeydown);

    overlay.append(dialog);
    document.body.append(overlay);
  });
}