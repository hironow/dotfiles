// Copy buttons for the install commands (docs/agents/web-ui.md).
// <ui-button> keeps a button pending while the copy runs; announce() tells
// screen readers how it went, without moving focus.
import { announce, prepareAnnouncements } from "./vendor/ui-sdk/0.1.0-beta.1/web/core.js";

// The live regions must exist before the first message, or it is lost.
prepareAnnouncements(document);

for (const wrapper of document.querySelectorAll("ui-button[data-copy]")) {
  const button = wrapper.querySelector("button");
  let reset;
  wrapper.addEventListener("action", (event) => {
    const command = document.getElementById(wrapper.dataset.copy);
    const text = command.textContent.trim();
    const copying = navigator.clipboard
      ? navigator.clipboard.writeText(text)
      : Promise.reject(new Error("no clipboard"));
    // waitUntil() must run during the event, before any await.
    event.detail.waitUntil(copying);
    copying.then(
      () => {
        clearTimeout(reset);
        button.dataset.copied = "";
        announce("Copied the command.");
        reset = setTimeout(() => delete button.dataset.copied, 1800);
      },
      () => {
        getSelection().selectAllChildren(command);
        announce("Could not copy. The command is selected; copy it with your keyboard.");
      },
    );
  });
}
