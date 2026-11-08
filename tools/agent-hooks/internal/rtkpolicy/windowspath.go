package rtkpolicy

import "strings"

// AsPosixWindows is Python's PureWindowsPath(path).as_posix(), what the
// Claude script's Path(...).as_posix() gives on Windows. It keeps the drive
// (a letter and a colon, a UNC share like \\server\share, or a device path
// like \\?\C:) and a root after it; runs of either separator become one
// forward slash; "." segments go and ".." stays; no trailing separator is
// left, except that a UNC share always has its root. An empty result is ".".
func AsPosixWindows(path string) string {
	drive, root, rest := splitRootWindows(path)
	if root == "" && strings.HasPrefix(drive, `\\`) && !strings.HasSuffix(drive, `\`) {
		parts := strings.Split(drive, `\`)
		if (len(parts) == 4 && parts[2] != "?" && parts[2] != ".") || len(parts) == 6 {
			root = `\`
		}
	}
	var parts []string
	for part := range strings.SplitSeq(rest, `\`) {
		if part != "" && part != "." {
			parts = append(parts, part)
		}
	}
	text := drive + root + strings.Join(parts, `\`)
	if text == "" {
		return "."
	}
	return strings.ReplaceAll(text, `\`, "/")
}

// splitRootWindows is Python's ntpath.splitroot, reading forward slashes as
// backslashes: the drive, the root, and the rest.
func splitRootWindows(path string) (drive, root, rest string) {
	p := strings.ReplaceAll(path, "/", `\`)
	switch {
	case strings.HasPrefix(p, `\\`):
		start := 2
		if len(p) >= 8 && strings.EqualFold(p[:8], `\\?\UNC\`) {
			start = 8
		}
		index := strings.IndexByte(p[start:], '\\')
		if index < 0 {
			return p, "", ""
		}
		index += start
		index2 := strings.IndexByte(p[index+1:], '\\')
		if index2 < 0 {
			return p, "", ""
		}
		index2 += index + 1
		return p[:index2], p[index2 : index2+1], p[index2+1:]
	case strings.HasPrefix(p, `\`):
		return "", p[:1], p[1:]
	case len(p) >= 2 && p[1] == ':':
		if len(p) >= 3 && p[2] == '\\' {
			return p[:2], p[2:3], p[3:]
		}
		return p[:2], "", p[2:]
	default:
		return "", "", p
	}
}
