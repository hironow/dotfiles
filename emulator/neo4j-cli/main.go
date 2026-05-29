package main

import (
	"bufio"
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/neo4j/neo4j-go-driver/v5/neo4j"
	"github.com/olekukonko/tablewriter"
)

func getConnectionParams() (string, string, string) {
	uri := os.Getenv("NEO4J_URI")
	if uri == "" {
		uri = "bolt://localhost:7687"
	}
	username := os.Getenv("NEO4J_USER")
	if username == "" {
		username = "neo4j"
	}
	password := os.Getenv("NEO4J_PASSWORD")
	if password == "" {
		password = "password"
	}
	return uri, username, password
}

func main() {
	fmt.Println("🚀 Neo4j CLI for Neo4j Emulator")
	fmt.Println("======================================")

	// Get connection parameters
	uri, username, password := getConnectionParams()

	// Create driver
	driver, err := neo4j.NewDriverWithContext(uri, neo4j.BasicAuth(username, password, ""))
	if err != nil {
		fmt.Printf("❌ Failed to create driver: %v\n", err)
		os.Exit(1)
	}
	defer driver.Close(context.Background())

	// Verify connectivity
	ctx := context.Background()
	err = driver.VerifyConnectivity(ctx)
	if err != nil {
		fmt.Printf("❌ Failed to connect to Neo4j: %v\n", err)
		fmt.Println("💡 Make sure Neo4j is running on", uri)
		os.Exit(1)
	}

	fmt.Println("✅ Connected to Neo4j")
	fmt.Println("\nType 'help' for commands, or enter Cypher queries")
	fmt.Println("Type 'exit' or 'quit' to leave")
	fmt.Println()

	// Create session
	session := driver.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeWrite})
	defer session.Close(ctx)

	// Interactive loop
	scanner := bufio.NewScanner(os.Stdin)
	var multiline []string

	for {
		if len(multiline) == 0 {
			fmt.Print("neo4j> ")
		} else {
			fmt.Print("    -> ")
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
			case "labels", "\\l":
				showLabels(ctx, session)
				continue
			case "clear", "\\c":
				fmt.Print("\033[2J\033[H")
				continue
			case "schema", "\\s":
				showSchema(ctx, session)
				continue
			}
		}

		// Handle multiline Cypher
		if line == "" {
			continue
		}

		multiline = append(multiline, line)

		// Check if query is complete (ends with semicolon)
		if strings.HasSuffix(line, ";") {
			query := strings.Join(multiline, " ")
			query = strings.TrimSuffix(query, ";")
			multiline = nil

			executeQuery(ctx, session, query)
		}
	}
}

func printHelp() {
	fmt.Println("\n📚 Available Commands:")
	fmt.Println("  help, \\h     - Show this help")
	fmt.Println("  labels, \\l   - List all node labels")
	fmt.Println("  schema, \\s   - Show database schema")
	fmt.Println("  clear, \\c    - Clear screen")
	fmt.Println("  exit, \\q     - Exit the CLI")
	fmt.Println("\n💡 Cypher Examples:")
	fmt.Println("  CREATE (n:Person {name: 'Alice', age: 30});")
	fmt.Println()
	fmt.Println("  CREATE (n:Person {name: 'Bob', age: 25})")
	fmt.Println("  CREATE (m:Person {name: 'Alice', age: 30})")
	fmt.Println("  CREATE (n)-[:KNOWS]->(m);")
	fmt.Println()
	fmt.Println("  MATCH (n:Person) RETURN n.name, n.age;")
	fmt.Println()
	fmt.Println("  MATCH (n:Person)-[r:KNOWS]->(m:Person)")
	fmt.Println("  RETURN n.name AS person1, m.name AS person2;")
	fmt.Println()
}

func showLabels(ctx context.Context, session neo4j.SessionWithContext) {
	query := "CALL db.labels() YIELD label RETURN label ORDER BY label"

	result, err := session.Run(ctx, query, nil)
	if err != nil {
		fmt.Printf("❌ Error: %v\n", err)
		return
	}

	var labels []string
	for result.Next(ctx) {
		record := result.Record()
		label, _ := record.Get("label")
		labels = append(labels, label.(string))
	}

	if err = result.Err(); err != nil {
		fmt.Printf("❌ Error: %v\n", err)
		return
	}

	if len(labels) == 0 {
		fmt.Println("No labels found.")
	} else {
		fmt.Printf("\n📋 Labels (%d):\n", len(labels))
		for _, label := range labels {
			fmt.Printf("  - %s\n", label)
		}
	}
	fmt.Println()
}

func showSchema(ctx context.Context, session neo4j.SessionWithContext) {
	// Show constraints
	fmt.Println("\n📊 Constraints:")
	constraintQuery := "SHOW CONSTRAINTS"

	result, err := session.Run(ctx, constraintQuery, nil)
	if err != nil {
		// Try older syntax if new one fails
		result, err = session.Run(ctx, "CALL db.constraints()", nil)
		if err != nil {
			fmt.Printf("  ❌ Error fetching constraints: %v\n", err)
		}
	}

	hasConstraints := false
	if err == nil {
		for result.Next(ctx) {
			hasConstraints = true
			record := result.Record()
			fmt.Printf("  - %v\n", record.Values[0])
		}
	}

	if !hasConstraints {
		fmt.Println("  No constraints defined")
	}

	// Show indexes
	fmt.Println("\n📑 Indexes:")
	indexQuery := "SHOW INDEXES"

	result, err = session.Run(ctx, indexQuery, nil)
	if err != nil {
		// Try older syntax if new one fails
		result, err = session.Run(ctx, "CALL db.indexes()", nil)
		if err != nil {
			fmt.Printf("  ❌ Error fetching indexes: %v\n", err)
		}
	}

	hasIndexes := false
	if err == nil {
		for result.Next(ctx) {
			hasIndexes = true
			record := result.Record()
			fmt.Printf("  - %v\n", record.Values[0])
		}
	}

	if !hasIndexes {
		fmt.Println("  No indexes defined")
	}

	fmt.Println()
}

func executeQuery(ctx context.Context, session neo4j.SessionWithContext, query string) {
	start := time.Now()

	result, err := session.Run(ctx, query, nil)
	if err != nil {
		fmt.Printf("❌ Error: %v\n\n", err)
		return
	}

	// Check if it's a read query by looking at the result
	records, err := result.Collect(ctx)
	if err != nil {
		fmt.Printf("❌ Error collecting results: %v\n\n", err)
		return
	}

	summary, _ := result.Consume(ctx)
	elapsed := time.Since(start)

	// If we have records to display
	if len(records) > 0 {
		// Get keys from the first record
		if len(records[0].Keys) > 0 {
			// Prepare table writer (defensive to support multiple tablewriter versions)
			table := tablewriter.NewWriter(os.Stdout)
			if ts, ok := any(table).(interface{ SetHeader([]string) }); ok {
				ts.SetHeader(records[0].Keys)
			} else {
				table.Append(records[0].Keys)
			}
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

			// Add rows
			for _, record := range records {
				var row []string
				for _, key := range record.Keys {
					value, _ := record.Get(key)
					row = append(row, formatValue(value))
				}
				table.Append(row)
			}

			fmt.Println()
			table.Render()
			fmt.Printf("\n(%d rows) Time: %v\n\n", len(records), elapsed.Round(time.Millisecond))
		}
	} else {
		// No records returned (write query)
		counters := summary.Counters()

		var changes []string
		if counters.NodesCreated() > 0 {
			changes = append(changes, fmt.Sprintf("%d nodes created", counters.NodesCreated()))
		}
		if counters.NodesDeleted() > 0 {
			changes = append(changes, fmt.Sprintf("%d nodes deleted", counters.NodesDeleted()))
		}
		if counters.RelationshipsCreated() > 0 {
			changes = append(changes, fmt.Sprintf("%d relationships created", counters.RelationshipsCreated()))
		}
		if counters.RelationshipsDeleted() > 0 {
			changes = append(changes, fmt.Sprintf("%d relationships deleted", counters.RelationshipsDeleted()))
		}
		if counters.PropertiesSet() > 0 {
			changes = append(changes, fmt.Sprintf("%d properties set", counters.PropertiesSet()))
		}
		if counters.LabelsAdded() > 0 {
			changes = append(changes, fmt.Sprintf("%d labels added", counters.LabelsAdded()))
		}
		if counters.LabelsRemoved() > 0 {
			changes = append(changes, fmt.Sprintf("%d labels removed", counters.LabelsRemoved()))
		}
		if counters.IndexesAdded() > 0 {
			changes = append(changes, fmt.Sprintf("%d indexes added", counters.IndexesAdded()))
		}
		if counters.IndexesRemoved() > 0 {
			changes = append(changes, fmt.Sprintf("%d indexes removed", counters.IndexesRemoved()))
		}
		if counters.ConstraintsAdded() > 0 {
			changes = append(changes, fmt.Sprintf("%d constraints added", counters.ConstraintsAdded()))
		}
		if counters.ConstraintsRemoved() > 0 {
			changes = append(changes, fmt.Sprintf("%d constraints removed", counters.ConstraintsRemoved()))
		}

		if len(changes) > 0 {
			fmt.Printf("\n✅ Query OK: %s (%v)\n\n", strings.Join(changes, ", "), elapsed.Round(time.Millisecond))
		} else {
			fmt.Printf("\n✅ Query OK (%v)\n\n", elapsed.Round(time.Millisecond))
		}
	}
}

func formatValue(value interface{}) string {
	if value == nil {
		return "NULL"
	}

	switch v := value.(type) {
	case neo4j.Node:
		labels := strings.Join(v.Labels, ":")
		props := make([]string, 0)
		for k, val := range v.Props {
			props = append(props, fmt.Sprintf("%s: %v", k, val))
		}
		return fmt.Sprintf("(:%s {%s})", labels, strings.Join(props, ", "))
	case neo4j.Relationship:
		props := make([]string, 0)
		for k, val := range v.Props {
			props = append(props, fmt.Sprintf("%s: %v", k, val))
		}
		if len(props) > 0 {
			return fmt.Sprintf("[:%s {%s}]", v.Type, strings.Join(props, ", "))
		}
		return fmt.Sprintf("[:%s]", v.Type)
	case neo4j.Path:
		return fmt.Sprintf("Path[%d nodes, %d relationships]", len(v.Nodes), len(v.Relationships))
	case []interface{}:
		items := make([]string, len(v))
		for i, item := range v {
			items[i] = formatValue(item)
		}
		return fmt.Sprintf("[%s]", strings.Join(items, ", "))
	case map[string]interface{}:
		items := make([]string, 0)
		for k, val := range v {
			items = append(items, fmt.Sprintf("%s: %v", k, formatValue(val)))
		}
		return fmt.Sprintf("{%s}", strings.Join(items, ", "))
	default:
		return fmt.Sprintf("%v", v)
	}
}
