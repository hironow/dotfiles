package rules

import (
	"fmt"
	"regexp"
	"strings"
)

// scriptFact is one removed test that read a script's text, ported with its
// own pattern over the part of the file it searched (ADR-0093). check returns
// the test's failed assertions.
type scriptFact struct {
	test  string
	check func(files map[string]string) []string
}

// factCheck is one assertion of a removed test.
type factCheck func(files map[string]string) []string

// fact joins a test's assertions.
func fact(test string, checks ...factCheck) scriptFact {
	return scriptFact{test: test, check: func(files map[string]string) []string {
		var out []string
		for _, c := range checks {
			out = append(out, c(files)...)
		}
		return out
	}}
}

// factRule is a rule over the files its facts read; a finding names the
// removed test, so a reader finds why the line matters.
func factRule(id, why string, paths []string, facts []scriptFact) Rule {
	inputs := make([]Input, 0, len(paths))
	for _, p := range paths {
		inputs = append(inputs, Input{Path: p, Format: Text})
	}
	return Rule{
		ID:     id,
		Why:    why,
		Inputs: inputs,
		Check: func(in Inputs) []Finding {
			files := map[string]string{}
			for _, p := range paths {
				text, _ := in[p].(string)
				files[p] = universalNewlines.Replace(text)
			}
			r := &report{rule: id, path: paths[0]}
			for _, f := range facts {
				for _, problem := range f.check(files) {
					r.add("%s: %s", f.test, problem)
				}
			}
			return r.out
		},
	}
}

// universalNewlines reads a file as Python's read_text() did for the
// removed tests: "\r\n" and a lone "\r" both become "\n".
var universalNewlines = strings.NewReplacer("\r\n", "\n", "\r", "\n")

// has: the file holds each string (`s in text`).
func has(path string, subs ...string) factCheck {
	return func(files map[string]string) []string {
		var out []string
		for _, s := range subs {
			if !strings.Contains(files[path], s) {
				out = append(out, fmt.Sprintf("%s must hold %q", path, s))
			}
		}
		return out
	}
}

// lacks: the file holds none of the strings (`s not in text`).
func lacks(path string, subs ...string) factCheck {
	return func(files map[string]string) []string {
		var out []string
		for _, s := range subs {
			if strings.Contains(files[path], s) {
				out = append(out, fmt.Sprintf("%s must not hold %q", path, s))
			}
		}
		return out
	}
}

// matches: re.search of each pattern over the whole file finds a match.
func matches(path string, patterns ...string) factCheck {
	res := compileAll(patterns)
	return func(files map[string]string) []string {
		var out []string
		for _, re := range res {
			if !re.MatchString(files[path]) {
				out = append(out, fmt.Sprintf("%s must match %s", path, re))
			}
		}
		return out
	}
}

// noMatch: re.search of each pattern over the whole file finds nothing.
func noMatch(path string, patterns ...string) factCheck {
	res := compileAll(patterns)
	return func(files map[string]string) []string {
		var out []string
		for _, re := range res {
			if m := re.FindString(files[path]); m != "" {
				out = append(out, fmt.Sprintf("%s must not match %s: %q", path, re, m))
			}
		}
		return out
	}
}

// noLine: no line of the file matches any pattern (the tests' per-line
// comprehensions).
func noLine(path string, patterns ...string) factCheck {
	res := compileAll(patterns)
	return func(files map[string]string) []string {
		var out []string
		for line := range strings.SplitSeq(files[path], "\n") {
			for _, re := range res {
				if re.MatchString(line) {
					out = append(out, fmt.Sprintf("%s: line %q matches %s", path, strings.TrimSpace(line), re))
				}
			}
		}
		return out
	}
}

// anyOf passes when one of the checks passes (`a in text or b in text`).
func anyOf(checks ...factCheck) factCheck {
	return func(files map[string]string) []string {
		var out []string
		for _, c := range checks {
			problems := c(files)
			if len(problems) == 0 {
				return nil
			}
			out = append(out, problems...)
		}
		return []string{"none of: " + strings.Join(out, "; ")}
	}
}

func compileAll(patterns []string) []*regexp.Regexp {
	res := make([]*regexp.Regexp, 0, len(patterns))
	for _, p := range patterns {
		res = append(res, regexp.MustCompile(p))
	}
	return res
}

// codeLines is the lines that are not comments (`not line.lstrip().startswith("#")`).
func codeLinesOf(text string) []string {
	var out []string
	for line := range strings.SplitSeq(text, "\n") {
		if !strings.HasPrefix(strings.TrimLeft(line, " \t"), "#") {
			out = append(out, line)
		}
	}
	return out
}
