package main

import (
	"context"
	"fmt"
	"io"
	"net"
	"os"
	"time"
)

const connectTimeout = 2 * time.Second

func run(ctx context.Context, args []string, stderr io.Writer) int {
	if len(args) != 1 {
		fmt.Fprintln(stderr, "usage: tcp-healthcheck host:port")
		return 1
	}
	if err := checkTCP(ctx, args[0], (&net.Dialer{}).DialContext); err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}
	return 0
}

func checkTCP(ctx context.Context, address string, dial func(context.Context, string, string) (net.Conn, error)) error {
	ctx, cancel := context.WithTimeout(ctx, connectTimeout)
	defer cancel()
	conn, err := dial(ctx, "tcp", address)
	if err != nil {
		return fmt.Errorf("connect: %w", err)
	}
	if err := conn.Close(); err != nil {
		return fmt.Errorf("close: %w", err)
	}
	return nil
}

func main() {
	os.Exit(run(context.Background(), os.Args[1:], os.Stderr))
}
