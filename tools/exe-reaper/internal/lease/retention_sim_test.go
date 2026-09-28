package lease

import (
	"fmt"
	"math/rand/v2"
	"os"
	"slices"
	"strconv"
	"strings"
	"testing"
	"time"
)

// The seeded simulation of DecideRetention against exe/spec/retention.qnt's
// environment: the operator and ax-job create, suspend, resume, delete and keep
// tasks while the node wakes and sleeps, days pass, and Artifact Registry's
// cleanup collects any untagged version older than retentionARDeleteDays at any
// moment. L1's ticks run the real DecideRetention and apply what it decides.
// After every step the model's three invariants are checked on the Go state.
//
// A failure prints the seed; EXE_REAPER_RETENTION_SEED=<seed> replays it.

// retentionARDeleteDays is exe-task's cleanup policy (DELETE older than 14
// days; tofu/exe-platform/artifact_registry.tf). As in the model, no invariant
// depends on it, and the policy's "keep the 2 most recent" is left out so the
// simulation collects at least as much as AR does.
const retentionARDeleteDays = 14

// retentionSeeds is fixed, like the drain simulation's: a gate that cannot
// fail the same way twice is not a gate. The sweep is cheap (milliseconds per
// seed), so it is wide.
var retentionSeeds = func() []uint64 {
	seeds := make([]uint64, 200)
	for i := range seeds {
		seeds[i] = uint64(i) + 1
	}
	return seeds
}()

const (
	retentionSteps   = 2000
	retentionTasks   = 3
	retentionDigests = 3
	retentionPackage = "exe-task/task"
)

// retentionWeights: how often each kind of step is drawn. Days pass often
// enough for a 30-day TTL to run out inside one run, and L1 ticks often, as
// it does (every minute while a node is up).
var retentionWeights = []struct {
	kind   int
	weight int
}{
	{stepPush, 1},
	{stepAxJobTag, 2},
	{stepAxJobApply, 2},
	{stepRawApply, 1},
	{stepSuspend, 2},
	{stepResume, 1},
	{stepDelete, 1},
	{stepKeep, 1},
	{stepWakeOrSleep, 1},
	{stepDay, 5},
	{stepARCleanup, 1},
	{stepL1Tick, 4},
	{stepBackgroundWrite, 1},
}

const (
	stepPush = iota
	stepAxJobTag
	stepAxJobApply
	stepRawApply
	stepSuspend
	stepResume
	stepDelete
	stepKeep
	stepWakeOrSleep
	stepDay
	stepARCleanup
	stepL1Tick
	stepBackgroundWrite
)

func (w *retWorld) draw() int {
	total := 0
	for _, x := range retentionWeights {
		total += x.weight
	}
	n := w.rng.IntN(total)
	for _, x := range retentionWeights {
		if n < x.weight {
			return x.kind
		}
		n -= x.weight
	}
	return stepDay
}

type retTask struct {
	alive, suspended, protected bool
	digest                      string
	changedAt                   time.Time
	suspendedAt                 time.Time
}

type retWorld struct {
	rng   *rand.Rand
	epoch time.Time
	day   int
	awake bool

	tasks    map[string]*retTask
	pushedAt map[string]int
	gone     map[string]bool
	tags     map[string]Tag // by tag name; names are unique per package
	keep     map[string]bool
	pending  map[string]string // ax-job between its tag and its apply
	record   TasksRecord

	// sharedJobTag is retention.qnt's rejected design: ax-job tags the shared
	// inuse-<sha12>.
	sharedJobTag bool
	// backgroundWrites is its backgroundWriteRefreshes: something rewrites a
	// suspended actor's row now and then, moving its update_time.
	backgroundWrites bool

	trace []string
	stats retStats
}

type retStats struct {
	ttlDeletes, released, collected, jobTags, ticks int
}

func (w *retWorld) now() time.Time { return w.epoch.Add(time.Duration(w.day) * 24 * time.Hour) }

func (w *retWorld) note(format string, args ...any) {
	w.trace = append(w.trace, fmt.Sprintf("day %d: ", w.day)+fmt.Sprintf(format, args...))
}

func retDigest(i int) string {
	return "sha256:" + strings.Repeat(strconv.Itoa(i), 12) + strings.Repeat("0", 52)
}

func (w *retWorld) available(digest string) bool {
	_, pushed := w.pushedAt[digest]
	return pushed && !w.gone[digest]
}

func (w *retWorld) tagged(digest string) bool {
	for _, t := range w.tags {
		if t.Image.Digest == digest {
			return true
		}
	}
	return false
}

func (w *retWorld) liveTask(key string) (*retTask, bool) {
	t, ok := w.tasks[key]
	return t, ok && t.alive
}

// step takes one random environment action or L1 tick. It returns a violation
// message, or "".
func (w *retWorld) step() string {
	key := fmt.Sprintf("exe/t%d", w.rng.IntN(retentionTasks)+1)
	digest := retDigest(w.rng.IntN(retentionDigests) + 1)
	switch kind := w.draw(); kind {
	case stepPush:
		w.push(digest)
	case stepAxJobTag:
		w.axJobTag(key, digest)
	case stepAxJobApply:
		w.axJobApply(key)
	case stepRawApply:
		w.rawApply(key, digest)
	case stepSuspend, stepResume, stepDelete, stepBackgroundWrite:
		w.operate(kind, key)
	case stepKeep:
		w.keep[key] = !w.keep[key]
		w.note("keep %s = %t", key, w.keep[key])
	case stepWakeOrSleep:
		w.wakeOrSleep()
	case stepDay:
		w.day++
		w.pending = map[string]string{}
	case stepARCleanup:
		return w.arCleanup()
	case stepL1Tick:
		return w.l1Tick()
	}
	return ""
}

func (w *retWorld) push(digest string) {
	if _, pushed := w.pushedAt[digest]; !pushed {
		w.pushedAt[digest] = w.day
		w.note("push %s", digest[7:13])
	}
}

func (w *retWorld) rawApply(key, digest string) {
	if _, exists := w.tasks[key]; w.awake && !exists && w.pending[key] == "" && w.available(digest) {
		w.tasks[key] = &retTask{alive: true, digest: digest, changedAt: w.now()}
		w.note("raw apply %s on %s", key, digest[7:13])
	}
}

// operate is what the operator, AX, or a background writer does to one live
// task, with a node up.
func (w *retWorld) operate(kind int, key string) {
	t, ok := w.liveTask(key)
	if !ok || !w.awake {
		return
	}
	switch {
	case kind == stepSuspend && !t.suspended:
		t.suspended, t.changedAt, t.suspendedAt = true, w.now(), w.now()
		w.note("suspend %s", key)
	case kind == stepResume && t.suspended && w.available(t.digest):
		t.suspended, t.changedAt = false, w.now()
		w.note("resume %s", key)
	case kind == stepDelete:
		t.alive = false
		w.note("operator deletes %s", key)
	case kind == stepBackgroundWrite && w.backgroundWrites && t.suspended:
		t.changedAt = w.now()
		w.note("background write to %s", key)
	}
}

func (w *retWorld) axJobTag(key, digest string) {
	if _, exists := w.tasks[key]; !w.awake || exists || w.pending[key] != "" || !w.available(digest) {
		return
	}
	name := JobTagName(digest, w.now())
	if w.sharedJobTag {
		name = L1TagName(digest)
	}
	w.tags[name] = Tag{Name: name, Image: Image{Package: retentionPackage, Digest: digest}}
	w.pending[key] = digest
	w.stats.jobTags++
	w.note("ax-job tags %s as %s for %s", digest[7:13], name, key)
}

func (w *retWorld) axJobApply(key string) {
	digest := w.pending[key]
	if !w.awake || digest == "" {
		return
	}
	delete(w.pending, key)
	if !w.available(digest) {
		w.note("ax-job for %s finds its image gone and creates nothing", key)
		return
	}
	w.tasks[key] = &retTask{alive: true, protected: true, digest: digest, changedAt: w.now()}
	w.note("ax-job applies %s", key)
}

func (w *retWorld) wakeOrSleep() {
	if !w.awake {
		w.awake = true
		w.note("wake")
		return
	}
	// The drain suspends everything live, then the node goes.
	for _, t := range w.tasks {
		if t.alive && !t.suspended {
			t.suspended, t.changedAt, t.suspendedAt = true, w.now(), w.now()
		}
	}
	w.awake = false
	w.pending = map[string]string{}
	w.note("sleep")
}

func (w *retWorld) arCleanup() string {
	var doomed []string
	for digest, pushed := range w.pushedAt {
		if !w.gone[digest] && !w.tagged(digest) && w.day-pushed >= retentionARDeleteDays {
			doomed = append(doomed, digest)
		}
	}
	slices.Sort(doomed)
	for _, digest := range doomed {
		w.gone[digest] = true
		w.stats.collected++
		w.note("AR collects %s", digest[7:13])
		for key, t := range w.tasks {
			if t.alive && t.protected && t.digest == digest {
				return fmt.Sprintf("NoLiveImageCollected: AR collected %s, the image of protected live task %s", digest[7:13], key)
			}
		}
	}
	return ""
}

func (w *retWorld) l1Tick() string {
	if !w.awake {
		return ""
	}
	o := RetentionObservation{Now: w.now(), Record: w.record}
	for key, t := range w.tasks {
		if t.alive {
			o.Tasks = append(o.Tasks, TaskObs{
				Key: key, Suspended: t.suspended, ChangedAt: t.changedAt,
				Image: Image{Package: retentionPackage, Digest: t.digest},
			})
		}
	}
	for key, kept := range w.keep {
		if kept {
			o.Keep = append(o.Keep, key)
		}
	}
	for _, t := range w.tags {
		o.Tags = append(o.Tags, t)
	}
	// Go map order is random: sort, so a seed replays.
	slices.SortFunc(o.Tasks, func(a, b TaskObs) int { return strings.Compare(a.Key, b.Key) })
	slices.Sort(o.Keep)
	slices.SortFunc(o.Tags, func(a, b Tag) int { return strings.Compare(a.Name, b.Name) })

	d := DecideRetention(o)
	w.stats.ticks++
	// The liveness half (TtlNeverMissed): a task SUSPENDED and untouched for
	// the TTL, and not kept, is deleted by this tick.
	for key, t := range w.tasks {
		if t.alive && t.suspended && !w.keep[key] && !w.now().Before(t.suspendedAt.Add(TaskTTL)) && !slices.Contains(d.Delete, key) {
			return fmt.Sprintf("TtlNeverMissed: %s has been suspended since %s and is not kept, and the tick on day %d left it",
				key, t.suspendedAt.Format(time.DateOnly), w.day)
		}
	}
	for _, key := range d.Delete {
		t := w.tasks[key]
		if !t.suspended || w.keep[key] || w.now().Before(t.suspendedAt.Add(TaskTTL)) {
			return fmt.Sprintf("TtlDeletesOnlyTheExpired: L1 deleted %s, suspended since %s, kept=%t, on day %d",
				key, t.suspendedAt.Format(time.DateOnly), w.keep[key], w.day)
		}
		t.alive = false
		w.stats.ttlDeletes++
		w.note("L1 deletes %s (TTL)", key)
	}
	for _, img := range d.Tag {
		name := L1TagName(img.Digest)
		w.tags[name] = Tag{Name: name, Image: img}
	}
	for _, tag := range d.Untag {
		delete(w.tags, tag.Name)
		w.stats.released++
		w.note("L1 releases %s", tag.Name)
	}
	for _, t := range w.tasks {
		if t.alive {
			t.protected = true
		}
	}
	w.record = d.Record
	return ""
}

// protectedImagesAreTagged is the model's state invariant, on the Go state.
func (w *retWorld) protectedImagesAreTagged() string {
	for key, t := range w.tasks {
		if t.alive && t.protected && !w.tagged(t.digest) {
			return fmt.Sprintf("ProtectedImagesAreTagged: live task %s's image %s carries no tag", key, t.digest[7:13])
		}
	}
	return ""
}

// retentionVariant switches one of retention.qnt's rejected designs into the
// simulated world.
type retentionVariant int

const (
	decidedRetention retentionVariant = iota
	withSharedJobTag
	withBackgroundWrites
)

func runRetention(seed uint64, variant retentionVariant) (retStats, string, []string) {
	w := &retWorld{
		rng:              rand.New(rand.NewPCG(seed, seed^0x5eed)),
		epoch:            time.Date(2026, 9, 1, 0, 0, 0, 0, time.UTC),
		tasks:            map[string]*retTask{},
		pushedAt:         map[string]int{},
		gone:             map[string]bool{},
		tags:             map[string]Tag{},
		keep:             map[string]bool{},
		pending:          map[string]string{},
		sharedJobTag:     variant == withSharedJobTag,
		backgroundWrites: variant == withBackgroundWrites,
	}
	for range retentionSteps {
		if v := w.step(); v != "" {
			return w.stats, v, w.trace
		}
		if v := w.protectedImagesAreTagged(); v != "" {
			return w.stats, v, w.trace
		}
	}
	return w.stats, "", w.trace
}

func TestSimulationRetentionHoldsTheInvariants(t *testing.T) {
	seeds := retentionSeeds
	if raw := os.Getenv("EXE_REAPER_RETENTION_SEED"); raw != "" {
		seed, err := strconv.ParseUint(raw, 10, 64)
		if err != nil {
			t.Fatalf("EXE_REAPER_RETENTION_SEED=%q: %v", raw, err)
		}
		seeds = []uint64{seed}
	}
	var total retStats
	for _, seed := range seeds {
		stats, violation, trace := runRetention(seed, decidedRetention)
		if violation != "" {
			t.Fatalf("seed %d: %s\nreplay: EXE_REAPER_RETENTION_SEED=%d\nlast steps:\n  %s",
				seed, violation, seed, strings.Join(trace[max(0, len(trace)-15):], "\n  "))
		}
		total.ttlDeletes += stats.ttlDeletes
		total.released += stats.released
		total.collected += stats.collected
		total.jobTags += stats.jobTags
		total.ticks += stats.ticks
	}
	// Coverage: a sweep that never deleted, released or collected would pass
	// vacuously.
	if len(seeds) > 1 && (total.ttlDeletes == 0 || total.released == 0 || total.collected == 0 || total.jobTags == 0) {
		t.Errorf("the sweep never reached the states that matter: %+v", total)
	}
	t.Logf("retention sweep: %+v", total)
}

func TestSimulationRetentionIsDeterministic(t *testing.T) {
	a, va, ta := runRetention(42, decidedRetention)
	b, vb, tb := runRetention(42, decidedRetention)
	if a != b || va != vb || !slices.Equal(ta, tb) {
		t.Error("the same seed ran two different ways")
	}
}

func TestSimulationRetentionCatchesASharedJobTag(t *testing.T) {
	// The teeth: with retention.qnt's rejected design wired in, the same
	// sweep must find its violation.
	for _, seed := range retentionSeeds {
		if _, violation, _ := runRetention(seed, withSharedJobTag); violation != "" {
			t.Logf("seed %d: %s", seed, violation)
			return
		}
	}
	t.Error("no seed found a violation with ax-job tagging the shared inuse-<sha12>: the simulation has no teeth")
}

func TestSimulationRetentionCatchesABackgroundWriter(t *testing.T) {
	// The liveness half's teeth: with something rewriting suspended actors,
	// update_time never ages, and the sweep must see a TTL that did not fire.
	for _, seed := range retentionSeeds {
		if _, violation, _ := runRetention(seed, withBackgroundWrites); strings.HasPrefix(violation, "TtlNeverMissed") {
			t.Logf("seed %d: %s", seed, violation)
			return
		}
	}
	t.Error("no seed found a missed TTL with background writes: the liveness check has no teeth")
}
