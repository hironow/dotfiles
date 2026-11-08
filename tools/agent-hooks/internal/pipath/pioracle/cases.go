package pioracle

import "strings"

// Cases covers Pi's POSIX path rules with made-up directories only.
func Cases() []Case {
	paths := []string{
		"", ".", "..", "./x", "../x", "x", "x/", "x/../y", "/x", "/x/", "/", "//", "//x///y/",
		"@", "@@", "@@x", "@x", "@/x", "@~", "@~/x", "@file:///x", "@@file:///x",
		"~", "~/", "~/x", "~//x", "~/../x", "~user", "~user/x", "~\\x",
		" x ", "x\ny\n", "x\ty", "x\x00y", "docker-compose.yaml", "@docker-compose.yaml", "docs/agents/x.yml",
		"file:///", "file:///x", "file://localhost/x", "file://other/x", "file://LOCALHOST/x",
		"file:///a%20b", "file:///%2F", "file:///%2f", "file:///%7E", "file:///%",
		"file:///%G0", "file:///%FF", "file:///%00", "file:///a/%2e%2e/x", "file:///a/../x",
		"file:///x?q", "file:///x#f", "file:///a\\b", "FILE:///x", "file:/x", "file:", "file://",
		"file://localhost", "file:////x", "file:///a b", "file:///日", "file:///%E6%97%A5",
		"file:///%5C", "file:///%3F%23", "file:///a/%252e%252e/x", "file:///AZaz09._~-",
		"file:///%C0%AF", "file:///%ED%A0%80", "file:///%F4%90%80%80", "file:///%E2%82",
		"file:///x:y", "file://localhost:80/x", "file://user@localhost/x", "file:///a/.%2e/x",
		"file:///a/%2e./x", "file:///a/%2E%2E/x", "file:///a/%2f/../x", "file:///a/%FF/../x",
	}
	// Empty segments before a dot segment, as a URL and as a path: the URL
	// parser keeps an empty segment, and path.resolve drops it.
	paths = append(paths,
		"file:///w/docker-compose.yaml//..", "file:///w/docs/extra//../agents/docker-compose.yaml",
		"@file:///w/compose.yml//%2e%2e", "file:///a//../x", "file:///a/b//../../x", "file:///a/.//../x",
		"file:///a//%2e%2e/x", "docker-compose.yaml//..", "docs/extra//../agents/docker-compose.yaml",
		"docs/agents/../docker-compose.yaml",
	)
	paths = append(paths, segmentGrid()...)
	var cases []Case
	for _, path := range paths {
		cases = append(cases, Case{Path: path, Cwd: "/w", Home: "/home/user"})
	}
	for _, space := range "\u00a0\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000\u2028\ufeff\u200b\u1680\u1fff\u200c\u202e\u2060\u3001" {
		cases = append(cases,
			Case{Path: "a" + string(space) + "b" + string(space), Cwd: "/w", Home: "/home/user"},
			Case{Path: "file:///a" + string(space) + "b", Cwd: "/w", Home: "/home/user"},
		)
	}
	for _, home := range []string{"", "/home/user/", "homes/user", "/home/user/../other", "file:///home/user", "/home/a\u00a0b"} {
		for _, path := range []string{"~", "~/", "~/x", "~//x", "~/../x", "~/../../x", "~user"} {
			cases = append(cases, Case{Path: path, Cwd: "/w", Home: home})
		}
	}
	for _, cwd := range []string{"/w/../project", "//w///project", "/w/", "/", "/w/a\u00a0b", "/w/@x"} {
		for _, path := range []string{"", ".", "..", "//", "x/", "/absolute/", "~/x", "file:///a/../x"} {
			cases = append(cases, Case{Path: path, Cwd: cwd, Home: "/home/user"})
		}
	}
	return cases
}

// gridSegments are the path segments segmentGrid combines: a name, an empty
// segment, and the dot segments, plain and percent-encoded.
var gridSegments = []string{"a", "", ".", "..", "%2e", "%2e%2e", ".%2e"}

// segmentGrid is every path of one to three gridSegments, relative, absolute,
// and as a file: URL, so that every order of names, empty segments, and dot
// segments is checked against Pi.
func segmentGrid() []string {
	var joined []string
	var grow func(prefix []string)
	grow = func(prefix []string) {
		if len(prefix) > 0 {
			joined = append(joined, strings.Join(prefix, "/"))
		}
		if len(prefix) == 3 {
			return
		}
		for _, segment := range gridSegments {
			grow(append(append([]string(nil), prefix...), segment))
		}
	}
	grow(nil)
	var paths []string
	for _, path := range joined {
		paths = append(paths, path, "/"+path, "file:///"+path)
	}
	return paths
}
