package jsonc

import (
	"reflect"
	"testing"
)

func TestDecodeDropsCommentsAndTrailingCommasOutsideStrings(t *testing.T) {
	literal := `quoted \" /* literal */ // literal , }`
	for _, endpoint := range []string{"unix:///run/podman.sock", "https://example.invalid//x", "tcp://h:1,]"} {
		text := "// leading comment\n{\n" +
			`  /* block comment */ "containerEnv": {` + "\n" +
			`    "CONTAINER_HOST": "` + endpoint + `", // inline comment` + "\n" +
			`    "LITERAL": "` + literal + `",` + "\n" +
			"  },\n  \"list\": [1, 2,],\n}\n"
		got, err := Decode(text)
		if err != nil {
			t.Fatalf("%s: %v", endpoint, err)
		}
		want := map[string]any{
			"containerEnv": map[string]any{"CONTAINER_HOST": endpoint, "LITERAL": `quoted " /* literal */ // literal , }`},
			"list":         []any{float64(1), float64(2)},
		}
		if !reflect.DeepEqual(got, want) {
			t.Errorf("%s: got %#v", endpoint, got)
		}
	}
}

func TestDecodeEndsALineCommentAtAnyLineBreak(t *testing.T) {
	for _, text := range []string{"{\r// comment\r\"a\":1\r}", "{\r\n// comment\r\n\"a\":1\r\n}"} {
		got, err := Decode(text)
		if err != nil || !reflect.DeepEqual(got, map[string]any{"a": float64(1)}) {
			t.Errorf("%q = %#v, %v", text, got, err)
		}
	}
}

func TestDecodeReportsBrokenJSON(t *testing.T) {
	if _, err := Decode("{ \"a\": }"); err == nil {
		t.Fatal("broken JSON decoded")
	}
}

func TestDecodeDropsHashLineComments(t *testing.T) {
	got, err := Decode("# leading\n{\n  \"a\": \"# kept\", # trailing\n}\n")
	if err != nil || !reflect.DeepEqual(got, map[string]any{"a": "# kept"}) {
		t.Fatalf("got %#v, %v", got, err)
	}
}
