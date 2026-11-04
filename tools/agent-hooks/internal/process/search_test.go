package process

import "testing"

func TestSearchPathWalksPATHAsShutilWhichDoes(t *testing.T) {
	// executable is the set of paths that are executable non-directories.
	executable := map[string]bool{
		"/a/rtk":                        true,
		"/b/rtk":                        true,
		"/inside/link/../bin/rtk":       true, // the kernel resolves link/.. through the link
		"rtk":                           true, // a relative entry "" joins to the bare name
		"./rtk":                         true,
		"rel/dir/rtk":                   true,
		"/trailing/rtk":                 true,
		"/dup/rtk":                      true,
		"/x/./bin/rtk":                  true,
		"/not-exec/rtk":                 false,
		"/c/rtk-is-a-directory-not-hit": false,
	}
	isExecutable := func(path string) bool { return executable[path] }
	cases := []struct {
		name, pathEnv string
		want          Program
		found         bool
	}{
		{"the first hit wins", "/a:/b", Program{Path: "/a/rtk"}, true},
		{"a non-executable entry is skipped", "/not-exec:/b", Program{Path: "/b/rtk"}, true},
		{"joined without cleaning", "/inside/link/../bin:/a", Program{Path: "/inside/link/../bin/rtk"}, true},
		{"a dot segment is kept", "/x/./bin", Program{Path: "/x/./bin/rtk"}, true},
		{"a trailing slash is not doubled", "/trailing/", Program{Path: "/trailing/rtk"}, true},
		{"an empty entry is the current directory", ":/a", Program{Path: "rtk", Relative: true}, true},
		{"a dot entry is relative", ".:/a", Program{Path: "./rtk", Relative: true}, true},
		{"a relative entry is relative", "rel/dir:/a", Program{Path: "rel/dir/rtk", Relative: true}, true},
		{"a relative entry without the program is passed over", "nowhere:/a", Program{Path: "/a/rtk"}, true},
		{"nothing found", "/none:/also-none", Program{}, false},
		{"an empty PATH finds nothing", "", Program{}, false},
	}
	for _, c := range cases {
		got, found := Search(c.pathEnv, "rtk", isExecutable)
		if got != c.want || found != c.found {
			t.Errorf("%s: Search(%q) = %+v, %v; want %+v, %v", c.name, c.pathEnv, got, found, c.want, c.found)
		}
	}
}
