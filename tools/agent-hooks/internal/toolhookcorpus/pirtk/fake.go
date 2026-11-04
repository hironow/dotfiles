package pirtk

import (
	"encoding/base64"
	"fmt"
	"strings"
)

func fakeScript(scenario Scenario) (string, error) {
	rewrite := scenario.Fake.Rewrite
	stdout, err := base64.StdEncoding.DecodeString(rewrite.StdoutB64)
	if err != nil {
		return "", fmt.Errorf("fake stdout: %w", err)
	}
	late, err := base64.StdEncoding.DecodeString(rewrite.LateB64)
	if err != nil {
		return "", fmt.Errorf("fake late stdout: %w", err)
	}
	if rewrite.PauseAt < 0 || rewrite.PauseAt > len(stdout) || rewrite.SleepMs < 0 || rewrite.LateMs < 0 ||
		(len(late) > 0) != (rewrite.LateMs > 0) {
		return "", fmt.Errorf("invalid fake timing: %+v", rewrite)
	}
	var script strings.Builder
	script.WriteString("#!/bin/sh\n{ printf '%s\\000' \"$@\"; printf '\\036'; } >> \"$RTK_LOG\"\n")
	script.WriteString("if [ \"$1\" = \"--version\" ]; then\n")
	script.WriteString(printBytes([]byte(scenario.Fake.Version.Stdout)))
	fmt.Fprintf(&script, "exit %d\nfi\n", scenario.Fake.Version.Exit)
	if rewrite.PauseAt > 0 {
		script.WriteString(printBytes(stdout[:rewrite.PauseAt]))
		script.WriteString("sleep 0.100\n")
		script.WriteString(printBytes(stdout[rewrite.PauseAt:]))
	} else if command, ok := scenario.Command.(string); ok && string(stdout) == "rtk "+command+"\n" {
		script.WriteString("printf 'rtk %s\\n' \"$2\"\n")
	} else {
		script.WriteString(printBytes(stdout))
	}
	if len(late) > 0 {
		fmt.Fprintf(&script, "( sleep %d.%03d\n", rewrite.LateMs/1000, rewrite.LateMs%1000)
		script.WriteString(printBytes(late))
		script.WriteString(") &\n")
	}
	script.WriteString(strings.TrimSuffix(printBytes([]byte(rewrite.Stderr)), "\n") + " >&2\n")
	if rewrite.SleepMs > 0 {
		fmt.Fprintf(&script, "exec sleep %d.%03d\n", rewrite.SleepMs/1000, rewrite.SleepMs%1000)
	}
	if rewrite.Signal {
		script.WriteString("kill -TERM \"$$\"\n")
	}
	fmt.Fprintf(&script, "exit %d\n", rewrite.Exit)
	return script.String(), nil
}

// Shell printf decodes octal bytes without depending on locale or a decoder.
func printBytes(value []byte) string {
	var out strings.Builder
	out.WriteString("printf '%b' '")
	for _, octet := range value {
		fmt.Fprintf(&out, "\\0%03o", octet)
	}
	out.WriteString("'\n")
	return out.String()
}
