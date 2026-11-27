package rules

import (
	"regexp"
	"strings"
	"unicode/utf8"
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

// The content models of Python 3.14's html.parser: raw text, and escapable
// raw text (character references still apply).
var (
	pageRawText    = map[string]bool{"script": true, "style": true, "xmp": true, "iframe": true, "noembed": true, "noframes": true, "plaintext": true}
	pageRCData     = map[string]bool{"textarea": true, "title": true}
	pageAmpPending = regexp.MustCompile(`[\t\n\r\f ;]`)
	pageAttrRef    = regexp.MustCompile(`&(#[0-9]+|#[xX][0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*)[;=]?`)
)

// pageReader holds the parser's state and the subclass's collections.
type pageReader struct {
	src       string
	pg        page
	open      []openElement
	cdata     string
	escapable bool
}

// readPage is the test's parser run over src with feed() alone (it never
// called close()): Python 3.14's html.parser.HTMLParser, convert_charrefs on,
// ported step for step, with the subclass's handlers. A construct the parser
// would wait on more input for (an unclosed tag or comment, raw text with no
// end tag) ends the reading there, as it did.
func readPage(src string) page {
	r := &pageReader{src: src, pg: page{text: map[string]string{}}, escapable: true}
	for i := 0; i < len(src); {
		j := r.textEnd(i)
		if j < 0 {
			break
		}
		if i < j {
			if r.escapable {
				r.data(pyUnescape(src[i:j]))
			} else {
				r.data(src[i:j])
			}
		}
		if j == len(src) {
			break
		}
		k := r.markup(j)
		if k < 0 {
			break
		}
		i = k
	}
	return r.pg
}

// textEnd is where the text from i ends: the next '<' (or, in raw text, the
// end tag), the end of the input, or -1 when the parser waits for more.
func (r *pageReader) textEnd(i int) int {
	src, n := r.src, len(r.src)
	if r.cdata == "plaintext" {
		return n // nothing ends plaintext
	}
	if r.cdata != "" {
		return pageCDataEnd(src, i, r.cdata)
	}
	if j := strings.IndexByte(src[i:], '<'); j >= 0 {
		return i + j
	}
	// Text that may end in a character reference cut in half waits. The
	// window is the last 34 characters, as Python counts them.
	from := max(i, pageLastChars(src, 34))
	if amp := strings.LastIndexByte(src[from:], '&'); amp >= 0 && !pageAmpPending.MatchString(src[from+amp:]) {
		return -1
	}
	return n
}

// markup reads the construct at i ('<') and returns where the next text
// starts, or -1 when the parser waits for more input.
func (r *pageReader) markup(i int) int {
	src := r.src
	rest := src[i:]
	switch {
	case len(rest) > 1 && isASCIILetter(rest[1]):
		return r.startTag(i)
	case strings.HasPrefix(rest, "</"):
		return pageEndTag(src, i, func(tag string) {
			r.endTag(tag)
			r.cdata, r.escapable = "", true
		})
	case strings.HasPrefix(rest, "<!--"):
		return pageComment(src, i)
	case strings.HasPrefix(rest, "<?"):
		if g := strings.IndexByte(src[i+2:], '>'); g >= 0 {
			return i + 2 + g + 1
		}
		return -1
	case strings.HasPrefix(rest, "<!"):
		return pageDeclaration(src, i)
	case i+1 < len(src):
		r.data("<")
		return i + 1
	}
	return -1
}

// startTag is parse_starttag with the subclass's handlers.
func (r *pageReader) startTag(i int) int {
	end := pageTagEnd(r.src, i+1)
	if r.src[end-1] != '>' {
		return -1
	}
	tag, attrs, closing := pageStartTag(r.src, i, end)
	switch closing {
	case "":
		r.data(r.src[i:end])
	case "/>":
		r.open1(tag, attrs)
		r.endTag(tag)
	default:
		r.open1(tag, attrs)
		if pageRawText[tag] {
			r.cdata, r.escapable = tag, false
		} else if pageRCData[tag] {
			r.cdata, r.escapable = tag, true
		}
	}
	return end
}

// data is the subclass's handle_data: text for every open element with an id.
func (r *pageReader) data(s string) {
	for _, e := range r.open {
		if e.id != "" {
			r.pg.text[e.id] += s
		}
	}
}

// endTag is the subclass's handle_endtag: pop down to the matching element.
func (r *pageReader) endTag(tag string) {
	for len(r.open) > 0 {
		top := r.open[len(r.open)-1]
		r.open = r.open[:len(r.open)-1]
		if top.tag == tag {
			return
		}
	}
}

// open1 is the subclass's handle_starttag.
func (r *pageReader) open1(tag string, attrs []pageAttr) {
	s := pageScript{attrs: map[string]string{}, bare: map[string]bool{}}
	for _, a := range attrs {
		s.attrs[a.name], s.bare[a.name] = a.value, a.bare
	}
	if tag == "script" {
		r.pg.scripts = append(r.pg.scripts, s)
	}
	if pageVoid[tag] {
		return
	}
	id := s.attrs["id"]
	if s.bare["id"] {
		id = ""
	}
	r.open = append(r.open, openElement{tag: tag, id: id})
	if id != "" {
		r.pg.text[id] = ""
	}
}

// pageCDataEnd finds `</name` followed by whitespace, `/` or `>` (ASCII case
// insensitive), the only way out of raw text.
func pageCDataEnd(src string, from int, name string) int {
	for k := from; ; {
		at := strings.Index(src[k:], "</")
		if at < 0 {
			return -1
		}
		at += k
		after := at + 2 + len(name)
		if after < len(src) && asciiEqualFold(src[at+2:after], name) && strings.ContainsRune("\t\n\r\f />", rune(src[after])) {
			return at
		}
		k = at + 1
	}
}

const pageSpace = "\t\n\r\f "

func pageIn(set string, c byte) bool { return strings.IndexByte(set, c) >= 0 }

// pageTagEnd is locatetagend matched at p (the tag name's first letter): the
// end of the tag, which is complete only when it ends with '>'.
func pageTagEnd(src string, p int) int {
	i := p + 1
	for i < len(src) && !pageIn(pageSpace+"/>", src[i]) {
		i++
	}
	for i < len(src) && pageIn(pageSpace+"/", src[i]) {
		i++
	}
	for i < len(src) && pageIn(`'"`+pageSpace+"/", src[i-1]) && !pageIn(pageSpace+"/>", src[i]) {
		i++
		for i < len(src) && !pageIn(pageSpace+"/=>", src[i]) {
			i++
		}
		i = pageAttrValueEnd(src, i)
		for i < len(src) && pageIn(pageSpace+"/", src[i]) {
			i++
		}
	}
	if i < len(src) && src[i] == '>' {
		i++
	}
	return i
}

// pageAttrValueEnd is the optional `\s*=\s*value` after an attribute name:
// where it ends, or i when there is none.
func pageAttrValueEnd(src string, i int) int {
	j := i
	for j < len(src) && pageIn(pageSpace, src[j]) {
		j++
	}
	if j >= len(src) || src[j] != '=' {
		return i
	}
	j++
	for j < len(src) && pageIn(pageSpace, src[j]) {
		j++
	}
	if j < len(src) && (src[j] == '\'' || src[j] == '"') {
		closing := strings.IndexByte(src[j+1:], src[j])
		if closing < 0 {
			return i
		}
		return j + 1 + closing + 1
	}
	for j < len(src) && !pageIn(">"+pageSpace, src[j]) {
		j++
	}
	return j
}

type pageAttr struct {
	name, value string
	bare        bool
}

// pageStartTag is parse_starttag between i ('<') and end: the tag, its
// attributes, and how it closes (">", "/>", or "" when the rest is not a
// tag end, which the parser hands on as text).
func pageStartTag(src string, i, end int) (string, []pageAttr, string) {
	k := i + 1
	for k < end && !pageIn(pageSpace+"/>", src[k]) {
		k++
	}
	tag := pyLower(src[i+1 : k])
	k = pageSkipSpaceAndSlash(src, k)
	var attrs []pageAttr
	for k < end {
		if !pageIn(`'"`+pageSpace+"/", src[k-1]) || pageIn(pageSpace+"/>", src[k]) {
			break
		}
		start := k
		k++
		for k < len(src) && !pageIn(pageSpace+"/=>", src[k]) {
			k++
		}
		name := pyLower(src[start:k])
		valueEnd := pageAttrValueEnd(src, k)
		attr := pageAttr{name: name, bare: valueEnd == k}
		if !attr.bare {
			raw := strings.TrimLeft(src[k:valueEnd], pageSpace)
			raw = strings.TrimLeft(raw[1:], pageSpace) // the '='
			if len(raw) >= 2 && (raw[0] == '\'' || raw[0] == '"') && raw[len(raw)-1] == raw[0] {
				raw = raw[1 : len(raw)-1]
			}
			attr.value = pageUnescapeAttr(raw)
		}
		attrs = append(attrs, attr)
		k = pageSkipSpaceAndSlash(src, valueEnd)
	}
	switch pyStrip(src[k:end]) {
	case ">":
		return tag, attrs, ">"
	case "/>":
		return tag, attrs, "/>"
	}
	return tag, attrs, ""
}

// pageSkipSpaceAndSlash is (?:[\t\n\r\f ]|/(?!>))*.
func pageSkipSpaceAndSlash(src string, k int) int {
	for k < len(src) && (pageIn(pageSpace, src[k]) || src[k] == '/' && (k+1 >= len(src) || src[k+1] != '>')) {
		k++
	}
	return k
}

// pageUnescapeAttr is _unescape_attrvalue: numeric references always, a
// named one only when it is a whole entity name not followed by '='.
func pageUnescapeAttr(v string) string {
	return pageAttrRef.ReplaceAllStringFunc(v, func(ref string) string {
		if strings.HasPrefix(ref, "&#") {
			return pyUnescape(ref)
		}
		if strings.HasSuffix(ref, "=") {
			return ref
		}
		u := pyUnescape(ref)
		if u == ref || strings.IndexFunc(u, func(r rune) bool {
			return 'a' <= r && r <= 'z' || 'A' <= r && r <= 'Z' || '0' <= r && r <= '9'
		}) >= 0 {
			return ref // not a whole entity name
		}
		return u
	})
}

// pageEndTag is parse_endtag at i ("</"): the end, or -1 when the parser
// waits for more input. It calls end with the tag name when there is one.
func pageEndTag(src string, i int, end func(string)) int {
	if strings.IndexByte(src[i+2:], '>') < 0 {
		return -1
	}
	if i+2 >= len(src) || !isASCIILetter(src[i+2]) {
		if src[i+2] == '>' {
			return i + 3
		}
		return i + 2 + strings.IndexByte(src[i+2:], '>') + 1 // a bogus comment
	}
	j := pageTagEnd(src, i+2)
	if src[j-1] != '>' {
		return -1
	}
	k := i + 3
	for k < len(src) && !pageIn(pageSpace+"/>", src[k]) {
		k++
	}
	end(pyLower(src[i+2 : k]))
	return j
}

// pageComment is parse_comment at i ("<!--"): closed by `--!?>`, or at once
// by `-?>`; -1 when unclosed.
func pageComment(src string, i int) int {
	for k := i + 4; ; {
		at := strings.Index(src[k:], "--")
		if at < 0 {
			break
		}
		at += k
		if strings.HasPrefix(src[at+2:], ">") {
			return at + 3
		}
		if strings.HasPrefix(src[at+2:], "!>") {
			return at + 4
		}
		k = at + 1
	}
	switch {
	case strings.HasPrefix(src[i+4:], ">"):
		return i + 5
	case strings.HasPrefix(src[i+4:], "->"):
		return i + 6
	}
	return -1
}

// pageDeclaration is parse_html_declaration at i ("<!"): CDATA, doctype or
// a bogus comment.
func pageDeclaration(src string, i int) int {
	rest := src[i:]
	switch {
	case strings.HasPrefix(rest, "<![CDATA["):
		if j := strings.Index(rest[9:], "]]>"); j >= 0 {
			return i + 9 + j + 3
		}
		return -1
	case len(rest) >= 9 && strings.EqualFold(rest[:9], "<!doctype"):
		if j := strings.IndexByte(rest[9:], '>'); j >= 0 {
			return i + 9 + j + 1
		}
		return -1
	}
	if j := strings.IndexByte(rest[2:], '>'); j >= 0 {
		return i + 2 + j + 1
	}
	return -1
}

func isASCIILetter(c byte) bool { return 'a' <= c && c <= 'z' || 'A' <= c && c <= 'Z' }

// asciiEqualFold compares under ASCII case folding only, as the parser's
// re.ASCII | re.IGNORECASE pattern does.
func asciiEqualFold(a, b string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range len(a) {
		x, y := a[i], b[i]
		if 'A' <= x && x <= 'Z' {
			x += 'a' - 'A'
		}
		if 'A' <= y && y <= 'Z' {
			y += 'a' - 'A'
		}
		if x != y {
			return false
		}
	}
	return true
}

// pageLastChars is the byte offset where the last n characters of s start.
func pageLastChars(s string, n int) int {
	end := len(s)
	for range n {
		if end == 0 {
			break
		}
		_, size := utf8.DecodeLastRuneInString(s[:end])
		end -= size
	}
	return end
}
