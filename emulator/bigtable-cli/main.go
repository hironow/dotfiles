package main

import (
	"bufio"
	"context"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	"cloud.google.com/go/bigtable"
	"github.com/olekukonko/tablewriter"
)

type clients struct {
	project  string
	instance string
	admin    *bigtable.AdminClient
	data     *bigtable.Client
}

func getenv(key, def string) string {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	return v
}

func connect(ctx context.Context) (*clients, error) {
	project := getenv("BIGTABLE_PROJECT", "test-project")
	instance := getenv("BIGTABLE_INSTANCE", "test-instance")

	// Emulator is detected via BIGTABLE_EMULATOR_HOST env var (host:port)
	// We intentionally do not enforce it to allow \h/exit flows without emulator.

	admin, err := bigtable.NewAdminClient(ctx, project, instance)
	if err != nil {
		return &clients{project: project, instance: instance}, fmt.Errorf("admin client: %w", err)
	}
	data, err := bigtable.NewClient(ctx, project, instance)
	if err != nil {
		admin.Close()
		return &clients{project: project, instance: instance}, fmt.Errorf("data client: %w", err)
	}
	return &clients{project: project, instance: instance, admin: admin, data: data}, nil
}

func (c *clients) close() {
	if c == nil {
		return
	}
	if c.admin != nil {
		_ = c.admin.Close()
	}
	if c.data != nil {
		_ = c.data.Close()
	}
}

func printHelp() {
	fmt.Println("\n📚 Available Commands:")
	fmt.Println("  help, \\h              - Show this help")
	fmt.Println("  tables, \\lt           - List tables")
	fmt.Println("  init [instance] [cluster] [zone] [nodes] - Ensure instance/cluster exist (defaults: test-instance, test-cluster, us-central1-f, 1)")
	fmt.Println("  create <table> [cf]    - Create table with column family (default: cf1)")
	fmt.Println("  delete <table>         - Delete table")
	fmt.Println("  put <table> <row> <family:col> <value>  - Write a cell")
	fmt.Println("  get <table> <row> [family:col]         - Read a row/cell")
	fmt.Println("  scan <table> [limit]   - Scan first N rows (default 10)")
	fmt.Println("  exit, quit, \\q        - Exit the CLI")
	fmt.Println()
	fmt.Println("Env:")
	fmt.Println("  BIGTABLE_EMULATOR_HOST=host:port (default: localhost:8086 if exported)")
	fmt.Println("  BIGTABLE_PROJECT (default: test-project)")
	fmt.Println("  BIGTABLE_INSTANCE (default: test-instance)")
}

// setHeader sets a header row if the tablewriter version supports it.
// Falls back to appending the header as the first row when unavailable.
func setHeader(t *tablewriter.Table, headers []string) {
	if ts, ok := any(t).(interface{ SetHeader([]string) }); ok {
		ts.SetHeader(headers)
		return
	}
	_ = t.Append(headers)
}

func appendRow(t *tablewriter.Table, row []string) {
	_ = t.Append(row)
}

func renderTable(t *tablewriter.Table) {
	_ = t.Render()
}

func ensureConnected(cli *clients, connected bool) (*clients, bool) {
	if connected {
		return cli, true
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	c, err := connect(ctx)
	cancel()
	if err != nil {
		fmt.Printf("❌ Connect error: %v\n", err)
		fmt.Println("💡 Ensure emulator is running and instance exists, or run 'help'.")
		return cli, false
	}
	return c, true
}

func handleInit(ctx context.Context, cli *clients, parts []string, start time.Time) {
	inst := getenv("BIGTABLE_INSTANCE", "test-instance")
	cl := "test-cluster"
	zone := "us-central1-f"
	nodes := 1
	if len(parts) >= 2 {
		inst = parts[1]
	}
	if len(parts) >= 3 {
		cl = parts[2]
	}
	if len(parts) >= 4 {
		zone = parts[3]
	}
	if len(parts) >= 5 {
		if n, err := strconv.Atoi(parts[4]); err == nil {
			nodes = n
		}
	}

	ia, err := bigtable.NewInstanceAdminClient(ctx, cli.project)
	if err != nil {
		fmt.Printf("❌ Error: %v\n\n", err)
		return
	}
	if _, err := ia.InstanceInfo(ctx, inst); err != nil {
		conf := &bigtable.InstanceConf{
			InstanceId:   inst,
			DisplayName:  inst,
			ClusterId:    cl,
			Zone:         zone,
			NumNodes:     int32(nodes),
			InstanceType: bigtable.DEVELOPMENT,
		}
		if err := ia.CreateInstance(ctx, conf); err != nil {
			fmt.Printf("❌ Error: %v\n\n", err)
			_ = ia.Close()
			return
		}
	}
	_ = ia.Close()
	fmt.Printf("\n✅ Instance %s ready with cluster %s (%v)\n\n", inst, cl, time.Since(start).Round(time.Millisecond))
}

func handleTables(ctx context.Context, cli *clients, start time.Time) {
	names, err := cli.admin.Tables(ctx)
	if err != nil {
		fmt.Printf("❌ Error: %v\n\n", err)
		return
	}
	table := tablewriter.NewWriter(os.Stdout)
	setHeader(table, []string{"Tables"})
	for _, n := range names {
		appendRow(table, []string{n})
	}
	fmt.Println()
	renderTable(table)
	fmt.Printf("\n(%d rows) Time: %v\n\n", len(names), time.Since(start).Round(time.Millisecond))
}

func handleCreate(ctx context.Context, cli *clients, parts []string, start time.Time) {
	if len(parts) < 2 {
		fmt.Println("Usage: create <table> [cf]")
		return
	}
	tbl := parts[1]
	cf := "cf1"
	if len(parts) >= 3 {
		cf = parts[2]
	}
	if err := cli.admin.CreateTable(ctx, tbl); err != nil && !strings.Contains(strings.ToLower(err.Error()), "already exists") {
		fmt.Printf("❌ Error: %v\n\n", err)
		return
	}
	if err := cli.admin.CreateColumnFamily(ctx, tbl, cf); err != nil && !strings.Contains(strings.ToLower(err.Error()), "already exists") {
		fmt.Printf("❌ Error: %v\n\n", err)
		return
	}
	fmt.Printf("\n✅ Table %s (cf=%s) ready (%v)\n\n", tbl, cf, time.Since(start).Round(time.Millisecond))
}

func handleDelete(ctx context.Context, cli *clients, parts []string, start time.Time) {
	if len(parts) < 2 {
		fmt.Println("Usage: delete <table>")
		return
	}
	tbl := parts[1]
	if err := cli.admin.DeleteTable(ctx, tbl); err != nil {
		fmt.Printf("❌ Error: %v\n\n", err)
		return
	}
	fmt.Printf("\n✅ Dropped %s (%v)\n\n", tbl, time.Since(start).Round(time.Millisecond))
}

func handlePut(ctx context.Context, cli *clients, parts []string, start time.Time) {
	if len(parts) < 5 {
		fmt.Println("Usage: put <table> <row> <family:col> <value>")
		return
	}
	tbl, row, famcol, val := parts[1], parts[2], parts[3], strings.Join(parts[4:], " ")
	f := strings.SplitN(famcol, ":", 2)
	if len(f) != 2 {
		fmt.Println("family:col required")
		return
	}
	mut := bigtable.NewMutation()
	mut.Set(f[0], f[1], bigtable.Now(), []byte(val))
	if err := cli.data.Open(tbl).Apply(ctx, row, mut); err != nil {
		fmt.Printf("❌ Error: %v\n\n", err)
		return
	}
	fmt.Printf("\n✅ Wrote row=%s %s:%s (%v)\n\n", row, f[0], f[1], time.Since(start).Round(time.Millisecond))
}

func handleGet(ctx context.Context, cli *clients, parts []string, start time.Time) {
	if len(parts) < 3 {
		fmt.Println("Usage: get <table> <row> [family:col]")
		return
	}
	tbl, row := parts[1], parts[2]
	var fam, col string
	if len(parts) >= 4 {
		fc := strings.SplitN(parts[3], ":", 2)
		if len(fc) == 2 {
			fam, col = fc[0], fc[1]
		}
	}
	rr, err := cli.data.Open(tbl).ReadRow(ctx, row)
	if err != nil {
		fmt.Printf("❌ Error: %v\n\n", err)
		return
	}
	table := tablewriter.NewWriter(os.Stdout)
	setHeader(table, []string{"Family", "Column", "Timestamp(us)", "Value"})
	for famName, items := range rr {
		for _, item := range items {
			if fam != "" && famName != fam {
				continue
			}
			if col != "" && item.Column != fam+":"+col {
				continue
			}
			ts := fmt.Sprintf("%d", item.Timestamp)
			appendRow(table, []string{famName, item.Column, ts, string(item.Value)})
		}
	}
	fmt.Println()
	renderTable(table)
	fmt.Printf("\nTime: %v\n\n", time.Since(start).Round(time.Millisecond))
}

func handleScan(ctx context.Context, cli *clients, parts []string, start time.Time) {
	if len(parts) < 2 {
		fmt.Println("Usage: scan <table> [limit]")
		return
	}
	tbl := parts[1]
	limit := 10
	if len(parts) >= 3 {
		if n, err := strconv.Atoi(parts[2]); err == nil {
			limit = n
		}
	}
	t := cli.data.Open(tbl)
	count := 0
	table := tablewriter.NewWriter(os.Stdout)
	setHeader(table, []string{"RowKey", "Family", "Column", "Value"})
	err := t.ReadRows(ctx, bigtable.InfiniteRange(""), func(rr bigtable.Row) bool {
		var rowKey string
		for fam, items := range rr {
			for _, item := range items {
				if rowKey == "" {
					rowKey = item.Row
				}
				appendRow(table, []string{rowKey, fam, item.Column, string(item.Value)})
			}
		}
		count++
		return count < limit
	})
	if err != nil {
		fmt.Printf("❌ Error: %v\n\n", err)
		return
	}
	fmt.Println()
	renderTable(table)
	fmt.Printf("\n(%d rows) Time: %v\n\n", count, time.Since(start).Round(time.Millisecond))
}

func main() {
	fmt.Println("🚀 Bigtable CLI (Emulator)")
	fmt.Println("======================================")
	fmt.Printf("Project: %s  Instance: %s\n", getenv("BIGTABLE_PROJECT", "test-project"), getenv("BIGTABLE_INSTANCE", "test-instance"))
	if host := os.Getenv("BIGTABLE_EMULATOR_HOST"); host != "" {
		fmt.Printf("Emulator: %s\n", host)
	}
	fmt.Println("\nType 'help' for commands; 'exit' to leave")
	fmt.Println()

	var cli *clients
	var connected bool

	scanner := bufio.NewScanner(os.Stdin)
	for {
		fmt.Print("bigtable> ")
		if !scanner.Scan() {
			break
		}
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		low := strings.ToLower(line)
		switch low {
		case "help", "\\h":
			printHelp()
			continue
		case "exit", "quit", "\\q":
			fmt.Println("Goodbye! 👋")
			if cli != nil {
				cli.close()
			}
			return
		}

		cli, connected = ensureConnected(cli, connected)
		if !connected {
			continue
		}

		parts := strings.Fields(line)
		if len(parts) == 0 {
			continue
		}
		cmd := strings.ToLower(parts[0])
		ctx := context.Background()
		start := time.Now()

		switch cmd {
		case "init", "init-instance":
			handleInit(ctx, cli, parts, start)
		case "tables", "\\lt":
			handleTables(ctx, cli, start)
		case "create":
			handleCreate(ctx, cli, parts, start)
		case "delete":
			handleDelete(ctx, cli, parts, start)
		case "put":
			handlePut(ctx, cli, parts, start)
		case "get":
			handleGet(ctx, cli, parts, start)
		case "scan":
			handleScan(ctx, cli, parts, start)
		default:
			fmt.Printf("Unknown command: %s\n", cmd)
		}
	}
}
