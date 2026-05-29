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
		host = "localhost"
	}
	port := os.Getenv("PGPORT")
	if port == "" {
		port = "5432"
	}
	user := os.Getenv("PGUSER")
	if user == "" {
		user = "user"
	}
	dbname := os.Getenv("PGDATABASE")
	if dbname == "" {
		dbname = "test-instance"
	}
	sslmode := os.Getenv("PGSSLMODE")
	if sslmode == "" {
		sslmode = "disable"
	}

	return fmt.Sprintf("host=%s port=%s user=%s dbname=%s sslmode=%s",
		host, port, user, dbname, sslmode)
}

func main() {
	fmt.Println("🚀 pgAdapter CLI for Spanner Emulator")
	fmt.Println("======================================")

	// Connect to database
	connStr := getConnStr()
	db, err := sql.Open("postgres", connStr)
	if err != nil {
		fmt.Printf("❌ Failed to connect: %v\n", err)
		os.Exit(1)
	}
	defer db.Close()

	// Test connection
	ctx := context.Background()
	if err := db.PingContext(ctx); err != nil {
		fmt.Printf("❌ Failed to ping database: %v\n", err)
		// Show current target and a host-side hint
		host := os.Getenv("PGHOST")
		if host == "" {
			host = "localhost"
		}
		port := os.Getenv("PGPORT")
		if port == "" {
			port = "5432"
		}
		alt := os.Getenv("PGADAPTER_PORT")
		if alt == "" {
			alt = "55432"
		}
		fmt.Printf("💡 Target: %s:%s\n", host, port)
		fmt.Printf("💡 Host access hint: localhost:%s (override with PGADAPTER_PORT)\n", alt)
		os.Exit(1)
	}

	fmt.Println("✅ Connected to Spanner Emulator via pgAdapter")
	fmt.Println("\nType 'help' for commands, or enter SQL queries")
	fmt.Println("Type 'exit' or 'quit' to leave")
	fmt.Println()

	// Interactive loop
	scanner := bufio.NewScanner(os.Stdin)
	var multiline []string

	for {
		if len(multiline) == 0 {
			fmt.Print("pgadapter> ")
		} else {
			fmt.Print("      -> ")
		}

		if !scanner.Scan() {
			break
		}

		line := strings.TrimSpace(scanner.Text())

		// Handle special commands
		if len(multiline) == 0 {
			switch strings.ToLower(line) {
			case "exit", "quit", "\\q":
				fmt.Println("Goodbye! 👋")
				return
			case "help", "\\h":
				printHelp()
				continue
			case "tables", "\\dt":
				showTables(ctx, db)
				continue
			case "clear", "\\c":
				fmt.Print("\033[2J\033[H")
				continue
			}
		}

		// Handle multiline SQL
		if line == "" {
			continue
		}

		multiline = append(multiline, line)

		// Check if query is complete (ends with semicolon)
		if strings.HasSuffix(line, ";") {
			query := strings.Join(multiline, " ")
			multiline = nil

			executeQuery(ctx, db, query)
		}
	}
}

func printHelp() {
	fmt.Println("\n📚 Available Commands:")
	fmt.Println("  help, \\h     - Show this help")
	fmt.Println("  tables, \\dt  - List all tables")
	fmt.Println("  clear, \\c    - Clear screen")
	fmt.Println("  exit, \\q     - Exit the CLI")
	fmt.Println("\n💡 SQL Examples (Spanner types):")
	fmt.Println("  CREATE TABLE users (")
	fmt.Println("    id INT64 NOT NULL,")
	fmt.Println("    name STRING(100),")
	fmt.Println("    email STRING(100),")
	fmt.Println("    created_at TIMESTAMP")
	fmt.Println("  ) PRIMARY KEY (id);")
	fmt.Println()
	fmt.Println("  INSERT INTO users (id, name, email, created_at)")
	fmt.Println("  VALUES (1, 'John Doe', 'john@example.com', CURRENT_TIMESTAMP());")
	fmt.Println()
	fmt.Println("  SELECT * FROM users;")
	fmt.Println()

	fmt.Println("🔁 PostgreSQL dialect on pgAdapter (recommended):")
	fmt.Println("  CREATE TABLE users (")
	fmt.Println("    id BIGINT PRIMARY KEY,")
	fmt.Println("    name VARCHAR(100),")
	fmt.Println("    email VARCHAR(100),")
	fmt.Println("    created_at TIMESTAMPTZ")
	fmt.Println("  );")
	fmt.Println()
	fmt.Println("  INSERT INTO users (id, name, email, created_at)")
	fmt.Println("  VALUES (1, 'John Doe', 'john@example.com', CURRENT_TIMESTAMP);")
	fmt.Println()
	fmt.Println("  SELECT * FROM users;")
	fmt.Println()

	fmt.Println("⚠️  pgAdapter/Spanner notes:")
	fmt.Println("  - Every table must have a PRIMARY KEY")
	fmt.Println("  - SERIAL/SEQUENCE are generally unsupported")
	fmt.Println("  - Some PostgreSQL features may be limited vs stock PostgreSQL")
}

func showTables(ctx context.Context, db *sql.DB) {
	query := `
		SELECT table_name 
		FROM information_schema.tables 
		WHERE table_schema = ''
		ORDER BY table_name
	`

	rows, err := db.QueryContext(ctx, query)
	if err != nil {
		fmt.Printf("❌ Error: %v\n", err)
		return
	}
	defer rows.Close()

	var tables []string
	for rows.Next() {
		var tableName string
		if err := rows.Scan(&tableName); err != nil {
			fmt.Printf("❌ Error scanning row: %v\n", err)
			continue
		}
		tables = append(tables, tableName)
	}

	if len(tables) == 0 {
		fmt.Println("No tables found.")
	} else {
		fmt.Printf("\n📋 Tables (%d):\n", len(tables))
		for _, table := range tables {
			fmt.Printf("  - %s\n", table)
		}
	}
	fmt.Println()
}

func executeQuery(ctx context.Context, db *sql.DB, query string) {
	start := time.Now()

	// Remove trailing semicolon for cleaner processing
	query = strings.TrimSuffix(strings.TrimSpace(query), ";")

	// Check if it's a SELECT query
	isSelect := strings.HasPrefix(strings.ToUpper(strings.TrimSpace(query)), "SELECT")

	if isSelect {
		rows, err := db.QueryContext(ctx, query)
		if err != nil {
			fmt.Printf("❌ Error: %v\n\n", err)
			return
		}
		defer rows.Close()

		// Get column names
		columns, err := rows.Columns()
		if err != nil {
			fmt.Printf("❌ Error getting columns: %v\n\n", err)
			return
		}

		// Prepare table writer (defensive to support multiple tablewriter versions)
		table := tablewriter.NewWriter(os.Stdout)
		if ts, ok := any(table).(interface{ SetHeader([]string) }); ok {
			ts.SetHeader(columns)
		} else {
			table.Append(columns)
		}
		// Optional styling if methods exist in the linked tablewriter version
		if x, ok := any(table).(interface{ SetAutoWrapText(bool) }); ok {
			x.SetAutoWrapText(false)
		}
		if x, ok := any(table).(interface{ SetAutoFormatHeaders(bool) }); ok {
			x.SetAutoFormatHeaders(true)
		}
		if x, ok := any(table).(interface{ SetCenterSeparator(string) }); ok {
			x.SetCenterSeparator("|")
		}
		if x, ok := any(table).(interface{ SetColumnSeparator(string) }); ok {
			x.SetColumnSeparator("|")
		}
		if x, ok := any(table).(interface{ SetRowSeparator(string) }); ok {
			x.SetRowSeparator("-")
		}
		if x, ok := any(table).(interface{ SetHeaderLine(bool) }); ok {
			x.SetHeaderLine(true)
		}
		if x, ok := any(table).(interface{ SetBorder(bool) }); ok {
			x.SetBorder(true)
		}

		// Scan rows
		rowCount := 0
		values := make([]sql.RawBytes, len(columns))
		scanArgs := make([]interface{}, len(values))
		for i := range values {
			scanArgs[i] = &values[i]
		}

		for rows.Next() {
			err := rows.Scan(scanArgs...)
			if err != nil {
				fmt.Printf("❌ Error scanning row: %v\n", err)
				continue
			}

			var row []string
			for _, col := range values {
				if col == nil {
					row = append(row, "NULL")
				} else {
					row = append(row, string(col))
				}
			}
			table.Append(row)
			rowCount++
		}

		fmt.Println()
		table.Render()

		elapsed := time.Since(start)
		fmt.Printf("\n(%d rows) Time: %v\n\n", rowCount, elapsed.Round(time.Millisecond))

	} else {
		// Execute non-SELECT query
		result, err := db.ExecContext(ctx, query)
		if err != nil {
			fmt.Printf("❌ Error: %v\n\n", err)
			return
		}

		rowsAffected, _ := result.RowsAffected()
		elapsed := time.Since(start)

		fmt.Printf("\n✅ Query OK, %d rows affected (%v)\n\n", rowsAffected, elapsed.Round(time.Millisecond))
	}
}
