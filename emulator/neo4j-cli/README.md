# Neo4j CLI

Interactive command-line interface for Neo4j in the emulator environment.

## Features

- Interactive Cypher query execution
- Auto-completion for multi-line queries
- Table-formatted query results
- Built-in commands for exploring the database
- Connection health checks

## Usage

### Running with Docker Compose

```bash
# Start Neo4j and run the CLI
docker compose --profile cli run --rm neo4j-cli

# Or, if Neo4j is already running
docker compose run --rm neo4j-cli
```

### Available Commands

- `help`, `\h` - Show available commands and examples
- `labels`, `\l` - List all node labels in the database
- `schema`, `\s` - Show database schema (constraints and indexes)
- `clear`, `\c` - Clear the screen
- `exit`, `\q` - Exit the CLI

### Cypher Query Examples

```cypher
-- Create nodes
CREATE (n:Person {name: 'Alice', age: 30});

-- Create relationships
CREATE (n:Person {name: 'Bob', age: 25})
CREATE (m:Person {name: 'Alice', age: 30})
CREATE (n)-[:KNOWS]->(m);

-- Query data
MATCH (n:Person) RETURN n.name, n.age;

-- Query relationships
MATCH (n:Person)-[r:KNOWS]->(m:Person)
RETURN n.name AS person1, m.name AS person2;
```

## Environment Variables

- `NEO4J_URI` - Neo4j connection URI (default: `bolt://localhost:7687`)
- `NEO4J_USER` - Neo4j username (default: `neo4j`)
- `NEO4J_PASSWORD` - Neo4j password (default: `password`)

## Building Locally

```bash
cd neo4j-cli
go build -o neo4j-cli .
./neo4j-cli
```
