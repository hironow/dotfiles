// @ts-check
// Copy buttons for the install commands (docs/agents/web-ui.md).
// <ui-button> keeps a button pending while the copy runs; announce() tells
// screen readers how it went, without moving focus.
import { announce, prepareAnnouncements } from "./vendor/ui-sdk/0.1.0-beta.1/web/core.js";

/**
 * What <ui-button> passes with its `action` event.
 * @typedef {object} ActionDetail
 * @property {(work: Promise<unknown>) => void} waitUntil Keep the button pending until `work` settles.
 */

const COPIED_MS = 1800;

/** @type {WeakMap<HTMLButtonElement, ReturnType<typeof setTimeout>>} */
const resets = new WeakMap();

/**
 * @param {Event} event
 * @returns {event is CustomEvent<ActionDetail>}
 */
const isAction = (event) => event instanceof CustomEvent;

/**
 * Write the text to the clipboard. A page with no clipboard (an insecure
 * context) rejects, like a denied permission does.
 * @param {string} text
 * @returns {Promise<void>}
 */
async function writeToClipboard(text) {
  if (!("clipboard" in navigator)) {
    throw new Error("no clipboard");
  }
  await navigator.clipboard.writeText(text);
}

/**
 * Show that the copy worked. When it failed, select the command so the
 * keyboard can copy it.
 * @param {Promise<void>} copying
 * @param {Element} command
 * @param {HTMLButtonElement} button
 * @returns {Promise<void>}
 */
async function report(copying, command, button) {
  try {
    await copying;
  } catch {
    getSelection()?.selectAllChildren(command);
    announce("Could not copy. The command is selected; copy it with your keyboard.");
    return;
  }
  clearTimeout(resets.get(button));
  button.dataset.copied = "";
  announce("Copied the command.");
  resets.set(
    button,
    setTimeout(() => {
      delete button.dataset.copied;
    }, COPIED_MS),
  );
}

/**
 * Wire one `<ui-button data-copy="id">`: its button copies the text of the
 * element with that id.
 * @param {HTMLElement} wrapper
 * @returns {void}
 */
function wire(wrapper) {
  const button = wrapper.querySelector("button");
  const { copy } = wrapper.dataset;
  if (!button || typeof copy !== "string") {
    return;
  }
  wrapper.addEventListener("action", (event) => {
    const command = document.querySelector(`#${CSS.escape(copy)}`);
    if (!command || !isAction(event)) {
      return;
    }
    const copying = writeToClipboard(command.textContent.trim());
    // Call waitUntil() during the event, before any await.
    event.detail.waitUntil(copying);
    void report(copying, command, button);
  });
}

// The live regions must exist before the first message, or it is lost.
prepareAnnouncements(document);

for (const wrapper of document.querySelectorAll("ui-button[data-copy]")) {
  if (wrapper instanceof HTMLElement) {
    wire(wrapper);
  }
}
