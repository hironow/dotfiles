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

func TestDecodeReportsBrokenJSON(t *testing.T) {
	if _, err := Decode("{ \"a\": }"); err == nil {
		t.Fatal("broken JSON decoded")
	}
}
