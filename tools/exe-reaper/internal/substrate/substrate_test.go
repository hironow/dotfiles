package substrate

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"errors"
	"math/big"
	"net"
	"os"
	"path/filepath"
	"slices"
	"strconv"
	"sync"
	"testing"
	"time"

	"github.com/agent-substrate/substrate/pkg/proto/ateapipb"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"

	"github.com/hironow/dotfiles/tools/exe-reaper/internal/lease"
)

// fakeControl is the Substrate Control API as L1 uses it: ListActors and
// ListActorTemplates, served page by page from fixed data. A real gRPC server
// on a real TLS listener, so the client's dial options, credentials and
// pagination run for real rather than being re-asserted.
type fakeControl struct {
	ateapipb.UnimplementedControlServer

	mu sync.Mutex
	// actorPages and templatePages are served in order: page i answers the
	// token strconv.Itoa(i) ("" for the first) and names i+1 as the next,
	// except the last, which names none.
	actorPages    [][]*ateapipb.Actor
	templatePages [][]*ateapipb.ActorTemplate
	// failPage makes the list fail at that page index (-1: never).
	failPage int
	// loopToken, when set, is handed back as every next token.
	loopToken string
	// seen records every request's atespace and bearer token.
	atespaces []string
	tokens    []string
}

func newFakeControl() *fakeControl { return &fakeControl{failPage: -1} }

func (f *fakeControl) record(ctx context.Context, atespace string) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.atespaces = append(f.atespaces, atespace)
	md, _ := metadata.FromIncomingContext(ctx)
	f.tokens = append(f.tokens, md.Get("authorization")...)
}

func (f *fakeControl) page(token string, pages int) (int, string, error) {
	i := 0
	if token != "" {
		n, err := strconv.Atoi(token)
		if err != nil || n < 0 || n >= pages {
			return 0, "", status.Errorf(codes.InvalidArgument, "bad page token %q", token)
		}
		i = n
	}
	if i == f.failPage {
		return 0, "", status.Error(codes.Unavailable, "the store went away")
	}
	next := ""
	if i+1 < pages {
		next = strconv.Itoa(i + 1)
	}
	if f.loopToken != "" {
		next = f.loopToken
	}
	return i, next, nil
}

func (f *fakeControl) ListActors(ctx context.Context, req *ateapipb.ListActorsRequest) (*ateapipb.ListActorsResponse, error) {
	f.record(ctx, req.GetAtespace())
	i, next, err := f.page(req.GetPageToken(), max(len(f.actorPages), 1))
	if err != nil {
		return nil, err
	}
	var actors []*ateapipb.Actor
	if i < len(f.actorPages) {
		actors = f.actorPages[i]
	}
	return &ateapipb.ListActorsResponse{Actors: actors, NextPageToken: next}, nil
}

func (f *fakeControl) ListActorTemplates(ctx context.Context, req *ateapipb.ListActorTemplatesRequest) (*ateapipb.ListActorTemplatesResponse, error) {
	f.record(ctx, req.GetAtespace())
	i, next, err := f.page(req.GetPageToken(), max(len(f.templatePages), 1))
	if err != nil {
		return nil, err
	}
	var templates []*ateapipb.ActorTemplate
	if i < len(f.templatePages) {
		templates = f.templatePages[i]
	}
	return &ateapipb.ListActorTemplatesResponse{ActorTemplates: templates, NextPageToken: next}, nil
}

// --- the fake's PKI -------------------------------------------------------------

// testCA is a throwaway certificate authority standing in for the servicedns
// trust bundle, and the serving certificate it signs for api.ate-system.svc.
type testCA struct {
	pemBytes []byte
	serving  tls.Certificate
}

func newTestCA(t *testing.T, serverName string) testCA {
	t.Helper()
	caKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	caTmpl := &x509.Certificate{
		SerialNumber:          big.NewInt(1),
		Subject:               pkix.Name{CommonName: "test servicedns CA"},
		NotBefore:             time.Now().Add(-time.Hour),
		NotAfter:              time.Now().Add(time.Hour),
		IsCA:                  true,
		KeyUsage:              x509.KeyUsageCertSign,
		BasicConstraintsValid: true,
	}
	caDER, err := x509.CreateCertificate(rand.Reader, caTmpl, caTmpl, &caKey.PublicKey, caKey)
	if err != nil {
		t.Fatal(err)
	}
	caCert, err := x509.ParseCertificate(caDER)
	if err != nil {
		t.Fatal(err)
	}
	leafKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	leafTmpl := &x509.Certificate{
		SerialNumber: big.NewInt(2),
		Subject:      pkix.Name{CommonName: serverName},
		DNSNames:     []string{serverName},
		NotBefore:    time.Now().Add(-time.Hour),
		NotAfter:     time.Now().Add(time.Hour),
		KeyUsage:     x509.KeyUsageDigitalSignature,
		ExtKeyUsage:  []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
	}
	leafDER, err := x509.CreateCertificate(rand.Reader, leafTmpl, caCert, &leafKey.PublicKey, caKey)
	if err != nil {
		t.Fatal(err)
	}
	return testCA{
		pemBytes: pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: caDER}),
		serving:  tls.Certificate{Certificate: [][]byte{leafDER}, PrivateKey: leafKey},
	}
}

// serve starts f on a TLS listener with ca's serving certificate and returns
// options that reach it: the trust bundle and a token file in a temp dir.
func serve(t *testing.T, f *fakeControl, ca testCA) Options {
	t.Helper()
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	srv := grpc.NewServer(grpc.Creds(credentials.NewServerTLSFromCert(&ca.serving)))
	ateapipb.RegisterControlServer(srv, f)
	go func() { _ = srv.Serve(lis) }()
	t.Cleanup(srv.Stop)

	dir := t.TempDir()
	caFile := filepath.Join(dir, "trust-bundle.pem")
	tokenFile := filepath.Join(dir, "token")
	if err := os.WriteFile(caFile, ca.pemBytes, 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(tokenFile, []byte("token-one\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	return Options{Target: lis.Addr().String(), ServerName: ServerName, TokenFile: tokenFile, CAFile: caFile}
}

func dial(t *testing.T, opts Options) *Client {
	t.Helper()
	c, err := Dial(opts)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = c.Close() })
	return c
}

// changedAt is the update_time every fixture actor carries.
var changedAt = time.Date(2026, 9, 20, 3, 4, 5, 0, time.UTC)

func actor(atespace, name, uid string, s ateapipb.ActorState, worker *ateapipb.WorkerAssignment) *ateapipb.Actor {
	return &ateapipb.Actor{
		Metadata: &ateapipb.ResourceMetadata{Atespace: atespace, Name: name, Uid: uid, UpdateTime: timestamppb.New(changedAt)},
		Status:   &ateapipb.ActorStatus{State: s, WorkerAssignment: worker},
	}
}

func onWorker(pod, uid string) *ateapipb.WorkerAssignment {
	return &ateapipb.WorkerAssignment{WorkerNamespace: "exe", WorkerPool: "exe-gvisor", WorkerPod: pod, WorkerPodUid: uid}
}

// --- tests ------------------------------------------------------------------------

func TestActorsReadsEveryPageOfEveryAtespaceAndClassifiesEachActor(t *testing.T) {
	// given three pages, the middle one empty but not the last -- the API
	// allows it ("This list may be empty even if there are more results")
	f := newFakeControl()
	f.actorPages = [][]*ateapipb.Actor{
		{
			actor("exe", "p1", "u1", ateapipb.ActorState_ACTOR_STATE_RUNNING, onWorker("w-a", "pa")),
			actor("exe", "p2", "u2", ateapipb.ActorState_ACTOR_STATE_SUSPENDED, nil),
		},
		{},
		{
			actor("exe", "p3", "u3", ateapipb.ActorState_ACTOR_STATE_DELETING, onWorker("w-b", "pb")),
			actor("ate-golden", "g1", "u4", ateapipb.ActorState_ACTOR_STATE_RESUMING, onWorker("w-a", "pa")),
		},
	}
	c := dial(t, serve(t, f, newTestCA(t, ServerName)))

	// when
	got, err := c.Actors(context.Background())
	// then every actor of every page, in every atespace, as L1 sees it
	if err != nil {
		t.Fatal(err)
	}
	want := []lease.ActorObs{
		{UID: "u1", State: lease.ActorAwake, Task: "exe/p1", Worker: "exe/w-a/pa", ChangedAt: changedAt},
		{UID: "u2", State: lease.ActorAtRest, Task: "exe/p2", ChangedAt: changedAt},
		{UID: "u3", State: lease.ActorDeleting, Task: "exe/p3", Worker: "exe/w-b/pb", ChangedAt: changedAt},
		{UID: "u4", State: lease.ActorAwake, Golden: true, Worker: "exe/w-a/pa", ChangedAt: changedAt},
	}
	if !slices.Equal(got, want) {
		t.Errorf("actors:\n got %+v\nwant %+v", got, want)
	}
	// and it asked across all atespaces at once, not one at a time
	for _, a := range f.atespaces {
		if a != "" {
			t.Errorf("listed atespace %q; L1 lists every atespace in one scan", a)
		}
	}
}

func TestEveryStoreStateHasOneMeaning(t *testing.T) {
	// The map from the store's states to L1's: PAUSED counts as awake, because
	// its sandbox is node-local state a stopped node loses (plan F2).
	want := map[ateapipb.ActorState]lease.ActorState{
		ateapipb.ActorState_ACTOR_STATE_RESUMING:   lease.ActorAwake,
		ateapipb.ActorState_ACTOR_STATE_RUNNING:    lease.ActorAwake,
		ateapipb.ActorState_ACTOR_STATE_PAUSING:    lease.ActorAwake,
		ateapipb.ActorState_ACTOR_STATE_PAUSED:     lease.ActorAwake,
		ateapipb.ActorState_ACTOR_STATE_SUSPENDING: lease.ActorCheckpointing,
		ateapipb.ActorState_ACTOR_STATE_SUSPENDED:  lease.ActorAtRest,
		ateapipb.ActorState_ACTOR_STATE_CRASHED:    lease.ActorCrashed,
		ateapipb.ActorState_ACTOR_STATE_DELETING:   lease.ActorDeleting,
	}
	for s, w := range want {
		got, err := classify(s)
		if err != nil || got != w {
			t.Errorf("%s: got %q (%v), want %q", s, got, err, w)
		}
	}
	// and every state the enum has is one of them, or refused
	for n := range ateapipb.ActorState_name {
		s := ateapipb.ActorState(n)
		if _, known := want[s]; known {
			continue
		}
		if _, err := classify(s); err == nil {
			t.Errorf("%s: classified, but L1 has no meaning for it", s)
		}
	}
}

func TestAnActorInAStateL1CannotClassifyIsAFailedRead(t *testing.T) {
	// A row L1 cannot classify is a row it might count wrong. A failed read
	// decides nothing that tick (plan D5); guessing could call a drain done.
	f := newFakeControl()
	f.actorPages = [][]*ateapipb.Actor{{actor("exe", "p1", "u1", ateapipb.ActorState(42), nil)}}
	c := dial(t, serve(t, f, newTestCA(t, ServerName)))

	if got, err := c.Actors(context.Background()); err == nil {
		t.Errorf("read %+v from a store state L1 cannot classify; want an error", got)
	}
}

func TestAListThatFailsPartwayIsAFailedRead(t *testing.T) {
	// A partial list would let a drain finish without seeing the rest.
	f := newFakeControl()
	f.actorPages = [][]*ateapipb.Actor{
		{actor("exe", "p1", "u1", ateapipb.ActorState_ACTOR_STATE_SUSPENDED, nil)},
		{actor("exe", "p2", "u2", ateapipb.ActorState_ACTOR_STATE_RUNNING, nil)},
	}
	f.failPage = 1
	c := dial(t, serve(t, f, newTestCA(t, ServerName)))

	if got, err := c.Actors(context.Background()); err == nil {
		t.Errorf("read %+v when the second page failed; want an error", got)
	}
}

func TestAPageTokenThatComesBackIsAFailedRead(t *testing.T) {
	// A server that hands back a token it already gave would keep the tick
	// reading forever; it is a failed read instead.
	f := newFakeControl()
	f.actorPages = [][]*ateapipb.Actor{{}, {}}
	f.loopToken = "1"
	c := dial(t, serve(t, f, newTestCA(t, ServerName)))

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if _, err := c.Actors(ctx); err == nil || errors.Is(err, context.DeadlineExceeded) {
		t.Errorf("err = %v; want a failed read that names the repeated token, before any deadline", err)
	}
}

func TestTemplatesPending(t *testing.T) {
	// The template reconciler's own rule (goldenSnapshotDone): a template is
	// done when its golden snapshot is written or has failed, and any other is
	// one Substrate may still resume a golden actor for.
	written := &ateapipb.ActorTemplate{Status: &ateapipb.ActorTemplateStatus{GoldenSnapshotStatus: &ateapipb.GoldenSnapshotStatus{
		GoldenSnapshot: &ateapipb.ExternalSnapshot{SnapshotUri: "gs://b/golden"},
	}}}
	failed := &ateapipb.ActorTemplate{Status: &ateapipb.ActorTemplateStatus{GoldenSnapshotStatus: &ateapipb.GoldenSnapshotStatus{
		ErrorMessage: "boot failed",
	}}}
	inFlight := &ateapipb.ActorTemplate{Status: &ateapipb.ActorTemplateStatus{GoldenSnapshotStatus: &ateapipb.GoldenSnapshotStatus{}}}
	noStatus := &ateapipb.ActorTemplate{}

	tests := []struct {
		name  string
		pages [][]*ateapipb.ActorTemplate
		want  bool
	}{
		{"no templates at all", nil, false},
		{"every template written or failed", [][]*ateapipb.ActorTemplate{{written, failed}}, false},
		{"one still in flight", [][]*ateapipb.ActorTemplate{{written, inFlight}}, true},
		{"one with no status yet", [][]*ateapipb.ActorTemplate{{noStatus}}, true},
		{"in flight on a later page", [][]*ateapipb.ActorTemplate{{written}, {}, {inFlight}}, true},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			f := newFakeControl()
			f.templatePages = tc.pages
			c := dial(t, serve(t, f, newTestCA(t, ServerName)))

			got, err := c.TemplatesPending(context.Background())
			if err != nil {
				t.Fatal(err)
			}
			if got != tc.want {
				t.Errorf("pending = %t, want %t", got, tc.want)
			}
		})
	}
}

func TestEveryCallCarriesTheCurrentToken(t *testing.T) {
	// The kubelet rotates a projected token in place, so the client reads the
	// file on every call instead of once at dial time.
	f := newFakeControl()
	opts := serve(t, f, newTestCA(t, ServerName))
	c := dial(t, opts)

	if _, err := c.Actors(context.Background()); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(opts.TokenFile, []byte("token-two"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := c.Actors(context.Background()); err != nil {
		t.Fatal(err)
	}
	if want := []string{"Bearer token-one", "Bearer token-two"}; !slices.Equal(f.tokens, want) {
		t.Errorf("tokens %q, want %q", f.tokens, want)
	}
}

func TestTheClientRefusesAServerItCannotVerify(t *testing.T) {
	// A server whose certificate does not chain to the trust bundle -- or
	// names another host -- is not the Control API, and L1 must not tell it
	// anything, least of all its token.
	f := newFakeControl()
	opts := serve(t, f, newTestCA(t, ServerName))
	other := newTestCA(t, ServerName)
	if err := os.WriteFile(opts.CAFile, other.pemBytes, 0o600); err != nil {
		t.Fatal(err)
	}
	c := dial(t, opts)
	if _, err := c.Actors(context.Background()); err == nil {
		t.Error("a server signed by another CA was trusted")
	}

	f2 := newFakeControl()
	misnamed := serve(t, f2, newTestCA(t, "api.elsewhere.svc"))
	if _, err := dial(t, misnamed).Actors(context.Background()); err == nil {
		t.Error("a certificate for another name was trusted")
	}
	if len(f.tokens)+len(f2.tokens) != 0 {
		t.Errorf("a token reached an unverified server: %q %q", f.tokens, f2.tokens)
	}
}
