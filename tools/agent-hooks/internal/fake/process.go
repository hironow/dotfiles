package fake

import "sync"

// ProcessLifetime records signals and reaping around an unreaped exit.
type ProcessLifetime struct {
	Exit       chan error
	ExitOnKill bool
	KillError  error
	once       sync.Once
	mu         sync.Mutex
	events     []string
}

func (p *ProcessLifetime) record(event string) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.events = append(p.events, event)
}

func (p *ProcessLifetime) WaitExit() error {
	err := <-p.Exit
	p.record("exit")
	return err
}

func (p *ProcessLifetime) KillGroup() error {
	p.record("kill")
	if p.ExitOnKill {
		p.once.Do(func() { p.Exit <- nil })
	}
	return p.KillError
}

func (p *ProcessLifetime) Reap() error {
	p.record("reap")
	return nil
}

func (p *ProcessLifetime) Events() []string {
	p.mu.Lock()
	defer p.mu.Unlock()
	return append([]string(nil), p.events...)
}
