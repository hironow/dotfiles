package rendercorpus

import (
	"fmt"
	"slices"
	"strings"
)

type scenario struct {
	name string
	args []string
	exit int
}

type form struct{ harness, os, shell string }

var forms = []form{
	{"claude", "darwin", ""},
	{"claude", "linux", ""},
	{"claude", "windows", ""},
	{"codex", "darwin", "sh"},
	{"codex", "linux", "sh"},
	{"codex", "windows", "powershell"},
	{"codex", "windows", "cmd"},
	{"codex", "darwin", ""},
	{"codex", "linux", ""},
}

func (f form) name() string {
	shell := f.shell
	if shell == "" {
		shell = "default"
	}
	return f.harness + "/" + f.os + "/" + shell
}

func (f form) args(binary string) []string {
	args := []string{"--harness", f.harness, "--os", f.os, "--binary", binary}
	if f.shell != "" {
		args = append(args, "--shell", f.shell)
	}
	return args
}

func (f form) binary(prefix, layout string) string {
	path := prefix + "/dotfiles/agent-hooks/" + layout + "/agent-hook"
	if f.os == "windows" {
		path = "C:" + path + ".exe"
	}
	return path
}

func scenarios() []scenario {
	var cases []scenario
	for _, f := range forms {
		for _, layout := range []struct{ name, path string }{{"stable", "current/" + f.harness}, {"release", "releases/abcdef0123456789"}} {
			for _, prefix := range []struct{ name, path string }{{"plain", "/state"}, {"quoted", "/a'$ `日本"}} {
				path := f.binary(prefix.path, layout.path)
				name := "render/" + f.name() + "/" + layout.name + "/" + prefix.name
				cases = append(cases, scenario{name, f.args(path), 0})
				if f.os == "windows" {
					cases = append(cases, scenario{name + "/backslashes", f.args(strings.ReplaceAll(path, "/", `\`)), 0})
				}
			}
		}
		cases = append(cases, pathRefusals(f)...)
	}
	return append(cases, argumentRefusals()...)
}

func pathRefusals(f form) []scenario {
	stable := f.binary("/state", "current/"+f.harness)
	bad := []struct{ name, path string }{
		{"relative", strings.TrimPrefix(strings.TrimPrefix(stable, "C:"), "/")},
		{"layout", strings.Replace(stable, "/dotfiles/", "/other/", 1)},
		// sync's rule names every directory above dotfiles/ by a whole
		// segment, so an empty one (two slashes) is no path it owns.
		{"empty-segment", strings.Replace(stable, "/state/", "/state//", 1)},
		{"home-uppercase", strings.Replace(stable, "current/"+f.harness, "current/Upper", 1)},
		{"home-empty", strings.Replace(stable, "current/"+f.harness, "current/", 1)},
		{"home-nested", strings.Replace(stable, "current/"+f.harness, "current/a/b", 1)},
		{"home-underscore", strings.Replace(stable, "current/"+f.harness, "current/a_b", 1)},
		{"filename", stable + "-x"},
		{"release-short", f.binary("/state", "releases/abcdef01234")},
		{"release-uppercase", f.binary("/state", "releases/ABCDEF012345")},
		{"release-nonhex", f.binary("/state", "releases/abcdef01234g")},
	}
	if f.os == "windows" {
		bad = append(bad,
			struct{ name, path string }{"drive-relative", strings.Replace(stable, "C:/", "C:", 1)},
			struct{ name, path string }{"UNC", `\\server` + strings.ReplaceAll(strings.TrimPrefix(stable, "C:"), "/", `\`)},
			struct{ name, path string }{"suffix", strings.TrimSuffix(stable, ".exe")},
		)
	} else {
		bad = append(bad, struct{ name, path string }{"suffix", stable + ".exe"})
	}
	for char := rune(0); char <= 0x7f; char++ {
		if char <= 0x1f || char == 0x7f {
			bad = append(bad, struct{ name, path string }{fmt.Sprintf("control-%02x", char), strings.Replace(stable, "state", "state"+string(char), 1)})
		}
	}
	var forbidden string
	switch {
	case f.harness == "claude":
		forbidden = "${"
	case f.shell == "powershell":
		forbidden = "*?[]‘’‚‛"
	case f.shell == "cmd":
		forbidden = "%!\""
	}
	if f.harness == "claude" {
		bad = append(bad, struct{ name, path string }{"placeholder", strings.Replace(stable, "state", "${state}", 1)})
	} else {
		for _, char := range forbidden {
			bad = append(bad, struct{ name, path string }{fmt.Sprintf("form-%04x", char), strings.Replace(stable, "state", "state"+string(char), 1)})
		}
	}
	cases := make([]scenario, 0, len(bad))
	for _, b := range bad {
		cases = append(cases, scenario{"refuse/" + f.name() + "/" + b.name, f.args(b.path), 2})
	}
	return cases
}

func argumentRefusals() []scenario {
	f := form{"claude", "linux", ""}
	base := f.args(f.binary("/state", "current/claude"))
	cases := []scenario{{"usage/no-flags", []string{}, 64}}
	for _, harness := range []string{"claude", "codex"} {
		args := slices.Clone(base)
		args[1] = harness
		cases = append(cases, scenario{"refuse/" + harness + "/empty-shell", append(args, "--shell="), 2})
	}
	for i, flag := range []string{"harness", "os", "binary"} {
		args := slices.Concat(base[:i*2], base[i*2+2:])
		cases = append(cases, scenario{"usage/missing-" + flag, args, 64})
		args = slices.Clone(base)
		args[i*2+1] = ""
		cases = append(cases, scenario{"usage/empty-" + flag, args, 64})
	}
	for _, flag := range []string{"harness", "os", "binary", "shell"} {
		cases = append(cases, scenario{"usage/no-value-" + flag, []string{"--" + flag}, 64})
	}
	for _, harness := range []string{"agy", "pi", "unknown", "render"} {
		args := slices.Clone(base)
		args[1] = harness
		cases = append(cases, scenario{"usage/harness-" + harness, args, 64})
	}
	cases = append(cases,
		scenario{"usage/unknown-flag", append(slices.Clone(base), "--unknown"), 64},
		scenario{"usage/positional", append(slices.Clone(base), "extra"), 64},
		scenario{"usage/help", []string{"--help"}, 64},
		scenario{"usage/os", append(slices.Clone(base), "--os", "freebsd"), 64},
	)
	for _, f := range forms {
		for _, shell := range []string{"exec", "sh", "powershell", "cmd", "fish"} {
			if f.shell == "" && f.harness == "codex" {
				continue
			}
			if f.harness == "codex" && ((f.os == "windows" && (shell == "powershell" || shell == "cmd")) || (f.os != "windows" && shell == "sh")) {
				continue
			}
			args := f.args(f.binary("/state", "current/"+f.harness))
			cases = append(cases, scenario{"refuse/" + f.name() + "/shell-" + shell, append(args, "--shell", shell), 2})
		}
	}
	win := form{"codex", "windows", ""}
	cases = append(cases, scenario{"refuse/codex/windows/missing-shell", win.args(win.binary("/state", "current/codex")), 2})
	return cases
}
