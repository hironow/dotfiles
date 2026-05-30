package main

import (
	"bufio"
	"context"
	"database/sql"
	"fmt"
	"os"
	"strings"
	"time"

	_ "github.com/lib/pq"
	"github.com/olekukonko/tablewriter"
)

func getConnStr() string {
	host := os.Getenv("PGHOST")
	if host == "" {
		host = "postgres"
	}
	port := os.Getenv("PGPORT")
	if port == "" {
		port = "5432"
	}
	user := os.Getenv("PGUSER")
	if user == "" {
		user = "postgres"
	}
	dbname := os.Getenv("PGDATABASE")
	if dbname == "" {
		dbname = "postgres"
	}
	sslmode := os.Getenv("PGSSLMODE")
	if sslmode == "" {
		sslmode = "disable"
	}
	password := os.Getenv("PGPASSWORD")

	conn := fmt.Sprintf("host=%s port=%s user=%s dbname=%s sslmode=%s", host, port, user, dbname, sslmode)
	if password != "" {
		conn += fmt.Sprintf(" password=%s", password)
	}
	return conn
}

func main() {
	fmt.Println("🚀 PostgreSQL 18 CLI")
	fmt.Println("=====================")

	connStr := getConnStr()
	db, err := sql.Open("postgres", connStr)
	if err != nil {
		fmt.Printf("❌ Failed to connect: %v\n", err)
		os.Exit(1)
	}
	defer db.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		fmt.Printf("❌ Failed to ping database: %v\n", err)
		host := os.Getenv("PGHOST")
		if host == "" {
			host = "localhost"
		}
		port := os.Getenv("PGPORT")
		if port == "" {
			port = "5433"
		}
		fmt.Printf("💡 Ensure PostgreSQL is reachable at %s:%s (host defaults)\n", host, port)
		os.Exit(1)
	}

	fmt.Println("✅ Connected to PostgreSQL 18")
	fmt.Println("\nType 'help' for commands, or enter SQL queries")
	fmt.Println("Type 'exit' or 'quit' to leave")
	fmt.Println()

	scanner := bufio.NewScanner(os.Stdin)
	var multiline []string
	for {
		if len(multiline) == 0 {
			fmt.Print("postgres> ")
		} else {
			fmt.Print("      -> ")
		}
		if !scanner.Scan() {
			break
		}
		line := strings.TrimSpace(scanner.Text())

		if len(multiline) == 0 {
			switch strings.ToLower(line) {
			case "exit", "quit", "\\q":
				fmt.Println("Goodbye! 👋")
				return
			case "help", "\\h":
				printHelp()
				continue
			case "tables", "\\dt":
				showTables(db)
				continue
			case "clear", "\\c":
				fmt.Print("\033[2J\033[H")
				continue
			}
		}

		if line == "" {
			continue
		}
		multiline = append(multiline, line)
		if strings.HasSuffix(line, ";") {
			query := strings.Join(multiline, " ")
			multiline = nil
			executeQuery(db, query)
		}
	}
}

func printHelp() {
	fmt.Println("\nPostgreSQL 18 CLI Commands:")
	fmt.Println("  \\h, help     Show help")
	fmt.Println("  \\q, quit     Exit")
	fmt.Println("  \\dt, tables  List tables")
	fmt.Println("  \\c, clear    Clear screen")
}

func showTables(db *sql.DB) {
	rows, err := db.Query(`
        select table_schema, table_name
        from information_schema.tables
        where table_type='BASE TABLE' and table_schema not in ('pg_catalog','information_schema')
        order by table_schema, table_name`)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		return
	}
	defer rows.Close()

	table := tablewriter.NewWriter(os.Stdout)
	if ts, ok := any(table).(interface{ SetHeader([]string) }); ok {
		ts.SetHeader([]string{"schema", "table"})
	} else {
		table.Append([]string{"schema", "table"})
	}
	for rows.Next() {
		var s, t string
		_ = rows.Scan(&s, &t)
		table.Append([]string{s, t})
	}
	table.Render()
}

func executeQuery(db *sql.DB, query string) {
	q := strings.TrimSpace(query)
	if q == "" {
		return
	}

	// Decide if it's a SELECT-like statement
	upper := strings.ToUpper(q)
	if strings.HasPrefix(upper, "SELECT") || strings.HasPrefix(upper, "WITH") || strings.HasPrefix(upper, "SHOW") {
		rows, err := db.Query(q)
		if err != nil {
			fmt.Printf("❌ %v\n", err)
			return
		}
		defer rows.Close()

		cols, err := rows.Columns()
		if err != nil {
			fmt.Printf("❌ %v\n", err)
			return
		}
		table := tablewriter.NewWriter(os.Stdout)
		if ts, ok := any(table).(interface{ SetHeader([]string) }); ok {
			ts.SetHeader(cols)
		} else {
			table.Append(cols)
		}

		vals := make([]interface{}, len(cols))
		ptrs := make([]interface{}, len(cols))
		for i := range vals {
			ptrs[i] = &vals[i]
		}

		for rows.Next() {
			if err := rows.Scan(ptrs...); err != nil {
				fmt.Printf("❌ %v\n", err)
				return
			}
			out := make([]string, len(cols))
			for i, v := range vals {
				if v == nil {
					out[i] = "NULL"
					continue
				}
				switch b := v.(type) {
				case []byte:
					out[i] = string(b)
				default:
					out[i] = fmt.Sprintf("%v", v)
				}
			}
			table.Append(out)
		}
		table.Render()
		return
	}

	res, err := db.Exec(q)
	if err != nil {
		fmt.Printf("❌ %v\n", err)
		return
	}
	if n, err := res.RowsAffected(); err == nil {
		fmt.Printf("✅ %d rows affected\n", n)
	} else {
		fmt.Println("✅ OK")
	}
}
