/** Cancel and Escape never execute the action. */
export function confirmAction(message: string): Promise<boolean> {
  return new Promise((resolve) => {
    const previous = document.activeElement as HTMLElement | null;
    const dialog = document.createElement("dialog");
    dialog.className = "app-confirmation";
    dialog.setAttribute("aria-label", "Confirm action");
    const text = document.createElement("p");
    text.textContent = message;
    const actions = document.createElement("div");
    actions.className = "notification-actions";
    const finish = (accepted: boolean) => {
      dialog.close();
      dialog.remove();
      previous?.focus();
      resolve(accepted);
    };
    for (const [label, accepted] of [
      ["Cancel", false],
      ["Confirm", true],
    ] as const) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.onclick = () => finish(accepted);
      actions.append(button);
    }
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      finish(false);
    });
    dialog.append(text, actions);
    document.body.append(dialog);
    dialog.showModal();
    actions.querySelector("button")?.focus();
  });
}

export function notify(message: string) {
  const toast = document.createElement("div");
  toast.className = "app-toast";
  toast.setAttribute("role", "status");
  toast.setAttribute("aria-live", "polite");
  const text = document.createElement("span");
  text.textContent = message;
  const dismiss = document.createElement("button");
  dismiss.type = "button";
  dismiss.textContent = "Dismiss";
  const timer = window.setTimeout(() => toast.remove(), 6000);
  dismiss.onclick = () => {
    window.clearTimeout(timer);
    toast.remove();
  };
  toast.append(text, dismiss);
  document.querySelectorAll(".app-toast").forEach((old) => old.remove());
  document.body.append(toast);
}
