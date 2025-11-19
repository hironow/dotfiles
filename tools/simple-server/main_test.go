package main

import (
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
)

func TestFileServer(t *testing.T) {
	// Create a temporary directory and file
	tmpDir, err := os.MkdirTemp("", "simple-server-test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	content := []byte("Hello, World!")
	err = os.WriteFile(tmpDir+"/index.html", content, 0644)
	if err != nil {
		t.Fatal(err)
	}

	// Create a request to the file server
	req, err := http.NewRequest("GET", "/", nil)
	if err != nil {
		t.Fatal(err)
	}

	// Create a ResponseRecorder to record the response
	rr := httptest.NewRecorder()

	// Create the file server handler
	fs := http.FileServer(http.Dir(tmpDir))
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fs.ServeHTTP(w, r)
	})

	// Serve the request
	handler.ServeHTTP(rr, req)

	// Check the status code
	if status := rr.Code; status != http.StatusOK {
		t.Errorf("handler returned wrong status code: got %v want %v",
			status, http.StatusOK)
	}

	// Check the response body
	expected := string(content)
	if rr.Body.String() != expected {
		t.Errorf("handler returned unexpected body: got %v want %v",
			rr.Body.String(), expected)
	}
}

func TestFileServerNotFound(t *testing.T) {
	// Create a temporary directory
	tmpDir, err := os.MkdirTemp("", "simple-server-test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	// Create a request to a non-existent file
	req, err := http.NewRequest("GET", "/nonexistent", nil)
	if err != nil {
		t.Fatal(err)
	}

	rr := httptest.NewRecorder()
	fs := http.FileServer(http.Dir(tmpDir))
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fs.ServeHTTP(w, r)
	})

	handler.ServeHTTP(rr, req)

	if status := rr.Code; status != http.StatusNotFound {
		t.Errorf("handler returned wrong status code: got %v want %v",
			status, http.StatusNotFound)
	}
}
