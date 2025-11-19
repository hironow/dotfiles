package main

import (
	"context"
	"flag"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func main() {
	// Define flags
	host := flag.String("host", "localhost", "Hostname to bind to")
	port := flag.String("port", "8080", "Port to listen on")
	dir := flag.String("dir", ".", "Directory to serve")
	certFile := flag.String("cert", "", "Path to TLS certificate file")
	keyFile := flag.String("key", "", "Path to TLS private key file")
	flag.Parse()

	// Setup logger
	logger := log.New(os.Stdout, "[simple-server] ", log.LstdFlags)

	// Verify directory exists
	if _, err := os.Stat(*dir); os.IsNotExist(err) {
		logger.Fatalf("Directory does not exist: %s", *dir)
	}

	// Setup server
	addr := *host + ":" + *port
	mux := http.NewServeMux()
	fs := http.FileServer(http.Dir(*dir))
	mux.Handle("/", fs)

	srv := &http.Server{
		Addr:    addr,
		Handler: mux,
	}

	// Start server in a goroutine
	go func() {
		if *certFile != "" && *keyFile != "" {
			logger.Printf("Starting HTTPS server at https://%s serving %s", addr, *dir)
			if err := srv.ListenAndServeTLS(*certFile, *keyFile); err != nil && err != http.ErrServerClosed {
				logger.Fatalf("ListenAndServeTLS: %v", err)
			}
		} else {
			logger.Printf("Starting HTTP server at http://%s serving %s", addr, *dir)
			if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
				logger.Fatalf("ListenAndServe: %v", err)
			}
		}
	}()

	// Graceful shutdown
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	logger.Println("Shutting down server...")

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		logger.Fatal("Server forced to shutdown: ", err)
	}

	logger.Println("Server exiting")
}
