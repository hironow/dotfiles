package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const (
	sourceRel    = "config/mise/image-tools.toml"
	hostRel      = "config/mise/config.toml"
	featureRel   = ".devcontainer/features/dotfiles-tools/install.sh"
	bootstrapRel = "install.sh"
)

// ---------- helpers ----------

func repoRoot(t *testing.T) string {
	t.Helper()
	root, err := defaultRoot()
	if err != nil {
		t.Fatalf("defaultRoot: %v", err)
	}
	return root
}

func copyFile(t *testing.T, src, dst string) {
	t.Helper()
	data, err := os.ReadFile(src)
	if err != nil {
		t.Fatalf("read %s: %v", src, err)
	}
	if err := os.MkdirAll(filepath.Dir(dst), 0o755); err != nil {
		t.Fatalf("mkdir %s: %v", filepath.Dir(dst), err)
	}
	if err := os.WriteFile(dst, data, 0o644); err != nil {
		t.Fatalf("write %s: %v", dst, err)
	}
}

// tree copies the four files the tool reads and writes into a temp checkout.
func tree(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	root := repoRoot(t)
	for _, rel := range []string{sourceRel, hostRel, featureRel, bootstrapRel} {
		copyFile(t, filepath.Join(root, rel), filepath.Join(dir, rel))
	}
	return dir
}

func read(t *testing.T, path string) string {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	return string(data)
}

func mutate(t *testing.T, root, rel, old, new string) {
	t.Helper()
	path := filepath.Join(root, rel)
	text := read(t, path)
	if !strings.Contains(text, old) {
		t.Fatalf("%q is not in %s: the fixture would be a no-op", old, rel)
	}
	if err := os.WriteFile(path, []byte(strings.Replace(text, old, new, 1)), 0o644); err != nil {
		t.Fatalf("write %s: %v", path, err)
	}
}

func runCLI(t *testing.T, args ...string) (int, string, string) {
	t.Helper()
	var stdout, stderr bytes.Buffer
	code := run(args, &stdout, &stderr)
	return code, stdout.String(), stderr.String()
}

func loadSourceDoc(t *testing.T, root string) *table {
	t.Helper()
	doc, err := loadDoc(filepath.Join(root, sourceRel))
	if err != nil {
		t.Fatalf("load %s: %v", sourceRel, err)
	}
	return doc
}

func loadHostDoc(t *testing.T, root string) *table {
	t.Helper()
	tools, err := loadHostTools(root)
	if err != nil {
		t.Fatalf("load %s: %v", hostRel, err)
	}
	return tools
}

func (tbl *table) must(key string) *table {
	v, ok := tbl.get(key)
	if !ok || v.kind != kindTable {
		panic("not a table: " + key)
	}
	return v.table
}

func (tbl *table) mustStr(key string) string {
	v, ok := tbl.get(key)
	if !ok || v.kind != kindString {
		panic("not a string: " + key)
	}
	return v.str
}

func (tbl *table) mustList(key string) []string {
	v, ok := tbl.get(key)
	if !ok || v.kind != kindArray {
		panic("not an array: " + key)
	}
	return v.list
}

func cloneTable(src *table) *table {
	dst := newTable()
	for _, key := range src.keys {
		v := src.vals[key]
		if v.table != nil {
			v = tableValue(cloneTable(v.table))
		}
		dst.set(key, v)
	}
	return dst
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

// ---------- the TOML subset reader ----------

func TestParseAcceptsTheShapesOurFilesUse(t *testing.T) {
	doc, err := parseTOML(`
# a comment
[settings.npm]
package_manager = "bun"   # trailing comment

[tools]
bun = "1.4.3"
"npm:cf" = "1.0.0-beta.18"
"github:google-antigravity/antigravity-cli" = { version = "1.4.2", rename_exe = "antigravity" }

[fetch]
mise_tools = ["uv", "just"]
"aqua:rossmacarthur/sheldon" = "0.8.5"
`)
	if err != nil {
		t.Fatalf("parseTOML: %v", err)
	}
	settings := doc.must("settings")
	if got := settings.must("npm").mustStr("package_manager"); got != "bun" {
		t.Errorf("settings.npm.package_manager = %q, want bun", got)
	}
	tools := doc.must("tools")
	if got := tools.mustStr(`npm:cf`); got != "1.0.0-beta.18" {
		t.Errorf("quoted key: got %q", got)
	}
	if got := tools.must("github:google-antigravity/antigravity-cli").mustStr("rename_exe"); got != "antigravity" {
		t.Errorf("inline table: got %q", got)
	}
	if got := doc.must("fetch").mustList("mise_tools"); len(got) != 2 || got[0] != "uv" || got[1] != "just" {
		t.Errorf("array: got %v", got)
	}
	// Insertion order is preserved: the renderer depends on it for byte equality.
	if want := []string{"bun", `npm:cf`, "github:google-antigravity/antigravity-cli"}; !sameStrings(tools.keys, want) {
		t.Errorf("keys = %v, want %v", tools.keys, want)
	}
}

func TestParseResolvesEscapes(t *testing.T) {
	doc, err := parseTOML("[tools]\nk = \"a\\\"b\\\\c\\nd\\te\\u0041\"\n")
	if err != nil {
		t.Fatalf("parseTOML: %v", err)
	}
	if got, want := doc.must("tools").mustStr("k"), "a\"b\\c\nd\teA"; got != want {
		t.Errorf("escapes: got %q, want %q", got, want)
	}
}

func TestParseRejectsWhatWeDoNotSupport(t *testing.T) {
	for name, text := range map[string]string{
		"duplicate key":        "[tools]\nbun = \"1\"\nbun = \"2\"\n",
		"redefined table":      "[tools]\nbun = \"1\"\n[tools]\ngo = \"1\"\n",
		"invalid escape":       "[tools]\nk = \"a\\qb\"\n",
		"unterminated string":  "[tools]\nk = \"a\n",
		"bare value":           "[tools]\nk = 1.4.3\n",
		"unknown value":        "[tools]\nk = true\n",
		"dotted key":           "[tools]\na.b = \"1\"\n",
		"array of non-strings": "[fetch]\nmise_tools = [1, 2]\n",
		"missing equals":       "[tools]\nbun \"1.4.3\"\n",
		"unknown table shape":  "[a.b.c]\nk = \"1\"\n",
	} {
		if _, err := parseTOML(text); err == nil {
			t.Errorf("%s: parseTOML accepted invalid input", name)
		}
	}
}

func TestParseRejectsMalformedTOML(t *testing.T) {
	for name, text := range map[string]string{
		"array hole":                  "[fetch]\nmise_tools = [\"uv\",,\"just\"]\n",
		"array leading comma":         "[fetch]\nmise_tools = [,\"uv\"]\n",
		"inline trailing comma":       "[tools]\nuv = { version = \"0.13.1\", }\n",
		"inline hole":                 "[tools]\nuv = { version = \"0.13.1\",, os = [\"linux\"] }\n",
		"inline redeclaration":        "[tools]\nuv = { version = \"0.13.1\" }\n[tools.uv]\n",
		"inline extension":            "[tools]\nuv = { version = \"0.13.1\" }\n[tools.uv]\nos = [\"linux\"]\n",
		"raw control":                 "[tools]\nk = \"a\x01b\"\n",
		"raw DEL":                     "[tools]\nk = \"a\x7fb\"\n",
		"invalid UTF-8":               "[tools]\nk = \"a\xffb\"\n",
		"invalid header":              "[settings.bad name]\nk = \"v\"\n",
		"normalized duplicate header": "[settings.npm]\na = \"b\"\n[ settings . npm ]\n",
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := parseTOML(text); err == nil {
				t.Fatal("accepted malformed TOML")
			}
		})
	}
}

func TestTOMLWhitespace(t *testing.T) {
	for _, text := range []string{
		"[tools]\nnode\u00a0= \"24.22.0\"\n",
		"[tools]\nnode\v= \"24.22.0\"\n",
		"[tools]\nnode\f= \"24.22.0\"\n",
		"# forbidden control \x01\n",
		"# forbidden bare CR\r",
	} {
		if _, err := parseTOML(text); err == nil {
			t.Errorf("accepted invalid TOML: %q", text)
		}
	}
	if _, err := parseTOML("[tools]\r\nnode\t= \"24.22.0\"\r\n"); err != nil {
		t.Fatalf("valid CRLF or tab rejected: %v", err)
	}
}

func TestParseAllowsArrayTrailingCommaAndImplicitParent(t *testing.T) {
	if _, err := parseTOML("[settings.npm]\npackage_manager = \"bun\"\n[settings]\n[fetch]\nmise_tools = [\"uv\",]\n"); err != nil {
		t.Fatal(err)
	}
}

func TestHostRejectsToolsHeaderRedefinition(t *testing.T) {
	root := tree(t)
	path := filepath.Join(root, hostRel)
	text := read(t, path) + "\n[ tools ]\n"
	if err := os.WriteFile(path, []byte(text), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := loadHostTools(root); err == nil {
		t.Fatal("host accepted a repeated tools header")
	}
}

// ---------- the renderer ----------

func TestRenderHeredocRoundTripsThroughOurParser(t *testing.T) {
	doc := loadSourceDoc(t, repoRoot(t))
	body, err := renderHeredocBody(doc)
	if err != nil {
		t.Fatalf("renderHeredocBody: %v", err)
	}
	got, err := parseTOML(body)
	if err != nil {
		t.Fatalf("the rendered body does not parse: %v", err)
	}
	if err := equalDocuments(doc, got, []string{"settings", "tools"}); err != nil {
		t.Errorf("rendered body differs from the source: %v", err)
	}
}

func TestRenderEscapesQuotesAndBackslashes(t *testing.T) {
	doc, err := parseTOML("[settings.npm]\npackage_manager = \"bun\"\n\n[tools]\n\"github:google-antigravity/antigravity-cli\" = { version = \"1.4.2\", rename_exe = \"a\\\"b\\\\c\" }\n")
	if err != nil {
		t.Fatalf("parseTOML: %v", err)
	}
	body, err := renderHeredocBody(doc)
	if err != nil {
		t.Fatalf("renderHeredocBody: %v", err)
	}
	got, err := parseTOML(body)
	if err != nil {
		t.Fatalf("escaped output does not parse: %v", err)
	}
	want := "a\"b\\c"
	inner := got.must("tools").must("github:google-antigravity/antigravity-cli").mustStr("rename_exe")
	if inner != want {
		t.Errorf("round trip: got %q, want %q", inner, want)
	}
}

// ---------- the invariants ----------

func TestValidateAcceptsTheCommittedSource(t *testing.T) {
	root := repoRoot(t)
	doc := loadSourceDoc(t, root)
	host := loadHostDoc(t, root)
	if problems := validate(doc, host); len(problems) != 0 {
		t.Errorf("committed source has problems: %v", problems)
	}
}

func TestValidateRejects(t *testing.T) {
	root := repoRoot(t)
	base := loadSourceDoc(t, root)
	host := loadHostDoc(t, root)
	cases := map[string]struct {
		mutate func(*table)
		want   string
	}{
		"channel instead of a pin": {
			mutate: func(d *table) { d.must("tools").set(`npm:cf`, strValue("latest")) },
			want:   "full version",
		},
		"partial version": {
			mutate: func(d *table) { d.must("tools").set("node", strValue("24")) },
			want:   "full version",
		},
		"tool missing on the host": {
			mutate: func(d *table) { d.must("tools").set("not-a-tool", strValue("1.0.0")) },
			want:   "not declared",
		},
		"exact pin disagrees with the host": {
			mutate: func(d *table) { d.must("tools").set(`npm:cf`, strValue("9.9.9")) },
			want:   "must agree",
		},
		"fetch names a tool that is not in [tools]": {
			mutate: func(d *table) { d.must("fetch").set("mise_tools", listValue("uv", "nope")) },
			want:   "mise_tools",
		},
		"bootstrap is a channel": {
			mutate: func(d *table) { d.must("bootstrap").set("mise", strValue("latest")) },
			want:   "full version",
		},
	}
	for name, tc := range cases {
		doc := cloneTable(base)
		tc.mutate(doc)
		problems := validate(doc, host)
		if len(problems) == 0 {
			t.Errorf("%s: validate accepted it", name)
			continue
		}
		joined := strings.Join(problems, "; ")
		if !strings.Contains(joined, tc.want) {
			t.Errorf("%s: problems = %v, want a message containing %q", name, problems, tc.want)
		}
	}
}

// ---------- the CLI ----------

func TestCheckAcceptsTheCommittedTree(t *testing.T) {
	code, stdout, stderr := runCLI(t, "check", "--root", repoRoot(t))
	if code != 0 {
		t.Fatalf("check = %d, want 0 (stdout %q, stderr %q)", code, stdout, stderr)
	}
	if !strings.Contains(stdout, "up to date") {
		t.Errorf("stdout = %q, want it to say up to date", stdout)
	}
}

func TestCheckReportsEveryOneSidedEdit(t *testing.T) {
	for name, tc := range map[string]struct{ rel, old, new string }{
		"source only":      {sourceRel, `"aqua:rossmacarthur/sheldon" = "0.8.5"`, `"aqua:rossmacarthur/sheldon" = "0.9.0"`},
		"host only":        {hostRel, `"aqua:rossmacarthur/sheldon" = { version = "0.8.5"`, `"aqua:rossmacarthur/sheldon" = { version = "0.9.0"`},
		"generated region": {featureRel, `bun = "1.4.4"`, `bun = "1.4.5"`},
		"bootstrap const":  {bootstrapRel, `_mise_ver="2026.10.17"`, `_mise_ver="2026.8.0"`},
	} {
		root := tree(t)
		mutate(t, root, tc.rel, tc.old, tc.new)
		code, stdout, stderr := runCLI(t, "check", "--root", root)
		if code == 0 {
			t.Errorf("%s: check = 0, want non-zero", name)
		}
		if !strings.Contains(stdout+stderr, "mise-versions") {
			t.Errorf("%s: no report (stdout %q, stderr %q)", name, stdout, stderr)
		}
	}
}

func TestSyncIsIdempotentAndWritesNothingWhenItFails(t *testing.T) {
	// The committed tree is already in sync, so nothing is written.
	clean := tree(t)
	if code, stdout, _ := runCLI(t, "check", "--root", clean); code != 0 {
		t.Fatalf("check on the temp copy = %d: %s", code, stdout)
	}
	if code, stdout, _ := runCLI(t, "sync", "--root", clean); code != 0 || !strings.Contains(stdout, "up to date") {
		t.Errorf("sync on a clean tree: code %d, stdout %q", code, stdout)
	}
	// A broken source must not touch either file.
	broken := tree(t)
	before := read(t, filepath.Join(broken, featureRel)) + read(t, filepath.Join(broken, bootstrapRel))
	mutate(t, broken, sourceRel, `node = "24.22.1"`, `node = "24"`)
	if code, _, _ := runCLI(t, "sync", "--root", broken); code == 0 {
		t.Fatal("sync accepted a partial version")
	}
	after := read(t, filepath.Join(broken, featureRel)) + read(t, filepath.Join(broken, bootstrapRel))
	if before != after {
		t.Error("a failed sync wrote to disk")
	}
}

func TestDefaultRootFollowsTheSourceFile(t *testing.T) {
	root, err := defaultRoot()
	if err != nil {
		t.Fatalf("defaultRoot: %v", err)
	}
	rootAbs, err := filepath.Abs(root)
	if err != nil {
		t.Fatal(err)
	}
	wantAbs, err := filepath.Abs(repoRoot(t))
	if err != nil {
		t.Fatal(err)
	}
	if rootAbs != wantAbs {
		t.Errorf("defaultRoot = %q, want %q", rootAbs, wantAbs)
	}
	if !fileExists(filepath.Join(rootAbs, sourceRel)) {
		t.Errorf("defaultRoot %q does not hold %s", rootAbs, sourceRel)
	}
	// The working directory must not matter, and --root must win.
	cwd, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Chdir(t.TempDir()); err != nil {
		t.Fatal(err)
	}
	defer func() { _ = os.Chdir(cwd) }()
	fromElsewhere, err := defaultRoot()
	if err != nil {
		t.Fatalf("defaultRoot from another directory: %v", err)
	}
	if fromElsewhere != root {
		t.Errorf("defaultRoot depends on the working directory: %q != %q", fromElsewhere, root)
	}
}

func sameStrings(got, want []string) bool {
	if len(got) != len(want) {
		return false
	}
	for i := range got {
		if got[i] != want[i] {
			return false
		}
	}
	return true
}
