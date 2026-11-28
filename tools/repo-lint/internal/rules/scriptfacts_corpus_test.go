package rules

import (
	"strings"
	"testing"
)

func corpusBase() Inputs {
	return Inputs{
		corpusBinaryOnly: `{"fixed-guard-failure":["bug","path","TestGuard"]}`,
		corpusFiles:      `{"bsd":{},"gnu":{"difference":"pass-diagnostic"},"difference":"fixed-guard-failure"}` + "\n",
		corpusPayloads:   `{"runs":[{"difference":""}]}` + "\n",
		corpusRTK:        `{"runs":[{"difference":"parity+noise"}],"difference":"fixed-guard-failure"}`,
		corpusFormatter:  `{"runs":[{"difference":""}]}`,
	}
}

func TestCorpusDifferenceFacts(t *testing.T) {
	runCases(t, corpusDifferenceFacts(), corpusBase, []ruleCase{
		{"bsd difference", edit(corpusFiles, `"bsd":{}`, `"bsd":{"difference":"pass-diagnostic+fixed-guard-failure"}`), "test_no_corpus_claims_a_binary_only_fix"},
		{"gnu difference", edit(corpusFiles, "pass-diagnostic", "pass-diagnostic+fixed-guard-failure"), "test_no_corpus_claims_a_binary_only_fix"},
		{"payload difference", edit(corpusPayloads, `"difference":""`, `"difference":"+fixed-guard-failure+"`), "test_no_corpus_claims_a_binary_only_fix"},
		{"rtk difference", edit(corpusRTK, "parity+noise", "fixed-guard-failure+fixed-guard-failure"), "test_no_corpus_claims_a_binary_only_fix"},
		{"formatter difference", edit(corpusFormatter, `"difference":""`, `"difference":"fixed-guard-failure"`), "test_no_corpus_claims_a_binary_only_fix"},
		{"blank JSON line", edit(corpusFiles, "\n", "\n\n"), "test_no_corpus_claims_a_binary_only_fix"},
		{"required difference missing", edit(corpusPayloads, `"difference":""`, `"else":""`), "test_no_corpus_claims_a_binary_only_fix"},
		{"missing flavor", edit(corpusFiles, `"bsd":{}`, `"other":{}`), "test_no_corpus_claims_a_binary_only_fix"},
		{"required runs missing", edit(corpusRTK, `"runs":`, `"other":`), "test_no_corpus_claims_a_binary_only_fix"},
		{"invalid registry", edit(corpusBinaryOnly, "{", "["), "test_no_corpus_claims_a_binary_only_fix"},
		{"invalid UTF-8 registry", edit(corpusBinaryOnly, "bug", "\xff"), "test_no_corpus_claims_a_binary_only_fix"},
		{"invalid UTF-8 corpus", edit(corpusRTK, "parity+noise", "\xff"), "test_no_corpus_claims_a_binary_only_fix"},
		{"trailing JSON", edit(corpusPayloads, `{"runs":`, `{} {"runs":`), "test_no_corpus_claims_a_binary_only_fix"},
	})
}

func TestCorpusRunsKeepPythonIterationSemantics(t *testing.T) {
	cases := []struct {
		name     string
		runs     string
		wantFail bool
	}{
		{"empty array", `[]`, false},
		{"array of runs", `[{"difference":"parity"},{"difference":""}]`, false},
		{"array with binary-only label", `[{"difference":"fixed-guard-failure"}]`, true},
		{"array of strings", `["difference"]`, true},
		{"array of null", `[null]`, true},
		{"empty dict", `{}`, false},
		// Python iterates dict keys and string characters, then rejects their
		// string["difference"] lookup with TypeError.
		{"dict of runs", `{"first":{"difference":"parity"}}`, true},
		{"dict with empty key", `{"":{"difference":"parity"}}`, true},
		{"empty string", `""`, false},
		{"string", `"parity"`, true},
		{"unicode string", `"界"`, true},
		// Null, numbers and booleans raise TypeError before iteration, even
		// when Python considers their value false.
		{"null", `null`, true},
		{"zero", `0`, true},
		{"integer", `1`, true},
		{"float", `1.5`, true},
		{"false", `false`, true},
		{"true", `true`, true},
	}
	for _, path := range []string{corpusPayloads, corpusRTK, corpusFormatter} {
		for _, tc := range cases {
			t.Run(path+"/"+tc.name, func(t *testing.T) {
				in := corpusBase()
				in[path] = `{"runs":` + tc.runs + `}`
				got := findingsOf(t, corpusDifferenceFacts(), in)
				if (len(got) != 0) != tc.wantFail {
					t.Fatalf("runs=%s: want failure %t, got %v", tc.runs, tc.wantFail, got)
				}
				if tc.wantFail && (len(got) != 1 || !strings.Contains(got[0].Message, "test_no_corpus_claims_a_binary_only_fix")) {
					t.Fatalf("expected the corpus fact to fail: %v", got)
				}
			})
		}
	}
}

func TestCorpusIgnoresLargeNumbersOutsideDifferences(t *testing.T) {
	for _, path := range []string{corpusFiles, corpusPayloads, corpusRTK, corpusFormatter} {
		t.Run(path, func(t *testing.T) {
			in := corpusBase()
			in[path] = strings.ReplaceAll(in[path].(string), "{", `{"ignored":1e400,`)
			in[path] = strings.ReplaceAll(in[path].(string), ",}", "}")
			if got := findingsOf(t, corpusDifferenceFacts(), in); len(got) != 0 {
				t.Fatalf("unused numbers must not change difference checks: %v", got)
			}
		})
	}
}

func TestCorpusIgnoresNonFiniteNumbersOutsideDifferences(t *testing.T) {
	for _, literal := range []string{"NaN", "Infinity", "-Infinity"} {
		for _, path := range []string{corpusFiles, corpusPayloads, corpusRTK, corpusFormatter} {
			t.Run(literal+"/"+path, func(t *testing.T) {
				in := corpusBase()
				in[path] = strings.Replace(in[path].(string), "{", `{"ignored":[`+literal+`,{"nested":`+literal+`}],`, 1)
				if got := findingsOf(t, corpusDifferenceFacts(), in); len(got) != 0 {
					t.Fatalf("unused Python JSON constants must not change difference checks: %v", got)
				}
			})
		}
	}
}

func TestCorpusJSONConstantsKeepLabelsAndSyntax(t *testing.T) {
	for _, label := range []string{"NaN", "Infinity", "-Infinity", `escaped\"NaN`, `escaped\\Infinity`} {
		t.Run(label, func(t *testing.T) {
			in := corpusBase()
			in[corpusBinaryOnly] = `{"` + label + `":["bug","path","TestGuard"]}`
			in[corpusPayloads] = `{"runs":[{"difference":"` + label + `"}]}`
			got := findingsOf(t, corpusDifferenceFacts(), in)
			if len(got) != 1 || !strings.Contains(got[0].Message, "is binary-only, but a corpus holds it") {
				t.Fatalf("quoted constants must still be checked as labels: %v", got)
			}
		})
	}
	for _, literal := range []string{"NaN", "Infinity", "-Infinity", "Infinitye5", "NaNx", "+Infinity", "-NaN"} {
		t.Run(literal+" is not a string", func(t *testing.T) {
			in := corpusBase()
			in[corpusPayloads] = `{"runs":[{"difference":` + literal + `}]}`
			if got := findingsOf(t, corpusDifferenceFacts(), in); len(got) == 0 {
				t.Fatal("non-string and invalid values must still be rejected")
			}
		})
	}
	for _, literal := range []string{"Infinitye5", "NaNx", "+Infinity", "-NaN"} {
		t.Run(literal+" is invalid even when ignored", func(t *testing.T) {
			in := corpusBase()
			in[corpusPayloads] = `{"runs":[],"ignored":` + literal + `}`
			if got := findingsOf(t, corpusDifferenceFacts(), in); len(got) == 0 {
				t.Fatal("invalid syntax must still be rejected")
			}
		})
	}
}

func TestCorpusDifferencesKeepPythonSemantics(t *testing.T) {
	for _, difference := range []string{"FIXED-guard-failure", "fixed-guard-failure-extra", " fixed-guard-failure", "fixed-guard-failure "} {
		in := corpusBase()
		in[corpusPayloads] = `{"runs":[{"difference":"` + difference + `"}]}`
		if got := findingsOf(t, corpusDifferenceFacts(), in); len(got) != 0 {
			t.Errorf("exact case-sensitive labels: %v", got)
		}
	}
	in := corpusBase()
	in[corpusFiles] = strings.ReplaceAll(in[corpusFiles].(string), "\n", "\r")
	in[corpusRTK] = in[corpusRTK].(string) + "\u0085" + in[corpusRTK].(string) + "\u2028"
	if got := findingsOf(t, corpusDifferenceFacts(), in); len(got) != 0 {
		t.Errorf("universal newlines and splitlines: %v", got)
	}
	in[corpusBinaryOnly] = `{"": ["bug","path","TestEmpty"]}`
	if got := findingsOf(t, corpusDifferenceFacts(), in); len(got) == 0 {
		t.Error("literal + split retains empty labels")
	}
}
