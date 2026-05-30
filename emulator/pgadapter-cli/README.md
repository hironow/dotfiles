# pgAdapter CLI

A command-line interface for accessing Spanner Emulator through pgAdapter using PostgreSQL protocol.

## Features

- Interactive SQL shell
- Table listing
- Pretty-printed query results
- Query timing
- Multi-line SQL support

## Usage

### Using Docker Compose (Recommended)

From the parent directory:

```bash
# Run the CLI tool
docker compose --profile cli run --rm pgadapter-cli
```

### Building and Running Locally

```bash
# Build the CLI
go build -o pgadapter-cli

# Run the CLI
./pgadapter-cli
```

### Using Docker Directly

```bash
docker build -t pgadapter-cli .
docker run -it --rm --network emulator-network pgadapter-cli
```

### Configuration

The CLI is configured through environment variables:

- `PGADAPTER_HOST`: pgAdapter host (default: `pgadapter` for Docker, `localhost` for local)
- `PGADAPTER_PORT`: pgAdapter host port (default: `55432` for host access; inside Compose the service listens on `5432`)
- `PGADAPTER_DATABASE`: Database name (default: `test-instance`)
- `PGADAPTER_USER`: Username (default: `user`)
- `PGADAPTER_PASSWORD`: Password (default: empty)

For Docker Compose usage, these are automatically configured to connect to the pgAdapter instance.

## Commands

- `help` or `\h` - Show help
- `tables` or `\dt` - List all tables
- `clear` or `\c` - Clear screen
- `exit` or `\q` - Exit the CLI

## SQL Examples

### Basic Examples

```sql
-- Create a table
CREATE TABLE users (
  id INT64 NOT NULL,
  name STRING(100),
  email STRING(100),
  created_at TIMESTAMP
) PRIMARY KEY (id);

-- Insert data
INSERT INTO users (id, name, email, created_at)
VALUES (1, 'John Doe', 'john@example.com', CURRENT_TIMESTAMP());

-- Query data
SELECT * FROM users;

-- Update data
UPDATE users SET email = 'newemail@example.com' WHERE id = 1;

-- Delete data
DELETE FROM users WHERE id = 1;
```

### Advanced Examples

```sql
-- Create table with indexes
CREATE TABLE products (
  id INT64 NOT NULL,
  name STRING(100),
  price NUMERIC,
  category STRING(50),
  stock INT64
) PRIMARY KEY (id);

CREATE INDEX idx_category ON products(category);
CREATE INDEX idx_price ON products(price);

-- Bulk insert
INSERT INTO products (id, name, price, category, stock) VALUES
  (1, 'Laptop', 999.99, 'Electronics', 50),
  (2, 'Mouse', 29.99, 'Electronics', 200),
  (3, 'Desk', 199.99, 'Furniture', 30);

-- Complex queries
SELECT category, COUNT(*) as count, AVG(price) as avg_price
FROM products
GROUP BY category
HAVING COUNT(*) > 1;

-- Joins (create related table first)
CREATE TABLE orders (
  id INT64 NOT NULL,
  user_id INT64,
  product_id INT64,
  quantity INT64,
  order_date TIMESTAMP
) PRIMARY KEY (id);

SELECT u.name, p.name as product, o.quantity
FROM orders o
JOIN users u ON o.user_id = u.id
JOIN products p ON o.product_id = p.id;
```

## pgAdapter-Specific Notes

While pgAdapter provides PostgreSQL protocol compatibility, there are some differences from standard PostgreSQL:

1. **Data Types**: Uses Spanner data types (INT64, STRING, etc.) instead of PostgreSQL types
2. **Primary Keys**: Tables must have an explicit PRIMARY KEY
3. **Transactions**: Follow Spanner's transaction semantics
4. **Some PostgreSQL features may not be supported**: Check Spanner documentation for limitations

## Troubleshooting

### Connection Issues

If you cannot connect to pgAdapter:

1. Verify pgAdapter is running:

   ```bash
   docker ps | grep pgadapter
   ```

2. Check network connectivity:

   ```bash
   nc -zv localhost ${PGADAPTER_PORT:-55432}
   ```

3. Ensure environment variables are set correctly

### SQL Errors

Common issues and solutions:

1. **"Table must have a primary key"**: Spanner requires all tables to have a primary key
2. **Data type errors**: Use Spanner-specific types (INT64, STRING, NUMERIC, etc.)
3. **Transaction errors**: Some operations may require explicit transaction boundaries

### Docker Network Issues

If running in Docker and getting connection errors:

- Ensure you're using the correct network (`emulator-network`)
- Use container names instead of `localhost` when connecting between containers
