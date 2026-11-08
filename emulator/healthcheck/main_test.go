package main

import (
	"bytes"
	"context"
	"errors"
	"io"
	"net"
	"os"
	"os/exec"
	"strings"
	"testing"
	"time"
)

func TestRunConnectsAndCloses(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()

	if code := run(t.Context(), []string{listener.Addr().String()}, io.Discard); code != 0 {
		t.Fatalf("listening loopback address: exit %d, want 0", code)
	}
	if err := listener.(*net.TCPListener).SetDeadline(time.Now().Add(2 * time.Second)); err != nil {
		t.Fatal(err)
	}
	conn, err := listener.Accept()
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	if err := conn.SetReadDeadline(time.Now().Add(2 * time.Second)); err != nil {
		t.Fatal(err)
	}
	var data [1]byte
	if n, err := conn.Read(data[:]); n != 0 || !errors.Is(err, io.EOF) {
		t.Fatalf("probe must close without sending data: n=%d err=%v", n, err)
	}
}

func TestRunRejectsUsageAndMalformedAddresses(t *testing.T) {
	for _, args := range [][]string{nil, {"a", "b"}, {""}, {"127.0.0.1"}, {"127.0.0.1:bad-port"}} {
		t.Run(strings.Join(args, ","), func(t *testing.T) {
			var stderr bytes.Buffer
			if code := run(t.Context(), args, &stderr); code != 1 {
				t.Errorf("exit %d, want 1", code)
			}
			if stderr.Len() == 0 {
				t.Error("failure must explain usage or connection error")
			}
		})
	}
}

func TestRunRefusedConnection(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	address := listener.Addr().String()
	if err := listener.Close(); err != nil {
		t.Fatal(err)
	}
	var stderr bytes.Buffer
	if code := run(t.Context(), []string{address}, &stderr); code != 1 {
		t.Fatalf("closed loopback listener: exit %d, want 1", code)
	}
	if !strings.Contains(stderr.String(), "refused") {
		t.Fatalf("expected connection refusal, got %q", stderr.String())
	}
}

func TestRunCanceledAndExpiredContexts(t *testing.T) {
	canceled, cancel := context.WithCancel(t.Context())
	cancel()
	expired, stop := context.WithDeadline(t.Context(), time.Now().Add(-time.Second))
	defer stop()
	for _, tc := range []struct {
		name string
		ctx  context.Context
		want string
	}{
		{"canceled", canceled, "canceled"},
		{"expired", expired, "i/o timeout"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			var stderr bytes.Buffer
			if code := run(tc.ctx, []string{"127.0.0.1:1"}, &stderr); code != 1 {
				t.Fatalf("exit %d, want 1", code)
			}
			if !strings.Contains(stderr.String(), tc.want) {
				t.Fatalf("error %q must contain %q", stderr.String(), tc.want)
			}
		})
	}
}

func TestCheckTCPBoundsDialAndPropagatesTimeout(t *testing.T) {
	start := time.Now()
	called := false
	err := checkTCP(t.Context(), "127.0.0.1:9010", func(ctx context.Context, network, address string) (net.Conn, error) {
		called = true
		deadline, ok := ctx.Deadline()
		if !ok || deadline.Before(start) || deadline.After(time.Now().Add(2*time.Second)) {
			t.Errorf("dial must have a deadline no more than two seconds away: %v, %v", deadline, ok)
		}
		if network != "tcp" || address != "127.0.0.1:9010" {
			t.Errorf("dial arguments: %q %q", network, address)
		}
		return nil, context.DeadlineExceeded
	})
	if !called || !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("dial timeout must fail: called=%v err=%v", called, err)
	}
}

func TestHealthcheckProcess(t *testing.T) {
	if os.Getenv("HEALTHCHECK_TEST_PROCESS") != "1" {
		return
	}
	if len(os.Args) < 3 || os.Args[2] != "--" {
		t.Fatal("subprocess must separate test flags from CLI arguments")
	}
	os.Args = os.Args[2:]
	main()
}

func TestCLIExitStatus(t *testing.T) {
	binary, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	for _, tc := range []struct {
		name string
		args []string
		want int
	}{
		{"listening", []string{listener.Addr().String()}, 0},
		{"usage", nil, 1},
		{"malformed", []string{"127.0.0.1"}, 1},
	} {
		t.Run(tc.name, func(t *testing.T) {
			args := append([]string{"-test.run=^TestHealthcheckProcess$", "--"}, tc.args...)
			cmd := exec.CommandContext(t.Context(), binary, args...)
			cmd.Env = append(os.Environ(), "HEALTHCHECK_TEST_PROCESS=1")
			output, err := cmd.CombinedOutput()
			code := 0
			if err != nil {
				var exitErr *exec.ExitError
				if !errors.As(err, &exitErr) {
					t.Fatal(err)
				}
				code = exitErr.ExitCode()
			}
			if code != tc.want {
				t.Fatalf("exit %d, want %d: %s", code, tc.want, output)
			}
		})
	}
}
