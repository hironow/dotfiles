package rules

import (
	"errors"
	"fmt"
	"io"
	"regexp"
	"slices"
	"strings"
	"unicode/utf8"

	"github.com/goccy/go-json"
)

const (
	corpusBinaryOnly = "tests/unit/corpus_binary_only.json"
	corpusFiles      = "tools/agent-hooks/internal/guardcorpus/files-guard.jsonl"
	corpusPayloads   = "tools/agent-hooks/internal/guardcorpus/payloads.jsonl"
	corpusRTK        = "tools/agent-hooks/internal/toolhookcorpus/rtk.jsonl"
	corpusFormatter  = "tools/agent-hooks/internal/toolhookcorpus/formatter.jsonl"
)

var corpusJSONConstants = regexp.MustCompile(`"(?:\\.|[^"\\])*"|-?Infinity|NaN`)

// Python accepts non-finite numbers. Their values never enter label checks.
func corpusJSONInput(line string) string {
	return corpusJSONConstants.ReplaceAllStringFunc(line, func(token string) string {
		if token[0] == '"' {
			return token
		}
		return "null"
	})
}

func corpusDifferenceFacts() Rule {
	return factRule("corpus-difference-facts", "corpora never claim a fix that only the binary can show",
		[]string{corpusBinaryOnly, corpusFiles, corpusPayloads, corpusRTK, corpusFormatter},
		[]scriptFact{fact("test_no_corpus_claims_a_binary_only_fix", corpusNoBinaryOnly)})
}

func corpusNoBinaryOnly(files map[string]string) []string {
	if !utf8.ValidString(files[corpusBinaryOnly]) {
		return []string{corpusBinaryOnly + " must decode as strict UTF-8"}
	}
	var registry map[string]json.RawMessage
	if err := json.Unmarshal([]byte(files[corpusBinaryOnly]), &registry); err != nil {
		return []string{fmt.Sprintf("%s: %v", corpusBinaryOnly, err)}
	}
	used := map[string]bool{}
	for _, path := range []string{corpusFiles, corpusPayloads, corpusRTK, corpusFormatter} {
		if !utf8.ValidString(files[path]) {
			return []string{path + " must decode as strict UTF-8"}
		}
		for n, line := range pySplitlines(files[path]) {
			differences, err := corpusLineDifferences(line, path == corpusFiles)
			if err != nil {
				return []string{fmt.Sprintf("%s:%d: %v", path, n+1, err)}
			}
			for _, difference := range differences {
				for part := range strings.SplitSeq(difference, "+") {
					used[part] = true
				}
			}
		}
	}
	names := make([]string, 0, len(registry))
	for name := range registry {
		names = append(names, name)
	}
	slices.Sort(names)
	var out []string
	for _, name := range names {
		if used[name] {
			out = append(out, name+" is binary-only, but a corpus holds it")
		}
	}
	return out
}

// corpusLineDifferences reads only bsd/gnu or runs, as _differences did.
func corpusLineDifferences(line string, flavors bool) ([]string, error) {
	var entry map[string]any
	decoder := json.NewDecoder(strings.NewReader(corpusJSONInput(line)))
	decoder.UseNumber()
	if err := decoder.Decode(&entry); err != nil {
		return nil, fmt.Errorf("decode JSON: %w", err)
	}
	if err := decoder.Decode(new(any)); !errors.Is(err, io.EOF) {
		return nil, errors.New("expected exactly one JSON value")
	}
	var selected []map[string]any
	if flavors {
		for _, flavor := range []string{"bsd", "gnu"} {
			t, ok := table(entry, flavor)
			if !ok {
				return nil, fmt.Errorf("missing %s object", flavor)
			}
			selected = append(selected, t)
		}
	} else {
		runs, err := corpusRuns(entry["runs"])
		if err != nil {
			return nil, err
		}
		for _, run := range runs {
			t, ok := run.(map[string]any)
			if !ok {
				return nil, errors.New("run must be an object")
			}
			selected = append(selected, t)
		}
	}
	var out []string
	for _, t := range selected {
		difference, ok := str(t, "difference")
		if !ok {
			if _, present := t["difference"]; present || !flavors {
				return nil, errors.New("missing or non-string difference")
			}
		}
		out = append(out, difference)
	}
	return out, nil
}

func corpusRuns(value any) ([]any, error) {
	switch runs := value.(type) {
	case []any:
		return runs, nil
	case map[string]any:
		if len(runs) == 0 {
			return nil, nil
		}
	case string:
		if runs == "" {
			return nil, nil
		}
	default:
		return nil, errors.New("runs is not iterable")
	}
	// Nonempty dicts and strings yield strings; Python cannot index these
	// with ["difference"]. Empty iterables never reach that lookup.
	return nil, errors.New("run string cannot be indexed by difference")
}
