# Simple Server

A simple HTTP/HTTPS static file server written in Go.

## Features

- Serves static files from a specified directory.
- Supports HTTP and HTTPS.
- Graceful shutdown support.
- Configurable via command-line flags.

## Usage

Build the server:

```bash
go build -o simple-server main.go
```

Run the server:

```bash
# Run on default port 8080 serving current directory
./simple-server

# Run on custom port and directory
./simple-server -port 3000 -dir ./assets

# Run with HTTPS
./simple-server -cert path/to/cert.pem -key path/to/key.pem
```

## Flags

- `-host`: Hostname to bind to (default: "localhost")
- `-port`: Port to listen on (default: "8080")
- `-dir`: Directory to serve (default: ".")
- `-cert`: Path to TLS certificate file (optional)
- `-key`: Path to TLS private key file (optional)
