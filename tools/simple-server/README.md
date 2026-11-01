# Simple Server

A small Go static file server for HTTP or HTTPS. It shuts down cleanly on
Ctrl-C (SIGINT) or SIGTERM.

`just check-localhost-tls` (macOS and Linux) uses it to check the
`localhost.hironow.dev` certificate on port 443.

## Usage

Run these from `tools/simple-server/`:

```bash
go build -o simple-server main.go

./simple-server                         # http://localhost:8080, serves .
./simple-server -port 3000 -dir ./assets
./simple-server -cert path/to/cert.pem -key path/to/key.pem   # HTTPS
```

## Flags

- `-host`: host name to bind (default `localhost`)
- `-port`: port to listen on (default `8080`)
- `-dir`: directory to serve (default `.`)
- `-cert`, `-key`: TLS certificate and key files. HTTPS needs both; with
  either one missing, it serves plain HTTP.
