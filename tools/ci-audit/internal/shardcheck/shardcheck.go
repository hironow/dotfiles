// Package shardcheck proves that the shards of a split test run together ran
// every test they were given, once, and says how unevenly they were balanced.
//
// It is a pure core: it takes values (each shard's collected list and its
// JUnit cases) and returns a Report. Reading files is the caller's job.
//
// The id contract: pytest's collect-only prints a node id such as
// "tests/unit/test_b.py::TestThing::test_method[param]"; JUnit writes the same
// test as classname "tests.unit.test_b.TestThing" and name
// "test_method[param]". KeyOf maps the first to the second. xdist 3.8.0's
// loadgroup run was checked on the real suite: 5156 collected, 5156 in JUnit,
// the sets equal, no "@group" suffix. An id that is not in the collected set is
// "unexpected" and fails the check; a suffix is never stripped.
package shardcheck

import (
	"bytes"
	"encoding/xml"
	"fmt"
	"maps"
	"slices"
	"sort"
	"strings"
)

// Key identifies a test the way JUnit does.
type Key struct {
	Class string
	Name  string
}

// Case is one executed test from a shard's JUnit report.
type Case struct {
	Key     Key
	Seconds float64
	Outcome string // passed, skipped, failed, error
}

// Shard is one job's collected list and its executed cases.
type Shard struct {
	Name      string
	Collected []string
	Cases     []Case
}

// Options tune the check.
type Options struct {
	// MaxImbalance is the largest allowed ratio of the slowest shard to the
	// mean shard. 0 turns the check off.
	MaxImbalance float64
}

// Report is the outcome of Check.
type Report struct {
	Expected       int
	Executed       int
	Missing        []string
	Unexpected     []string
	Duplicates     []string
	DifferingLists []string
	EmptyShards    []string
	// SkippedModules are modules that skipped themselves at collection
	// (pytest.skip(allow_module_level=True)). They have no collected ids, and
	// every shard reports them, so they are listed once and are not tests.
	SkippedModules []string
	// BrokenModules are modules whose collection failed: always a problem.
	BrokenModules []string
	Imbalance     float64
	ShardSeconds  map[string]float64
	Durations     map[string]float64
	Problems      []string
}

// OK reports whether the check found no problem.
func (r Report) OK() bool { return len(r.Problems) == 0 }

// KeyOf maps a pytest node id to the JUnit (classname, name) pair pytest writes.
func KeyOf(nodeID string) Key {
	path, params, hasParams := splitParams(nodeID)
	parts := strings.Split(path, "::")
	module := strings.ReplaceAll(parts[0], "/", ".")
	module = strings.TrimSuffix(module, ".py")
	name := parts[len(parts)-1]
	if hasParams {
		name += "[" + params
	}
	classParts := append([]string{module}, parts[1:len(parts)-1]...)
	if len(parts) == 1 {
		return Key{Class: module, Name: ""}
	}
	return Key{Class: strings.Join(classParts, "."), Name: name}
}

// splitParams cuts the id at the first "[" that starts the parameter list, so
// "::" or "/" inside the parameters never reach the path.
func splitParams(id string) (path, params string, ok bool) {
	i := strings.Index(id, "[")
	if i < 0 {
		return id, "", false
	}
	return id[:i], id[i+1:], true
}

// ParseCollected reads `pytest --collect-only -q` output and keeps the node ids.
func ParseCollected(data []byte) []string {
	var ids []string
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if strings.Contains(line, "::") && !strings.Contains(line, " tests collected") && !strings.Contains(line, ": ") || isParamID(line) {
			ids = append(ids, line)
		}
	}
	return ids
}

// isParamID accepts an id whose parameters hold ": " (such as "[Help: lists targets]").
func isParamID(line string) bool {
	i := strings.Index(line, "::")
	if i < 0 {
		return false
	}
	head := line[:i]
	return strings.HasSuffix(head, ".py") && !strings.ContainsAny(head, " :")
}

type junitCase struct {
	Class   string      `xml:"classname,attr"`
	Name    string      `xml:"name,attr"`
	Time    float64     `xml:"time,attr"`
	Failure *struct{}   `xml:"failure"`
	Error   *struct{}   `xml:"error"`
	Skipped *struct{}   `xml:"skipped"`
	Cases   []junitCase `xml:"-"`
}

type junitSuite struct {
	Cases []junitCase `xml:"testcase"`
}

type junitRoot struct {
	Suites []junitSuite `xml:"testsuite"`
	Cases  []junitCase  `xml:"testcase"`
}

// ParseJUnit reads a JUnit report and returns every testcase with its outcome.
func ParseJUnit(data []byte) ([]Case, error) {
	var root junitRoot
	dec := xml.NewDecoder(bytes.NewReader(data))
	if err := dec.Decode(&root); err != nil {
		return nil, fmt.Errorf("read junit: %w", err)
	}
	raw := append([]junitCase(nil), root.Cases...)
	for _, s := range root.Suites {
		raw = append(raw, s.Cases...)
	}
	cases := make([]Case, 0, len(raw))
	for _, c := range raw {
		outcome := "passed"
		switch {
		case c.Failure != nil:
			outcome = "failed"
		case c.Error != nil:
			outcome = "error"
		case c.Skipped != nil:
			outcome = "skipped"
		}
		cases = append(cases, Case{Key: Key{Class: c.Class, Name: c.Name}, Seconds: c.Time, Outcome: outcome})
	}
	return cases, nil
}

// Check compares what every shard ran with what it was given.
func Check(shards []Shard, opt Options) Report {
	r := Report{ShardSeconds: map[string]float64{}, Durations: map[string]float64{}}
	if len(shards) == 0 {
		r.Problems = append(r.Problems, "no shard reports were given")
		return r
	}
	reference := shards[0].Collected
	expected := map[Key]string{}
	for _, id := range reference {
		expected[KeyOf(id)] = id
	}
	r.Expected = len(expected)
	for _, s := range shards {
		if !sameSet(reference, s.Collected) {
			r.DifferingLists = append(r.DifferingLists, s.Name)
		}
		if len(s.Cases) == 0 {
			r.EmptyShards = append(r.EmptyShards, s.Name)
		}
	}
	seen := map[Key]int{}
	skipped, broken := map[string]bool{}, map[string]bool{}
	for _, s := range shards {
		for _, c := range s.Cases {
			// pytest writes a module-level report with an empty classname and
			// the module as the name; a real test always has a classname.
			if c.Key.Class == "" {
				if c.Outcome == "skipped" {
					skipped[c.Key.Name] = true
				} else {
					broken[c.Key.Name] = true
				}
				continue
			}
			seen[c.Key]++
			r.ShardSeconds[s.Name] += c.Seconds
			if id, ok := expected[c.Key]; ok {
				r.Durations[id] += c.Seconds
			}
		}
	}
	for key, count := range seen {
		if _, ok := expected[key]; !ok {
			r.Unexpected = append(r.Unexpected, key.Class+"::"+key.Name)
		}
		if count > 1 {
			r.Duplicates = append(r.Duplicates, key.Class+"::"+key.Name)
		}
		r.Executed += count
	}
	for key, id := range expected {
		if seen[key] == 0 {
			r.Missing = append(r.Missing, id)
		}
	}
	r.SkippedModules = slices.Sorted(maps.Keys(skipped))
	r.BrokenModules = slices.Sorted(maps.Keys(broken))
	for _, list := range [][]string{r.Missing, r.Unexpected, r.Duplicates} {
		sort.Strings(list)
	}
	r.Imbalance = imbalance(r.ShardSeconds)
	r.Problems = problems(r, opt)
	return r
}

func problems(r Report, opt Options) []string {
	var out []string
	add := func(label string, list []string) {
		if len(list) > 0 {
			out = append(out, fmt.Sprintf("%s (%d): %s", label, len(list), preview(list)))
		}
	}
	add("missing: collected but never executed", r.Missing)
	add("unexpected: executed but not in the collected list", r.Unexpected)
	add("duplicate: executed more than once", r.Duplicates)
	add("shards that collected a different list", r.DifferingLists)
	add("shards that ran nothing", r.EmptyShards)
	add("modules that failed to collect", r.BrokenModules)
	if opt.MaxImbalance > 0 && r.Imbalance > opt.MaxImbalance {
		out = append(out, fmt.Sprintf("the slowest shard is %.2f times the mean (limit %.2f): refresh the durations", r.Imbalance, opt.MaxImbalance))
	}
	return out
}

func preview(list []string) string {
	const shown = 5
	if len(list) <= shown {
		return strings.Join(list, "; ")
	}
	return strings.Join(list[:shown], "; ") + fmt.Sprintf("; and %d more", len(list)-shown)
}

func sameSet(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	set := make(map[string]struct{}, len(a))
	for _, id := range a {
		set[id] = struct{}{}
	}
	for _, id := range b {
		if _, ok := set[id]; !ok {
			return false
		}
	}
	return true
}

func imbalance(seconds map[string]float64) float64 {
	if len(seconds) == 0 {
		return 0
	}
	var sum, slowest float64
	for _, s := range seconds {
		sum += s
		if s > slowest {
			slowest = s
		}
	}
	mean := sum / float64(len(seconds))
	if mean == 0 {
		return 0
	}
	return slowest / mean
}
