package toolhookcorpus_test

import (
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/toolhookcorpus"
)

func TestSameJSONComparesValuesAsPythonReadsThem(t *testing.T) {
	cases := []struct {
		a, b string
		same bool
	}{
		{`{"a":1,"b":"x"}`, `{"b": "x", "a": 1}`, true},
		{`"é"`, `"é"`, true},
		{`[1,2]`, `[2,1]`, false},
		{`{"a":1}`, `{"a":1,"b":2}`, false},
		// Python keeps an integer whole: neighbors that round to one double differ.
		{`9007199254740993`, `9007199254740992`, false},
		{`12345678901234567890`, `12345678901234567890`, true},
		// Python reads any other number as a double.
		{`1.5e2`, `150.0`, true},
		{`1.50`, `1.5`, true},
		{`0.1000000000000000055511151231257827`, `0.1`, true},
		{`1.5`, `1.4999999999999998`, false},
		{`true`, `false`, false},
		{`null`, `null`, true},
		{`"1"`, `1`, false},
		{`{"a":1,"a":2}`, `{"a":2}`, true},
	}
	for _, c := range cases {
		same, err := toolhookcorpus.SameJSON([]byte(c.a), []byte(c.b))
		if err != nil || same != c.same {
			t.Errorf("SameJSON(%s, %s) = %v, %v; want %v", c.a, c.b, same, err, c.same)
		}
	}
	if _, err := toolhookcorpus.SameJSON([]byte(`{} {}`), []byte(`{}`)); err == nil {
		t.Error("SameJSON read two values as one")
	}
}

func TestSameJSONComparesAnIntegerAndADoubleExactly(t *testing.T) {
	// Python: 9007199254740993 == 9007199254740993.0 is False, since the
	// float rounds to 9007199254740992.0; 2 == 2.0 is True.
	cases := []struct {
		a, b string
		same bool
	}{
		{`9007199254740993`, `9007199254740993.0`, false},
		{`9007199254740992`, `9007199254740993.0`, true},
		{`2`, `2.0`, true},
		{`2`, `2.5`, false},
		{`1e400`, `1e400`, true},
		{`1`, `1e400`, false},
	}
	for _, c := range cases {
		for _, pair := range [][2]string{{c.a, c.b}, {c.b, c.a}} {
			same, err := toolhookcorpus.SameJSON([]byte(pair[0]), []byte(pair[1]))
			if err != nil || same != c.same {
				t.Errorf("SameJSON(%s, %s) = %v, %v; want %v", pair[0], pair[1], same, err, c.same)
			}
		}
	}
}
