package rules

import (
	"fmt"
	"maps"
	"regexp"
	"slices"
	"strconv"
	"strings"
)

const (
	featureInstall = ".devcontainer/features/dotfiles-tools/install.sh"
	caIncident     = "tools/ca-doctor/incidents/emudhra-2026.json"
)

// caRequired are the tools whose pins the CA incident reviewed.
var caRequired = []string{"bun", "go", "mise", "node", "rustup", "uv"}

var (
	rustupVersion = regexp.MustCompile(`(?m)^RUSTUP_VERSION="([^"]+)"$`)
	rustToolchain = regexp.MustCompile(`(?m)^RUST_TOOLCHAIN="([^"]+)"$`)
)

// checkFixedPins checks each pin against the incident's floors: every
// required tool has a floor and a pin, and each pin is a stable x.y.z on
// exactly one reviewed branch, at or above that branch's minimum.
func checkFixedPins(pins map[string]string, floors map[string]any) []string {
	var errs []string
	for _, tool := range caRequired {
		list, _ := at(floors, tool)
		items, _ := list.([]any)
		if _, pinned := pins[tool]; len(items) == 0 || !pinned {
			errs = append(errs, "missing required declaration or incident floor: "+tool)
		}
	}
	for _, tool := range slices.Sorted(maps.Keys(pins)) {
		ver := pins[tool]
		if !exactVersion.MatchString(ver) {
			errs = append(errs, fmt.Sprintf("non-stable fixed pin: %s %s", tool, ver))
			continue
		}
		list, _ := at(floors, tool)
		items, _ := list.([]any)
		var minimums []string
		for _, item := range items {
			branch, _ := str(item, "branch")
			if strings.HasPrefix(ver, branch+".") {
				minimum, _ := str(item, "minimum")
				minimums = append(minimums, minimum)
			}
		}
		if len(minimums) != 1 {
			errs = append(errs, fmt.Sprintf("unreviewed branch: %s %s", tool, ver))
			continue
		}
		if less(ver, minimums[0]) {
			errs = append(errs, fmt.Sprintf("below incident floor: %s %s < %s", tool, ver, minimums[0]))
		}
	}
	return errs
}

// less compares two dotted versions number by number.
func less(a, b string) bool {
	x, y := strings.Split(a, "."), strings.Split(b, ".")
	for i := range max(len(x), len(y)) {
		var p, q int
		if i < len(x) {
			p, _ = strconv.Atoi(x[i])
		}
		if i < len(y) {
			q, _ = strconv.Atoi(y[i])
		}
		if p != q {
			return p < q
		}
	}
	return false
}

// caIncidentFloors: after the eMudhra CA incident, every frozen pin of the
// image and every exact pin of the host is at or above the version the
// incident reviewed (tools/ca-doctor/incidents/emudhra-2026.json).
func caIncidentFloors() Rule {
	const id = "ca-incident-floors"
	return Rule{
		ID:     id,
		Why:    "frozen and exact pins stay at or above the CA incident's reviewed floors",
		Inputs: []Input{{imageConfig, TOML}, {hostConfig, TOML}, {featureInstall, Text}, {caIncident, JSON}},
		Check: func(in Inputs) []Finding {
			var out []Finding
			add := func(path, format string, args ...any) {
				out = append(out, Finding{Path: path, Rule: id, Message: fmt.Sprintf(format, args...)})
			}
			floors, _ := table(in[caIncident], "floors")
			if pending := strs(in[caIncident], "pending"); slices.Contains(pending, "bun") {
				add(caIncident, "patched Bun must not remain pending")
			}
			pins := map[string]string{}
			for _, tool := range []string{"bun", "go", "node", "uv"} {
				if v, ok := str(in[imageConfig], "tools", tool); ok {
					pins[tool] = v
				} else if v, ok := at(in[imageConfig], "tools", tool); ok {
					pins[tool] = fmt.Sprint(v)
				}
			}
			if v, ok := str(in[imageConfig], "bootstrap", "mise"); ok {
				pins["mise"] = v
			}
			script, _ := in[featureInstall].(string)
			if m := rustupVersion.FindStringSubmatch(script); m != nil {
				pins["rustup"] = m[1]
			} else {
				add(featureInstall, "the feature must declare its pinned rustup as RUSTUP_VERSION")
			}
			for _, e := range checkFixedPins(pins, floors) {
				add(imageConfig, "%s", e)
			}
			// The host's exact pins too; latest and lts move, and doctor checks
			// what is installed.
			hostTools, _ := table(in[hostConfig], "tools")
			for _, tool := range caRequired {
				spec, ok := hostTools[tool]
				if !ok {
					continue
				}
				ver := version(spec)
				if ver == "latest" || ver == "lts" {
					continue
				}
				with := maps.Clone(pins)
				with[tool] = ver
				for _, e := range checkFixedPins(with, floors) {
					if strings.Contains(e, " "+tool+" ") || strings.HasSuffix(e, ": "+tool) {
						add(hostConfig, "%s", e)
					}
				}
			}
			rust := version(hostTools["rust"])
			if m := rustToolchain.FindStringSubmatch(script); m == nil || m[1] != rust {
				got := ""
				if m != nil {
					got = m[1]
				}
				add(featureInstall, "RUST_TOOLCHAIN %q must equal the host's rust %q", got, rust)
			}
			return out
		},
	}
}
