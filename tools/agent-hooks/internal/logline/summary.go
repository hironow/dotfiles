package logline

// Summary is what `agent-hook log --summary` prints for doctor: how many
// lines the last days hold, and how many name each error code and mismatch.
type Summary struct {
	Days       int            `json:"days"`
	Lines      int            `json:"lines"`      // the lines read
	Unreadable int            `json:"unreadable"` // the lines skipped as unreadable
	Errors     map[string]int `json:"errors"`
	Mismatches map[string]int `json:"mismatches"`
}

// Summarize counts lines by error code and mismatch. A log file is read as
// untrusted input: Parse refuses unknown members but not unknown values, so a
// value outside the fixed sets counts as "other", and an empty one is not
// counted. The summary never names a key it did not choose.
func Summarize(days int, lines []Line, unreadable int) Summary {
	summary := Summary{
		Days:       days,
		Lines:      len(lines),
		Unreadable: unreadable,
		Errors:     map[string]int{},
		Mismatches: map[string]int{},
	}
	for _, line := range lines {
		if code := optional(line.Error, errorCodes); code != "" {
			summary.Errors[code]++
		}
		if name := optional(line.Mismatch, mismatches); name != "" {
			summary.Mismatches[name]++
		}
	}
	return summary
}
