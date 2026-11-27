package rules

import (
	"html"
	"strings"
)

// The Pages site: the page, its script, and the two installers it tells
// people to run.
const (
	pagesIndex      = "index.html"
	pagesScript     = "site/copy.js"
	pagesBash       = `bash -c "$(curl -fsSL https://raw.githubusercontent.com/hironow/dotfiles/main/install.sh)"`
	pagesPowershell = "irm https://raw.githubusercontent.com/hironow/dotfiles/main/bootstrap.ps1 | iex"
)

// pagesSiteFacts: the page keeps its script in site/copy.js and hands out
// the install commands word for word.
func pagesSiteFacts() Rule {
	return factRule(
		"pages-site-facts",
		"the Pages site runs no inline script and hands out the install commands word for word",
		[]string{pagesIndex, pagesScript, installSh, bootstrapPs1},
		[]scriptFact{
			// tests/unit/test_pages_site.py
			fact("test_the_page_keeps_its_script_in_site_copy_js", pageScriptsLiveInCopyJs),
			fact("test_the_install_commands_are_the_ones_people_should_run", pageInstallCommands),
		},
	)
}

func pageScriptsLiveInCopyJs(files map[string]string) []string {
	page := readPage(files[pagesIndex])
	var out []string
	module := false
	for _, s := range page.scripts {
		if src, ok := s.attrs["src"]; !ok || src == "" || s.bare["src"] {
			out = append(out, "no inline <script>: every script has a src")
		}
		if len(s.attrs) == 2 && s.attrs["type"] == "module" && s.attrs["src"] == pagesScript && !s.bare["type"] && !s.bare["src"] {
			module = true
		}
	}
	if !module {
		out = append(out, `the page must load <script type="module" src="site/copy.js">`)
	}
	out = append(out, lacks(pagesScript, "execCommand")(files)...)
	out = append(out, lacks(pagesIndex, "execCommand")(files)...)
	return append(out, has(pagesScript, "waitUntil(", "announce(", "prepareAnnouncements(")(files)...)
}

func pageInstallCommands(files map[string]string) []string {
	page := readPage(files[pagesIndex])
	var out []string
	for id, want := range map[string]string{"cmd-bash": pagesBash, "cmd-pwsh": pagesPowershell} {
		if got, ok := page.text[id]; !ok || pyStrip(got) != want {
			out = append(out, "#"+id+" must read "+want)
		}
	}
	return out
}

// pageScript is one <script> tag's attributes; bare names had no value.
type pageScript struct {
	attrs map[string]string
	bare  map[string]bool
}

// page is what the tests' html.parser.HTMLParser subclass collected: the
// text under each element id, and every <script> tag.
type page struct {
	text    map[string]string
	scripts []pageScript
}

type openElement struct{ tag, id string }

// pageVoid are the tags the test never opened.
var pageVoid = map[string]bool{"meta": true, "link": true, "br": true, "img": true, "input": true}

// readPage reads HTML as the test's parser did (convert_charrefs=True):
// lowercased names, unescaped values and text, comments and declarations
// skipped, script and style content as raw text, and an end tag that pops
// the open elements down to its match.
func readPage(src string) page {
	p := page{text: map[string]string{}}
	var open []openElement
	data := func(s string) {
		for _, e := range open {
			if e.id != "" {
				p.text[e.id] += s
			}
		}
	}
	end := func(tag string) {
		for len(open) > 0 {
			top := open[len(open)-1]
			open = open[:len(open)-1]
			if top.tag == tag {
				break
			}
		}
	}
	for i := 0; i < len(src); {
		lt := strings.IndexByte(src[i:], '<')
		if lt < 0 {
			data(html.UnescapeString(src[i:]))
			break
		}
		if lt > 0 {
			data(html.UnescapeString(src[i : i+lt]))
		}
		i += lt
		rest := src[i:]
		switch {
		case strings.HasPrefix(rest, "<!--"):
			j := strings.Index(rest, "-->")
			if j < 0 {
				return p
			}
			i += j + len("-->")
		case strings.HasPrefix(rest, "<!") || strings.HasPrefix(rest, "<?"):
			j := strings.IndexByte(rest, '>')
			if j < 0 {
				return p
			}
			i += j + 1
		case strings.HasPrefix(rest, "</") && len(rest) > 2 && isASCIILetter(rest[2]):
			j := strings.IndexByte(rest, '>')
			if j < 0 {
				return p
			}
			name, _, _ := strings.Cut(strings.TrimSpace(rest[2:j]), " ")
			end(strings.ToLower(name))
			i += j + 1
		case len(rest) > 1 && isASCIILetter(rest[1]):
			tag, attrs, bare, closed, n := readStartTag(rest)
			i += n
			if tag == "script" {
				p.scripts = append(p.scripts, pageScript{attrs: attrs, bare: bare})
			}
			if !pageVoid[tag] {
				open = append(open, openElement{tag: tag, id: attrs["id"]})
				if id := attrs["id"]; id != "" {
					p.text[id] = ""
				}
			}
			if closed {
				end(tag)
				continue
			}
			if tag == "script" || tag == "style" {
				closing := strings.Index(strings.ToLower(src[i:]), "</"+tag)
				if closing < 0 {
					data(src[i:])
					return p
				}
				data(src[i : i+closing])
				i += closing
			}
		default:
			data("<")
			i++
		}
	}
	return p
}

func isASCIILetter(c byte) bool { return 'a' <= c && c <= 'z' || 'A' <= c && c <= 'Z' }

// readStartTag reads `<name attr="v" bare ...>` and says whether it closed
// itself (`/>`) and how many bytes it took.
func readStartTag(s string) (tag string, attrs map[string]string, bare map[string]bool, closed bool, n int) {
	attrs, bare = map[string]string{}, map[string]bool{}
	i := 1
	for i < len(s) && !strings.ContainsRune(" \t\n\r\f/>", rune(s[i])) {
		i++
	}
	tag = strings.ToLower(s[1:i])
	for i < len(s) {
		for i < len(s) && strings.ContainsRune(" \t\n\r\f", rune(s[i])) {
			i++
		}
		if i >= len(s) {
			break
		}
		if s[i] == '>' {
			return tag, attrs, bare, false, i + 1
		}
		if strings.HasPrefix(s[i:], "/>") {
			return tag, attrs, bare, true, i + 2
		}
		if s[i] == '/' {
			i++
			continue
		}
		start := i
		for i < len(s) && !strings.ContainsRune(" \t\n\r\f=/>", rune(s[i])) {
			i++
		}
		name := strings.ToLower(s[start:i])
		for i < len(s) && strings.ContainsRune(" \t\n\r\f", rune(s[i])) {
			i++
		}
		if i >= len(s) || s[i] != '=' {
			attrs[name], bare[name] = "", true
			continue
		}
		i++
		for i < len(s) && strings.ContainsRune(" \t\n\r\f", rune(s[i])) {
			i++
		}
		var value string
		if i < len(s) && (s[i] == '"' || s[i] == '\'') {
			q := s[i]
			j := strings.IndexByte(s[i+1:], q)
			if j < 0 {
				value, i = s[i+1:], len(s)
			} else {
				value, i = s[i+1:i+1+j], i+2+j
			}
		} else {
			start := i
			for i < len(s) && !strings.ContainsRune(" \t\n\r\f>", rune(s[i])) {
				i++
			}
			value = s[start:i]
		}
		attrs[name], bare[name] = html.UnescapeString(value), false
	}
	return tag, attrs, bare, false, len(s)
}
