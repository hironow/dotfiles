package rules

import (
	"strings"
	"testing"
)

func incidentPolicy() map[string]any {
	floor := func(branch, minimum string) any { return map[string]any{"branch": branch, "minimum": minimum} }
	return map[string]any{
		"floors": map[string]any{
			"go":     []any{floor("1.27", "1.27.3"), floor("1.26", "1.26.10")},
			"node":   []any{floor("22", "22.23.4"), floor("24", "24.22.1"), floor("26", "26.12.1")},
			"uv":     []any{floor("0.13", "0.13.5")},
			"rustup": []any{floor("1", "1.29.2")},
			"bun":    []any{floor("1.4", "1.4.4")},
			"mise":   []any{floor("2026", "2026.10.17")},
		},
		"pending": []any{},
	}
}

const featureScript = "#!/bin/sh\nRUSTUP_VERSION=\"1.29.2\"\nRUST_TOOLCHAIN=\"1.99.1\"\n"

func caInputs() Inputs {
	return Inputs{hostConfig: host(), imageConfig: image(), featureInstall: featureScript, caIncident: incidentPolicy()}
}

func caMessages(t *testing.T, in Inputs) string {
	t.Helper()
	var b strings.Builder
	for _, f := range findingsOf(t, caIncidentFloors(), in) {
		if f.Rule != "ca-incident-floors" {
			t.Errorf("finding names rule %q", f.Rule)
		}
		b.WriteString(f.Message + "\n")
	}
	return b.String()
}

func TestCAFloorsAcceptPinsAtOrAboveTheReviewedFloors(t *testing.T) {
	if got := caMessages(t, caInputs()); got != "" {
		t.Fatalf("rejects the accepted pins:\n%s", got)
	}
}

func TestCAFloorsRejectStaleOrUnreviewedPins(t *testing.T) {
	cases := []struct {
		name   string
		change func(Inputs)
		expect string
	}{
		{"image go below its floor", func(in Inputs) { set(in[imageConfig], "1.27.2", "tools", "go") }, "below incident floor: go 1.27.2 < 1.27.3"},
		{"image node on an unreviewed branch", func(in Inputs) { set(in[imageConfig], "23.1.0", "tools", "node") }, "unreviewed branch: node 23.1.0"},
		{"image uv not a stable pin", func(in Inputs) { set(in[imageConfig], "0.13.9-rc.1", "tools", "uv") }, "non-stable fixed pin: uv 0.13.9-rc.1"},
		{"image bun moving", func(in Inputs) { set(in[imageConfig], "latest", "tools", "bun") }, "non-stable fixed pin: bun latest"},
		{"image bun missing", func(in Inputs) { set(in[imageConfig], nil, "tools", "bun") }, "missing required declaration or incident floor: bun"},
		{"mise below its floor", func(in Inputs) { set(in[imageConfig], "2026.10.16", "bootstrap", "mise") }, "below incident floor: mise"},
		{"rustup below its floor", func(in Inputs) { in[featureInstall] = strings.Replace(featureScript, "1.29.2", "1.29.1", 1) }, "below incident floor: rustup"},
		{"rustup undeclared", func(in Inputs) { in[featureInstall] = "RUST_TOOLCHAIN=\"1.99.1\"\n" }, "RUSTUP_VERSION"},
		{"floor removed", func(in Inputs) { set(in[caIncident], nil, "floors", "uv") }, "missing required declaration or incident floor: uv"},
		{"bun pending", func(in Inputs) { set(in[caIncident], []any{"bun"}, "pending") }, "patched Bun must not remain pending"},
		{"host fixed pin below the floor", func(in Inputs) { set(in[hostConfig], "1.26.9", "tools", "go") }, "below incident floor: go 1.26.9 < 1.26.10"},
		{"host fixed pin in a table", func(in Inputs) { set(in[hostConfig], map[string]any{"version": "0.13.4"}, "tools", "uv") }, "below incident floor: uv 0.13.4"},
		{"rust toolchain drifts from the host", func(in Inputs) { in[featureInstall] = strings.Replace(featureScript, "1.99.1", "1.98.0", 1) }, "RUST_TOOLCHAIN"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			in := caInputs()
			c.change(in)
			got := caMessages(t, in)
			if !strings.Contains(got, c.expect) {
				t.Fatalf("findings %q do not mention %q", got, c.expect)
			}
		})
	}
}

// The checker itself, on pins derived from the policy (never from the
// deployed pins), for every required tool: the floor passes, one patch below
// it fails, and moving, pre-release or unregistered pins fail.
func TestFixedPinsCheckerPerTool(t *testing.T) {
	floors, _ := table(incidentPolicy(), "floors")
	pins := map[string]string{}
	for _, tool := range caRequired {
		first, _ := at(floors, tool)
		minimum, _ := str(first.([]any)[0], "minimum")
		pins[tool] = minimum
	}
	if errs := checkFixedPins(pins, floors); len(errs) != 0 {
		t.Fatalf("the floors themselves fail: %v", errs)
	}
	for _, tool := range caRequired {
		t.Run(tool, func(t *testing.T) {
			with := func(v string) map[string]string {
				out := map[string]string{}
				for k, x := range pins {
					out[k] = x
				}
				out[tool] = v
				return out
			}
			parts := strings.Split(pins[tool], ".")
			if parts[2] == "0" {
				t.Fatalf("choose a stale same-branch case: the floor of %s is x.y.0", tool)
			}
			stale := parts[0] + "." + parts[1] + "." + decrement(parts[2])
			assertErr(t, checkFixedPins(with(stale), floors), "below incident floor")
			for _, bad := range []string{"0.0.0", pins[tool] + "-rc.1", "latest", "lts"} {
				if len(checkFixedPins(with(bad), floors)) == 0 {
					t.Errorf("accepts %s %s", tool, bad)
				}
			}
			missing := map[string]string{}
			for k, x := range pins {
				if k != tool {
					missing[k] = x
				}
			}
			assertErr(t, checkFixedPins(missing, floors), "missing required")
			noFloor := map[string]any{}
			for k, x := range floors {
				if k != tool {
					noFloor[k] = x
				}
			}
			assertErr(t, checkFixedPins(pins, noFloor), "missing required")
		})
	}
}

func decrement(s string) string {
	n := 0
	for _, c := range s {
		n = n*10 + int(c-'0')
	}
	n--
	if n < 0 {
		return "0"
	}
	out := ""
	for {
		out = string(rune('0'+n%10)) + out
		n /= 10
		if n == 0 {
			return out
		}
	}
}

func assertErr(t *testing.T, errs []string, want string) {
	t.Helper()
	for _, e := range errs {
		if strings.Contains(e, want) {
			return
		}
	}
	t.Errorf("errors %v do not mention %q", errs, want)
}
