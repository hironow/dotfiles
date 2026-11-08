package logline

import (
	"fmt"
	"strconv"
	"strings"
	"text/tabwriter"
)

// Table renders aligned columns in the given order, oldest first, and ends
// with the number of unreadable lines when skipped is not zero.
func Table(lines []Line, skipped int) string {
	var text strings.Builder
	if len(lines) > 0 {
		columns := tabwriter.NewWriter(&text, 0, 4, 2, ' ', 0)
		fmt.Fprintln(columns, "TIME\tHARNESS\tEVENT\tTOOL\tKIND\tHOOK\tOUTCOME\tRULE\tMS\tPROGRAM\tSUBCOMMAND\tEXTENSION\tPROJECT\tERROR\tMISMATCH")
		for _, line := range lines {
			duration := ""
			if line.Event != "" {
				duration = strconv.FormatFloat(line.DurationMs, 'f', -1, 64)
			}
			row := []string{
				line.Time, line.Harness, line.Event, line.Tool, line.Kind, line.Hook, line.Outcome, line.Rule,
				duration, line.Program, line.Subcommand, line.Extension, line.Project, line.Error, line.Mismatch,
			}
			for i, cell := range row {
				if cell == "" {
					row[i] = "-"
					continue
				}
				for _, b := range []byte(cell) {
					if b < 0x21 || b > 0x7e {
						row[i] = strconv.QuoteToASCII(cell)
						break
					}
				}
			}
			fmt.Fprintln(columns, strings.Join(row, "\t"))
		}
		// The writer's only destination is a strings.Builder, which cannot fail.
		_ = columns.Flush()
	}
	if skipped != 0 {
		fmt.Fprintf(&text, "Skipped %d unreadable lines.\n", skipped)
	}
	return text.String()
}
