package logsink_test

import (
	"path/filepath"
	"runtime"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logsink"
)

func TestBaseUsesOnlyAbsoluteEnvironmentPaths(t *testing.T) {
	cases := []struct {
		name string
		env  map[string]string
		want string
	}{
		{"XDG absolute", map[string]string{"XDG_STATE_HOME": "/state", "HOME": "/home/test"}, "/state"},
		{"XDG relative", map[string]string{"XDG_STATE_HOME": "state", "HOME": "/home/test"}, filepath.FromSlash("/home/test/.local/state")},
		{"HOME fallback", map[string]string{"HOME": "/home/test"}, filepath.FromSlash("/home/test/.local/state")},
		{"nothing", nil, ""},
		{"relative HOME", map[string]string{"HOME": "home/test"}, ""},
		{"relative XDG only", map[string]string{"XDG_STATE_HOME": "state"}, ""},
	}
	if runtime.GOOS == "windows" {
		cases = []struct {
			name string
			env  map[string]string
			want string
		}{
			{"local app data", map[string]string{"LOCALAPPDATA": `C:\Users\test\AppData\Local`}, `C:\Users\test\AppData\Local`},
			{"relative app data", map[string]string{"LOCALAPPDATA": `AppData\Local`, "HOME": `C:\Users\test`}, ""},
			{"drive relative", map[string]string{"LOCALAPPDATA": `C:Local`}, ""},
			{"no app data", map[string]string{"HOME": `C:\Users\test`, "XDG_STATE_HOME": `C:\state`}, ""},
		}
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got, ok := logsink.Base(func(key string) (string, bool) { value, exists := c.env[key]; return value, exists })
			if got != c.want || ok != (c.want != "") {
				t.Fatalf("Base = %q, %v; want %q, %v", got, ok, c.want, c.want != "")
			}
		})
	}
}
