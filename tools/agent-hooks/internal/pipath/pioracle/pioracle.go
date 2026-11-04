// Package pioracle runs Pi's own path resolution under node: resolveToCwd from
// the installed Pi 1.4.0 package, the function Pi's write and edit tools call.
// It is the oracle internal/pipath is checked against, and what
// corpus.jsonl there records (`just pi-paths-corpus`). It needs node and Pi
// 1.4.0 on PATH; the tests skip where either is missing.
package pioracle

import (
	"bytes"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"unicode/utf16"
	"unicode/utf8"

	json "github.com/goccy/go-json/v2"
)

// PiVersion is the Pi release whose resolveToCwd the corpus records.
const PiVersion = "1.4.0"

// piPackage is the npm package Pi is published as.
const piPackage = "@earendil-works/pi-coding-agent"

// Case is one input: a tool's path, the cwd Pi resolves it against, and HOME
// as Pi's process has it (Node's os.homedir() returns HOME when it is set,
// even to "").
type Case struct {
	Path string `json:"path"`
	Cwd  string `json:"cwd"`
	Home string `json:"home"`
}

// Answer is what Pi made of a case: the path it resolves to, or the error it
// throws (the error's code, else its name).
type Answer struct {
	Resolved *string `json:"resolved,omitempty"`
	Error    string  `json:"error,omitempty"`
}

// Find returns node and the path of Pi's path-utils module, both found
// through PATH. Pi is found through its `pi` program, whose real path is
// its package's dist/bundle/cli.js; a mise shim is followed to the program
// it runs. Any other Pi version is refused.
func Find() (node, module string, err error) {
	node, root, err := FindPackage()
	if err != nil {
		return "", "", err
	}
	module = filepath.Join(root, "dist", "core", "tools", "path-utils.js")
	if _, err := os.Stat(module); err != nil {
		return "", "", fmt.Errorf("pi's path-utils module: %w", err)
	}
	return node, module, nil
}

// FindPackage returns node and the installed Pi 1.4.0 package root. Both
// oracles use this discovery so they cannot silently select different Pi releases.
func FindPackage() (node, root string, err error) {
	node, err = exec.LookPath("node")
	if err != nil {
		return "", "", fmt.Errorf("no node on PATH: %w", err)
	}
	pi, err := exec.LookPath("pi")
	if err != nil {
		return "", "", fmt.Errorf("no pi on PATH: %w", err)
	}
	real, err := filepath.EvalSymlinks(pi)
	if err != nil {
		return "", "", fmt.Errorf("pi on PATH does not resolve: %w", err)
	}
	if filepath.Base(real) == "mise" {
		// A mise shim is mise itself; mise says which program it runs.
		if real, err = programBehindShim(real); err != nil {
			return "", "", err
		}
	}
	if filepath.Base(real) != "cli.js" || filepath.Base(filepath.Dir(real)) != "bundle" {
		return "", "", errors.New("pi on PATH is not a package's dist/bundle/cli.js")
	}
	root = filepath.Dir(filepath.Dir(filepath.Dir(real)))
	manifest, err := os.ReadFile(filepath.Join(root, "package.json"))
	if err != nil {
		return "", "", fmt.Errorf("pi's package.json: %w", err)
	}
	var pkg struct {
		Name    string `json:"name"`
		Version string `json:"version"`
	}
	if err := json.Unmarshal(manifest, &pkg); err != nil {
		return "", "", fmt.Errorf("pi's package.json: %w", err)
	}
	if pkg.Name != piPackage || pkg.Version != PiVersion {
		return "", "", fmt.Errorf("pi on PATH is %s %s, not %s %s", pkg.Name, pkg.Version, piPackage, PiVersion)
	}
	return node, root, nil
}

// programBehindShim is the real path of the pi program a mise shim runs.
func programBehindShim(mise string) (string, error) {
	out, err := exec.Command(mise, "which", "pi").Output()
	if err != nil {
		return "", fmt.Errorf("mise which pi: %w", err)
	}
	real, err := filepath.EvalSymlinks(strings.TrimSpace(string(out)))
	if err != nil {
		return "", fmt.Errorf("the pi mise runs does not resolve: %w", err)
	}
	return real, nil
}

// script reads the cases on stdin and answers each with Pi's resolveToCwd,
// HOME set as the case has it.
const script = `import { pathToFileURL } from "node:url";
const { resolveToCwd } = await import(pathToFileURL(process.argv[1]).href);
process.stdin.setEncoding("utf8");
let input = "";
for await (const chunk of process.stdin) input += chunk;
const answers = JSON.parse(input).map(({ path, cwd, home }) => {
  process.env.HOME = home;
  try {
    return { resolved: resolveToCwd(path, cwd) };
  } catch (error) {
    return { error: String(error?.code ?? error?.name ?? "Error") };
  }
});
process.stdout.write(JSON.stringify(answers));
`

// Run answers every case with Pi's resolveToCwd, in one node process that
// inherits nothing but PATH.
func Run(node, module string, cases []Case) ([]Answer, error) {
	input, err := json.Marshal(cases)
	if err != nil {
		return nil, err
	}
	command := exec.Command(node, "--input-type=module", "-e", script, module)
	command.Env = []string{"PATH=" + os.Getenv("PATH")}
	command.Stdin = bytes.NewReader(input)
	var stdout, stderr bytes.Buffer
	command.Stdout, command.Stderr = &stdout, &stderr
	if err := command.Run(); err != nil {
		return nil, fmt.Errorf("node: %w: %s", err, strings.TrimSpace(stderr.String()))
	}
	var answers []Answer
	if err := json.Unmarshal(stdout.Bytes(), &answers); err != nil {
		return nil, fmt.Errorf("node's answers: %w", err)
	}
	if len(answers) != len(cases) {
		return nil, fmt.Errorf("node answered %d cases of %d", len(answers), len(cases))
	}
	for i, answer := range answers {
		if (answer.Resolved == nil) == (answer.Error == "") {
			return nil, fmt.Errorf("case %d: an answer needs a path or an error, not both or none", i)
		}
	}
	return answers, nil
}

// header is the corpus's first line.
type header struct {
	Pi string `json:"pi"`
}

// Entry is one line of the corpus after its header: a case and Pi's answer.
type Entry struct {
	Case
	Answer
}

// Render writes the corpus: a header naming the Pi version, then one line
// per case with Pi's answer.
func Render(cases []Case, answers []Answer) ([]byte, error) {
	if len(cases) != len(answers) {
		return nil, errors.New("a case and an answer go together")
	}
	var out bytes.Buffer
	line, err := json.Marshal(header{Pi: PiVersion})
	if err != nil {
		return nil, err
	}
	out.Write(ASCIILine(line))
	out.WriteByte('\n')
	for i := range cases {
		line, err := json.Marshal(Entry{Case: cases[i], Answer: answers[i]})
		if err != nil {
			return nil, err
		}
		out.Write(ASCIILine(line))
		out.WriteByte('\n')
	}
	return out.Bytes(), nil
}

// ASCIILine escapes every non-ASCII character of a JSON line as \uXXXX
// (a surrogate pair above U+FFFF), as Python's json.dumps writes the
// repo's other corpora. A corpus then holds no U+2028, U+0085, or other
// character that some tools split lines on. Non-ASCII characters only
// stand inside JSON strings, where the escape means the same.
func ASCIILine(line []byte) []byte {
	var out bytes.Buffer
	for _, r := range string(line) {
		switch {
		case r < utf8.RuneSelf:
			out.WriteRune(r)
		case r > 0xffff:
			high, low := utf16.EncodeRune(r)
			fmt.Fprintf(&out, "\\u%04x\\u%04x", high, low)
		default:
			fmt.Fprintf(&out, "\\u%04x", r)
		}
	}
	return out.Bytes()
}

// Parse reads a corpus Render wrote.
func Parse(corpus []byte) ([]Entry, error) {
	lines := bytes.Split(bytes.TrimSuffix(corpus, []byte("\n")), []byte("\n"))
	var head header
	if err := json.Unmarshal(lines[0], &head, json.RejectUnknownMembers(true)); err != nil {
		return nil, fmt.Errorf("header: %w", err)
	}
	if head.Pi != PiVersion {
		return nil, fmt.Errorf("the corpus is Pi %s's, not %s's", head.Pi, PiVersion)
	}
	entries := make([]Entry, 0, len(lines)-1)
	for i, line := range lines[1:] {
		var entry Entry
		if err := json.Unmarshal(line, &entry, json.RejectUnknownMembers(true)); err != nil {
			return nil, fmt.Errorf("line %d: %w", i+2, err)
		}
		entries = append(entries, entry)
	}
	return entries, nil
}
