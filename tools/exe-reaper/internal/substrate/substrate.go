// Package substrate is L1's view of the Agent Substrate Control API: every
// actor in every atespace, classified the way the drain needs, and whether any
// ActorTemplate's golden snapshot is still in flight.
//
// It speaks the API through the stubs of the pinned release
// (github.com/agent-substrate/substrate, held to exe/versions.json by
// scripts/check_exe_pins.py), exactly as the ax-controller does: TLS to
// api.ate-system.svc against the servicedns trust bundle, and a projected
// service-account token for that audience on every call. The API
// authenticates but does not authorize (plan F1), so this package only ever
// reads.
//
// A read is all or nothing. Every list is followed to its last page, and a
// page that fails, a token the server already gave, or a row whose state L1
// cannot classify fails the whole read: that tick decides nothing (plan D5).
// A partial list is how a drain would finish without seeing an awake actor.
package substrate

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"fmt"
	"os"
	"strings"

	"github.com/agent-substrate/substrate/pkg/proto/ateapipb"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"

	"github.com/hironow/dotfiles/tools/exe-reaper/internal/lease"
)

const (
	// ServerName is the name on the Control API's serving certificate and the
	// :authority every call carries. The token's audience is the same name.
	ServerName = "api.ate-system.svc"

	// GoldenAtespace is where Substrate's template reconciler keeps the actors
	// it boots to take golden snapshots. They are Substrate's work, not a
	// task's: L1 waits for them and never suspends one.
	GoldenAtespace = "ate-golden"

	// pageSize asks for pages as large as the server allows (it coerces
	// anything above 1000).
	pageSize = 1000

	// maxPages bounds one scan. At pageSize rows a page, it is far beyond any
	// store this cluster can hold; a scan that reaches it is a server that
	// keeps inventing tokens.
	maxPages = 1000
)

// Options says where the Control API is and how L1 proves who it is.
type Options struct {
	// Target is the dial address, host:port.
	Target string
	// ServerName is the name the server's certificate must carry. Normally
	// the package's ServerName.
	ServerName string
	// TokenFile holds the projected service-account token. It is read on
	// every call, because the kubelet rotates it in place.
	TokenFile string
	// CAFile is the trust bundle the server's certificate must chain to.
	CAFile string
}

// Client is a connection to the Control API.
type Client struct {
	conn    *grpc.ClientConn
	control ateapipb.ControlClient
}

// Dial prepares a client. Like grpc.NewClient it does not connect: the first
// call does, and fails if the server cannot be verified.
func Dial(o Options) (*Client, error) {
	bundle, err := os.ReadFile(o.CAFile)
	if err != nil {
		return nil, fmt.Errorf("reading the Control API's trust bundle: %w", err)
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(bundle) {
		return nil, fmt.Errorf("%s holds no PEM certificate", o.CAFile)
	}
	tlsConfig := &tls.Config{
		ServerName: o.ServerName,
		RootCAs:    roots,
		MinVersion: tls.VersionTLS12,
	}
	conn, err := grpc.NewClient(o.Target,
		grpc.WithTransportCredentials(credentials.NewTLS(tlsConfig)),
		grpc.WithAuthority(o.ServerName),
		grpc.WithPerRPCCredentials(tokenFile(o.TokenFile)),
	)
	if err != nil {
		return nil, fmt.Errorf("preparing a client for the Control API at %s: %w", o.Target, err)
	}
	return &Client{conn: conn, control: ateapipb.NewControlClient(conn)}, nil
}

// Close releases the connection.
func (c *Client) Close() error { return c.conn.Close() }

// tokenFile is a bearer token read from a file on every call.
type tokenFile string

func (t tokenFile) GetRequestMetadata(context.Context, ...string) (map[string]string, error) {
	b, err := os.ReadFile(string(t))
	if err != nil {
		return nil, fmt.Errorf("reading the Control API token: %w", err)
	}
	return map[string]string{"authorization": "Bearer " + strings.TrimSpace(string(b))}, nil
}

// RequireTransportSecurity keeps the token off any connection that is not TLS.
func (tokenFile) RequireTransportSecurity() bool { return true }

// Actors is every actor in every atespace, as L1 classifies it.
//
//	Task    "<atespace>/<name>": AX names a task's actor after the task, in
//	        the task's atespace. Empty for a golden actor.
//	Worker  "<namespace>/<pod>/<pod uid>" of the worker hosting it, or empty.
//	        The UID is what lets a wedge's pod be deleted only if it is still
//	        the pod the store names, never a replacement that reused its name.
func (c *Client) Actors(ctx context.Context) ([]lease.ActorObs, error) {
	var out []lease.ActorObs
	err := scan(ctx, func(ctx context.Context, token string) (string, error) {
		resp, err := c.control.ListActors(ctx, &ateapipb.ListActorsRequest{PageSize: pageSize, PageToken: token})
		if err != nil {
			return "", err
		}
		for _, a := range resp.GetActors() {
			obs, err := observe(a)
			if err != nil {
				return "", err
			}
			out = append(out, obs)
		}
		return resp.GetNextPageToken(), nil
	})
	if err != nil {
		return nil, fmt.Errorf("listing actors: %w", err)
	}
	return out, nil
}

// TemplatesPending reports whether any ActorTemplate, in any atespace, has a
// golden snapshot neither written nor failed: the template reconciler's own
// test (goldenSnapshotDone), and so exactly the templates it may still resume
// a golden actor for.
func (c *Client) TemplatesPending(ctx context.Context) (bool, error) {
	pending := false
	err := scan(ctx, func(ctx context.Context, token string) (string, error) {
		resp, err := c.control.ListActorTemplates(ctx, &ateapipb.ListActorTemplatesRequest{PageSize: pageSize, PageToken: token})
		if err != nil {
			return "", err
		}
		for _, t := range resp.GetActorTemplates() {
			s := t.GetStatus().GetGoldenSnapshotStatus()
			if s.GetGoldenSnapshot().GetSnapshotUri() == "" && s.GetErrorMessage() == "" {
				pending = true
			}
		}
		return resp.GetNextPageToken(), nil
	})
	if err != nil {
		return false, fmt.Errorf("listing actor templates: %w", err)
	}
	return pending, nil
}

// errRepeatedToken is a server that hands back a page token it already gave.
var errRepeatedToken = errors.New("the server repeated a page token")

// scan follows a paginated list to its end. An empty page may still carry a
// token ("This list may be empty even if there are more results"), so only an
// empty token ends it.
func scan(ctx context.Context, page func(ctx context.Context, token string) (string, error)) error {
	seen := map[string]bool{}
	token := ""
	for range maxPages {
		next, err := page(ctx, token)
		if err != nil {
			return err
		}
		if next == "" {
			return nil
		}
		if seen[next] {
			return fmt.Errorf("%w: %q", errRepeatedToken, next)
		}
		seen[next] = true
		token = next
	}
	return fmt.Errorf("still paging after %d pages", maxPages)
}

// observe is one actor as L1 sees it.
func observe(a *ateapipb.Actor) (lease.ActorObs, error) {
	md := a.GetMetadata()
	state, err := classify(a.GetStatus().GetState())
	if err != nil {
		return lease.ActorObs{}, fmt.Errorf("actor %s/%s: %w", md.GetAtespace(), md.GetName(), err)
	}
	obs := lease.ActorObs{UID: md.GetUid(), State: state}
	if md.GetUpdateTime() != nil {
		obs.ChangedAt = md.GetUpdateTime().AsTime()
	}
	if md.GetAtespace() == GoldenAtespace {
		obs.Golden = true
	} else {
		obs.Task = md.GetAtespace() + "/" + md.GetName()
	}
	if w := a.GetStatus().GetWorkerAssignment(); w.GetWorkerPod() != "" {
		obs.Worker = w.GetWorkerNamespace() + "/" + w.GetWorkerPod() + "/" + w.GetWorkerPodUid()
	}
	return obs, nil
}

// errUnclassifiable is a store state L1 has no meaning for.
var errUnclassifiable = errors.New("a state L1 cannot classify")

// classify maps the store's states onto L1's (lease.ActorState documents the
// table). PAUSED counts as awake: its sandbox is node-local state that a
// stopped node loses (plan F2).
func classify(s ateapipb.ActorState) (lease.ActorState, error) {
	switch s {
	case ateapipb.ActorState_ACTOR_STATE_RESUMING,
		ateapipb.ActorState_ACTOR_STATE_RUNNING,
		ateapipb.ActorState_ACTOR_STATE_PAUSING,
		ateapipb.ActorState_ACTOR_STATE_PAUSED:
		return lease.ActorAwake, nil
	case ateapipb.ActorState_ACTOR_STATE_SUSPENDING:
		return lease.ActorCheckpointing, nil
	case ateapipb.ActorState_ACTOR_STATE_SUSPENDED:
		return lease.ActorAtRest, nil
	case ateapipb.ActorState_ACTOR_STATE_CRASHED:
		return lease.ActorCrashed, nil
	case ateapipb.ActorState_ACTOR_STATE_DELETING:
		return lease.ActorDeleting, nil
	default:
		return "", fmt.Errorf("%w: %s", errUnclassifiable, s)
	}
}
