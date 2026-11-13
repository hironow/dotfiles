# Web UI: the platform first, then ui-sdk

Read this when you build or change an interface that runs in a browser page.

## Choose what to use

1. **Use the platform first.** Plain HTML, CSS, and browser APIs cover a lot:
   `<button>`, `<a>`, form controls, `<dialog>`, `<details>`, and the
   `popover` attribute. Where the modern-web-guidance skill is installed,
   check it before you write your own code or add a dependency.
2. **Use ui-sdk for behavior the platform lacks**
   ([vercel-labs/ui](https://github.com/vercel-labs/ui)): keyboard
   navigation, focus handling, the ARIA patterns of menus, comboboxes, tabs,
   and trees, popup placement, and a pending state with screen-reader
   announcements. Do not hand-roll ARIA, and do not add another UI library.
3. **Choose the setup from the constraints:**
   - The user names a framework, or the repo already depends on one (React,
     Vue, Svelte, Solid): use that framework's ui-sdk package.
   - No such constraint: plain HTML with ui-sdk's web components, with no
     build step.
   - A smaller constraint (TypeScript, npm packages, several files to bundle,
     or an existing bundler): ui-sdk's web components with Vite.

## Before you write the interface

Follow the `ui-sdk` skill (dotfiles installs it in every agent home). Then read
the docs for your setup: https://ui-sdk.dev/web.md for a page with no build
step, or `node_modules/@ui-sdk/<framework>/docs/llms.txt` once a package is
installed.

Where the skill or the upstream setup steps differ from this guide, this guide
wins:

- Pin an exact version. Never load `https://ui-sdk.dev/web.js` or `web@0.js`:
  they redirect to whatever release is newest.
- Use bun: `bun add` and `bunx` wherever upstream shows an npm command.

## The seven-day wait

ui-sdk is new and still before 1.0, so it is a Class 2 dependency
(docs/agents/dependency-policy.md): adopt a release only when it is seven days
old.

The `min-release-age` in `~/.npmrc` does not reach bun, so set the wait where
you install:

- With a package:
  `bun add --exact --minimum-release-age 7d @ui-sdk/web@<version> @ui-sdk/core@<version>`
  (the same version for both), or `[install] minimumReleaseAge = "7d"` in the
  repo's `bunfig.toml`.
- With no build step: check the release date with `bun info @ui-sdk/web time`
  before you pin a version.

An owner's ruling recorded in a decision record can lift the wait for one named
version.

## Load it on a page with no build step

Host the files yourself by default. Install the package in a temporary folder
with `bun add --exact --ignore-scripts --minimum-release-age 7d @ui-sdk/web@<version>`
(bun checks the bytes against the registry's integrity). Copy
`node_modules/@ui-sdk/web/browser/` and the package's `LICENSE` into a folder
named after the version, keeping `web.js` next to its `web/` folder. Record a
SHA-256 for every file and check them in a test, so a later edit or a formatter
cannot change the bytes unnoticed.

```html
<link rel="stylesheet" href="vendor/ui-sdk/<version>/web.css" />
<script type="module" src="vendor/ui-sdk/<version>/web.js"></script>
```

A page that hands out commands to run, or that takes credentials, must host the
files itself. Another page may load the CDN with both tags pinned to
`web@<version>.js` and `web@<version>.css`. An `integrity` attribute on those
two tags does not cover the modules `web.js` loads later. Only an import map
that lists every module with its `integrity` covers them, and browsers older
than Chrome 127, Firefox 138, and Safari 18 ignore it.

## Style it

- `web.css` gives every component a default look. Theme it with the `--ui-*`
  tokens on `:root`, and override a part with your own rules. Do not fight it
  with `!important`.
- Put `@layer ui-sdk;` at the top of your stylesheet, so your rules win over
  the ones ui-sdk adds.
- Check the colors: text needs 4.5:1 against its background, and control edges,
  focus rings, and state fills need 3:1.

## Keep it current

A copy you host yourself gets no Dependabot alerts. When you change the page,
check the package's releases and security advisories, and move to a new version
only after its seven-day wait.
