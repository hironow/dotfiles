package rules

import (
	"strings"
	"testing"
)

const pageFixture = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <style>ui-button:not(:defined) { display: none; }</style>
  <!-- <script>alert(1)</script> is a comment, not a script -->
  <link rel="stylesheet" href="site/vendor/ui-sdk/0.1.0/web.css">
  <script type="module" src="site/vendor/ui-sdk/0.1.0/web.js"></script>
  <script type="module" src="site/copy.js"></script>
</head>
<body>
  <nav aria-label="Main"><a href="#cmd-bash">Install</a></nav>
  <p><span class="cmd" id="cmd-bash">bash -c &quot;$(curl -fsSL <span class="str">https://raw.githubusercontent.com/hironow/dotfiles/main/install.sh</span>)&quot;</span></p>
  <ui-button data-copy="cmd-bash"><button class="copy" type="button">Copy</button></ui-button>
  <p><span class="cmd" id="cmd-pwsh">irm <span class="str">https://raw.githubusercontent.com/hironow/dotfiles/main/bootstrap.ps1</span> | iex</span></p>
  <ui-button data-copy="cmd-pwsh"><button class="copy" type="button">Copy</button></ui-button>
</body>
</html>
`

const copyJsFixture = `import { announce, prepareAnnouncements } from "./vendor/ui-sdk/0.1.0/core.js";
prepareAnnouncements();
await waitUntil(navigator.clipboard.writeText(text));
announce("copied");
`

func pagesBase() Inputs {
	return Inputs{pagesIndex: pageFixture, pagesScript: copyJsFixture, installSh: "#!/bin/sh\n", bootstrapPs1: "# bootstrap\n", pagesVendor: []string{"0.1.0"}}
}

func TestPagesVendoredSDKFacts(t *testing.T) {
	const name = "test_ui_sdk_loads_only_from_the_vendored_version_by_relative_path"
	runCases(t, pagesSiteFacts(), pagesBase, []ruleCase{
		{"no web.js", edit(pagesIndex, "0.1.0/web.js", "other/web.js"), name},
		{"no web.css", edit(pagesIndex, "0.1.0/web.css", "other/web.css"), name},
		{"absolute path", edit(pagesScript, `from "./vendor`, `from "/vendor`), name},
		{"origin URL", edit(pagesScript, `from "./vendor`, `from "https://cdn.invalid/vendor`), name},
		{"wrong version", edit(pagesScript, "0.1.0/core.js", "other/core.js"), name},
		{"no matching imports", edit(pagesScript, `from "`, `from '`), name},
		{"dev host in comment", edit(pagesScript, "prepareAnnouncements();", "// ui-sdk.dev\nprepareAnnouncements();"), name},
		{"dev host in page comment", edit(pagesIndex, "</head>", "<!-- ui-sdk.dev -->\n</head>"), name},
		{"duplicate attribute", edit(pagesIndex, `href="#cmd-bash"`, `href="https://cdn.invalid/ui-sdk/x" href="#cmd-bash"`), name},
		{"comment import", edit(pagesScript, "prepareAnnouncements();", "// from \"/ui-sdk/core.js\"\nprepareAnnouncements();"), name},
		{"no version directory", func(in Inputs) { in[pagesVendor] = []string{} }, name},
		{"two version directories", func(in Inputs) { in[pagesVendor] = []string{"0.1.0", "other"} }, name},
		{"invalid UTF-8", edit(pagesScript, "prepareAnnouncements();", "// \xff\nprepareAnnouncements();"), name},
	})
}

func TestPagesVendorSearchKeepsPythonSemantics(t *testing.T) {
	in := pagesBase()
	in[pagesScript] = strings.ReplaceAll(copyJsFixture, `from "`, "from\u0085\u001c\u2028\"")
	in[pagesScript] = strings.ReplaceAll(in[pagesScript].(string), "core.js", "anything.js")
	in[pagesIndex] = strings.ReplaceAll(pageFixture, "</head>", `<a href="https://cdn.invalid/UI-SDK/x" src="" href>case-sensitive</a></head>`)
	if got := findingsOf(t, pagesSiteFacts(), in); len(got) != 0 {
		t.Errorf("Unicode spaces, arbitrary import basename and case-sensitive filtering: %v", got)
	}
	in = pagesBase()
	in[pagesVendor] = []string{"arbitrary-folder"}
	in[pagesIndex] = strings.ReplaceAll(pageFixture, "0.1.0", "arbitrary-folder")
	in[pagesScript] = strings.ReplaceAll(copyJsFixture, "0.1.0", "arbitrary-folder")
	if got := findingsOf(t, pagesSiteFacts(), in); len(got) != 0 {
		t.Errorf("a folder name need not be a version number: %v", got)
	}
}

func TestReadPageKeepsEveryNonemptySrcAndHref(t *testing.T) {
	p := readPage(`<link href="a&amp;b" href="c"><script src="" src src="d"></script><!-- <img src="no"> -->`)
	if strings.Join(p.links, ",") != "a&b,c,d" {
		t.Errorf("links = %v", p.links)
	}
}

func TestPagesVendorDecodesNamedEntitiesContainingLetters(t *testing.T) {
	in := pagesBase()
	in[pagesVendor] = []string{"fj"}
	in[pagesIndex] = strings.ReplaceAll(pageFixture, "0.1.0", "&fjlig;")
	in[pagesScript] = strings.ReplaceAll(copyJsFixture, "0.1.0", "fj")
	if got := findingsOf(t, pagesSiteFacts(), in); len(got) != 0 {
		t.Fatalf("HTML entity is the selected vendor folder: %v", got)
	}
	in[pagesVendor] = []string{"other"}
	if got := findingsOf(t, pagesSiteFacts(), in); len(got) == 0 {
		t.Fatal("an entity must not hide a different vendor folder")
	}
}

func TestPageAttributeEntitiesKeepWholeNameSemantics(t *testing.T) {
	for _, tc := range []struct{ input, want string }{
		{"&fjlig;", "fj"},
		{"&fjlig", "&fjlig"},
		{"&amp", "&"},
		{"&amp;", "&"},
		{"&amp=", "&amp="},
		{"&ampx;", "&ampx;"},
		{"&fjlig;=", "fj="},
		{"&#102;&#106;", "fj"},
	} {
		t.Run(tc.input, func(t *testing.T) {
			if got := pageUnescapeAttr(tc.input); got != tc.want {
				t.Fatalf("attribute = %q, want %q", got, tc.want)
			}
		})
	}
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
		{"no bash copy button", edit(pagesIndex, `data-copy="cmd-bash"`, `data-copy="other"`), "test_copy_buttons_are_ui_buttons_that_hide_until_defined"},
		{"no pwsh copy button", edit(pagesIndex, `data-copy="cmd-pwsh"`, `data-copy="other"`), "test_copy_buttons_are_ui_buttons_that_hide_until_defined"},
		{"visible before definition", edit(pagesIndex, "display: none", "display: block"), "test_copy_buttons_are_ui_buttons_that_hide_until_defined"},
		{"button label attribute", edit(pagesIndex, `type="button">`, `type="button" aria-label="Copy">`), "test_copy_buttons_are_ui_buttons_that_hide_until_defined"},
		{"nav closing tag label", edit(pagesIndex, "</nav>", "</nav aria-label=x>"), "test_copy_buttons_are_ui_buttons_that_hide_until_defined"},
		{"uppercase nav label", edit(pagesIndex, "<nav ", "<NAV "), "test_copy_buttons_are_ui_buttons_that_hide_until_defined"},
		{"attribute order changes", edit(pagesIndex, `class="copy" type="button"`, `type="button" class="copy"`), "test_copy_buttons_are_ui_buttons_that_hide_until_defined"},
		{"single quoted copy target", edit(pagesIndex, `data-copy="cmd-bash"`, `data-copy='cmd-bash'`), "test_copy_buttons_are_ui_buttons_that_hide_until_defined"},
	})
}

func TestPageCopyButtonsKeepRawSearchSemantics(t *testing.T) {
	in := pagesBase()
	text := strings.ReplaceAll(pageFixture, "><button", ">\u00a0\u0085<button")
	text = strings.ReplaceAll(text, " { display: none; }", "\u2003{\u001cdisplay:\u2028none\u00a0}")
	text = strings.ReplaceAll(text, "</body>", "<nav-extra aria-label=\"Other\"></nav-extra></body>")
	in[pagesIndex] = text
	if got := findingsOf(t, pagesSiteFacts(), in); len(got) != 0 {
		t.Errorf("Unicode spaces and nav opening tags must pass: %v", got)
	}
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

// Readings Python 3.14's html.parser gives for these inputs (checked against
// the test's parser on 15,000 generated inputs while porting).
func TestReadPageFollowsPython314(t *testing.T) {
	// --!> closes a comment, so the script after it is a script.
	p := readPage(`<!--x--!><script>alert(1)</script>`)
	if len(p.scripts) != 1 || len(p.scripts[0].attrs) != 0 {
		t.Errorf("after --!>: scripts = %+v", p.scripts)
	}
	// textarea and title hold text, not tags.
	p = readPage(`<textarea><script src="site/copy.js"></textarea><script>alert(1)</script>`)
	if len(p.scripts) != 1 || p.scripts[0].attrs["src"] != "" {
		t.Errorf("after textarea: scripts = %+v", p.scripts)
	}
	p = readPage(`<title id=t>&lt;b&gt;</title><xmp id=x><b>raw</b></xmp>`)
	if p.text["t"] != "<b>" || p.text["x"] != "<b>raw</b>" {
		t.Errorf("text = %q", p.text)
	}
	// A closing script tag needs a following space, slash or '>'.
	p = readPage(`<script>var x = "</scriptx>"; </SCRIPT ><p id=s>t</p>`)
	if p.text["s"] != "t" {
		t.Errorf(`text["s"] = %q`, p.text["s"])
	}
	// Nothing ends plaintext: the rest of the page is text.
	p = readPage(`<p id=k><plaintext></plaintext><script>alert(1)</script>`)
	if len(p.scripts) != 0 || p.text["k"] != "</plaintext><script>alert(1)</script>" {
		t.Errorf("after plaintext: %+v %q", p.scripts, p.text)
	}
	// Numeric references to invalid code points unescape to nothing; the
	// C1 range maps to Windows-1252.
	p = readPage("<p id=r>ba&#11;sh &#x80; &#55296; &#0;</p>")
	if p.text["r"] != "bash € \uFFFD \uFFFD" {
		t.Errorf(`text["r"] = %q`, p.text["r"])
	}
	// The pending-reference window is the last 34 characters, not bytes: a
	// '&' 23 characters (41 bytes) from the end still makes the text wait.
	p = readPage("<p id=w>x &quot" + strings.Repeat("\u00a0", 18))
	if p.text["w"] != "" {
		t.Errorf(`text["w"] = %q, want the text left waiting`, p.text["w"])
	}
	// Python lowercases the dotted capital I to i + U+0307.
	p = readPage("<p İD=x id=y>z</p>")
	if p.text["y"] != "z" {
		t.Errorf("text = %q", p.text)
	}
}
