package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/olekukonko/tablewriter"
	"github.com/tidwall/gjson"
)

var (
	host   string
	port   string
	client *http.Client
)

func init() {
	host = os.Getenv("QDRANT_HOST")
	if host == "" {
		host = "localhost"
	}

	port = os.Getenv("QDRANT_PORT")
	if port == "" {
		port = "6333"
	}

	client = &http.Client{
		Timeout: 30 * time.Second,
	}
}

func main() {
	fmt.Printf("Connected to Qdrant at %s:%s\n", host, port)
	fmt.Println("Type \\h for help, \\q to quit")

	reader := bufio.NewReader(os.Stdin)
	var multiLineQuery strings.Builder
	inMultiLine := false

	for {
		if inMultiLine {
			fmt.Print("... ")
		} else {
			fmt.Print("qdrant> ")
		}

		line, err := reader.ReadString('\n')
		if err != nil {
			if err == io.EOF {
				fmt.Println("\nBye!")
				return
			}
			fmt.Printf("Error reading input: %v\n", err)
			continue
		}

		line = strings.TrimSpace(line)

		// Handle special commands
		if !inMultiLine && strings.HasPrefix(line, "\\") {
			switch line {
			case "\\h", "\\help":
				printHelp()
			case "\\q", "\\quit", "\\exit":
				fmt.Println("Bye!")
				return
			case "\\c", "\\clear":
				clearScreen()
			case "\\l", "\\collections":
				listCollections()
			case "\\i", "\\info":
				showClusterInfo()
			default:
				fmt.Printf("Unknown command: %s\n", line)
			}
			continue
		}

		// Handle multi-line queries
		if inMultiLine {
			multiLineQuery.WriteString(line)
			multiLineQuery.WriteString(" ")
			if strings.HasSuffix(line, ";") {
				query := strings.TrimSuffix(multiLineQuery.String(), ";")
				query = strings.TrimSpace(query)
				inMultiLine = false
				multiLineQuery.Reset()
				executeCommand(query)
			}
		} else if line != "" {
			if strings.HasSuffix(line, ";") {
				query := strings.TrimSuffix(line, ";")
				executeCommand(query)
			} else {
				multiLineQuery.WriteString(line)
				multiLineQuery.WriteString(" ")
				inMultiLine = true
			}
		}
	}
}

func printHelp() {
	fmt.Println("\nQdrant CLI Commands:")
	fmt.Println("  \\h, \\help      Show this help message")
	fmt.Println("  \\q, \\quit      Exit the CLI")
	fmt.Println("  \\c, \\clear     Clear the screen")
	fmt.Println("  \\l, \\collections  List all collections")
	fmt.Println("  \\i, \\info      Show cluster info")
	fmt.Println("\nAPI Commands (end with semicolon):")
	fmt.Println("  GET /collections;")
	fmt.Println("  GET /collections/{collection_name};")
	fmt.Println("  PUT /collections/{collection_name} {\"vectors\": {\"size\": 4, \"distance\": \"Cosine\"}};")
	fmt.Println("  DELETE /collections/{collection_name};")
	fmt.Println("  PUT /collections/{collection_name}/points {\"points\": [...]};")
	fmt.Println("  POST /collections/{collection_name}/points/search {\"vector\": [...], \"limit\": 10};")
	fmt.Println("\nExamples:")
	fmt.Println("  PUT /collections/test_collection {\"vectors\": {\"size\": 4, \"distance\": \"Cosine\"}};")
	fmt.Println("  GET /collections/test_collection;")
	fmt.Println("  PUT /collections/test_collection/points {\"points\": [{\"id\": 1, \"vector\": [0.1, 0.2, 0.3, 0.4]}]};")
	fmt.Println("  POST /collections/test_collection/points/search {\"vector\": [0.1, 0.2, 0.3, 0.4], \"limit\": 5};")
	fmt.Println()
}

func clearScreen() {
	fmt.Print("\033[H\033[2J")
}

func listCollections() {
	resp, err := makeRequest("GET", "/collections", nil)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		return
	}

	result := gjson.Get(resp, "result.collections")
	if !result.Exists() {
		fmt.Println("No collections found")
		return
	}

	table := tablewriter.NewWriter(os.Stdout)
	if ts, ok := any(table).(interface{ SetHeader([]string) }); ok {
		ts.SetHeader([]string{"Name", "Vectors Count", "Points Count", "Config"})
	} else {
		table.Append([]string{"Name", "Vectors Count", "Points Count", "Config"})
	}

	result.ForEach(func(key, value gjson.Result) bool {
		name := value.Get("name").String()

		// Get collection details
		detailResp, err := makeRequest("GET", fmt.Sprintf("/collections/%s", name), nil)
		if err == nil {
			details := gjson.Get(detailResp, "result")
			vectorsCount := details.Get("vectors_count").String()
			pointsCount := details.Get("points_count").String()
			vectorSize := details.Get("config.params.vectors.size").String()
			distance := details.Get("config.params.vectors.distance").String()
			config := fmt.Sprintf("size=%s, distance=%s", vectorSize, distance)

			table.Append([]string{name, vectorsCount, pointsCount, config})
		}
		return true
	})

	table.Render()
}

func showClusterInfo() {
	resp, err := makeRequest("GET", "/", nil)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		return
	}

	result := gjson.Parse(resp)

	fmt.Println("\nCluster Information:")
	fmt.Printf("Title: %s\n", result.Get("title").String())
	fmt.Printf("Version: %s\n", result.Get("version").String())
	fmt.Printf("Commit: %s\n", result.Get("commit").String())
	fmt.Println()
}

func executeCommand(command string) {
	start := time.Now()

	parts := strings.SplitN(command, " ", 3)
	if len(parts) < 2 {
		fmt.Println("Invalid command format. Use: METHOD /path [body]")
		return
	}

	method := strings.ToUpper(parts[0])
	path := parts[1]
	var body []byte

	if len(parts) == 3 {
		body = []byte(parts[2])
	}

	resp, err := makeRequest(method, path, body)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		return
	}

	// Pretty print JSON response
	var prettyJSON bytes.Buffer
	if err := json.Indent(&prettyJSON, []byte(resp), "", "  "); err != nil {
		fmt.Println(resp)
	} else {
		fmt.Println(prettyJSON.String())
	}

	fmt.Printf("\nTime: %v\n", time.Since(start))
}

func makeRequest(method, path string, body []byte) (string, error) {
	url := fmt.Sprintf("http://%s:%s%s", host, port, path)

	var req *http.Request
	var err error

	if body != nil {
		req, err = http.NewRequest(method, url, bytes.NewBuffer(body))
		req.Header.Set("Content-Type", "application/json")
	} else {
		req, err = http.NewRequest(method, url, nil)
	}

	if err != nil {
		return "", err
	}

	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	if resp.StatusCode >= 400 {
		return string(respBody), fmt.Errorf("HTTP %d: %s", resp.StatusCode, resp.Status)
	}

	return string(respBody), nil
}
