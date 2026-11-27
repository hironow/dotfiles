package rules

import "testing"

const pageFixture = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <!-- <script>alert(1)</script> is a comment, not a script -->
  <script type="module" src="site/vendor/ui-sdk/0.1.0/web.js"></script>
  <script type="module" src="site/copy.js"></script>
</head>
<body>
  <p><span class="cmd" id="cmd-bash">bash -c &quot;$(curl -fsSL <span class="str">https://raw.githubusercontent.com/hironow/dotfiles/main/install.sh</span>)&quot;</span></p>
  <p><span class="cmd" id="cmd-pwsh">irm <span class="str">https://raw.githubusercontent.com/hironow/dotfiles/main/bootstrap.ps1</span> | iex</span></p>
</body>
</html>
`

const copyJsFixture = `import { announce, prepareAnnouncements } from "./vendor/ui-sdk/0.1.0/core.js";
prepareAnnouncements();
await waitUntil(navigator.clipboard.writeText(text));
announce("copied");
`

func pagesBase() Inputs {
	return Inputs{pagesIndex: pageFixture, pagesScript: copyJsFixture, installSh: "#!/bin/sh\n", bootstrapPs1: "# bootstrap\n"}
}

func TestPagesSiteFacts(t *testing.T) {
	runCases(t, pagesSiteFacts(), pagesBase, []ruleCase{
		{"an inline script", edit(pagesIndex, "</head>", "<script>alert(1)</script>\n</head>"), "test_the_page_keeps_its_script_in_site_copy_js"},
		{"copy.js is a classic script", edit(pagesIndex, `<script type="module" src="site/copy.js">`, `<script src="site/copy.js">`), "test_the_page_keeps_its_script_in_site_copy_js"},
		{"copy.js gains an attribute", edit(pagesIndex, `<script type="module" src="site/copy.js">`, `<script type="module" src="site/copy.js" defer>`), "test_the_page_keeps_its_script_in_site_copy_js"},
		{"the page copies the old way", edit(pagesScript, "navigator.clipboard.writeText(text)", "document.execCommand('copy')"), "test_the_page_keeps_its_script_in_site_copy_js"},
		{"no announcement", edit(pagesScript, `announce("copied");`, `console.log("copied");`), "test_the_page_keeps_its_script_in_site_copy_js"},
		{"the bash command changes", edit(pagesIndex, "curl -fsSL ", "curl -sSL "), "test_the_install_commands_are_the_ones_people_should_run"},
		{"the pwsh command points elsewhere", edit(pagesIndex, "hironow/dotfiles/main/bootstrap.ps1", "someone/dotfiles/main/bootstrap.ps1"), "test_the_install_commands_are_the_ones_people_should_run"},
		{"no pwsh command", edit(pagesIndex, `id="cmd-pwsh"`, `id="cmd-ps"`), "test_the_install_commands_are_the_ones_people_should_run"},
	})
}

func TestReadPageReadsLikeHTMLParser(t *testing.T) {
	p := readPage(`<p id="a">x<br/>y</p><div id="b">&amp;<!-- <span id="c">no</span> -->z</div><script defer src=x.js></script><style>p{}</style>`)
	// <br/> opens nothing and its end tag pops every open element, as the
	// test's handle_endtag did, so "y" belongs to no id.
	if p.text["a"] != "x" {
		t.Errorf(`text["a"] = %q, want "x"`, p.text["a"])
	}
	if p.text["b"] != "&z" {
		t.Errorf(`text["b"] = %q, want "&z"`, p.text["b"])
	}
	if _, ok := p.text["c"]; ok {
		t.Error("a tag inside a comment is not an element")
	}
	if len(p.scripts) != 1 || !p.scripts[0].bare["defer"] || p.scripts[0].attrs["src"] != "x.js" {
		t.Errorf("scripts = %+v", p.scripts)
	}
}
