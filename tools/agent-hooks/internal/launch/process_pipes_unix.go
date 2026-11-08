//go:build !windows

package launch

import (
	"bytes"
	"io"
	"os"
	"os/exec"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/process"
)

type outputPipe struct {
	reader, writer *os.File
	output         bytes.Buffer
	done           chan struct{}
}

// commandPipes serves the pipes itself, so exec never reaps before cleanup.
type commandPipes struct {
	outputs                  []*outputPipe
	stdinReader, stdinWriter *os.File
	stdinDone                chan struct{}
}

func (p *commandPipes) addOutput() (*os.File, error) {
	reader, writer, err := os.Pipe()
	if err != nil {
		return nil, err
	}
	p.outputs = append(p.outputs, &outputPipe{reader: reader, writer: writer, done: make(chan struct{})})
	return writer, nil
}

func openCommandPipes(cmd *exec.Cmd, command process.Command) (*commandPipes, error) {
	p := &commandPipes{}
	stdout, err := p.addOutput()
	if err != nil {
		return nil, err
	}
	cmd.Stdout, cmd.Stderr = stdout, stdout
	if !command.Combined {
		cmd.Stderr, err = p.addOutput()
	}
	if err == nil && command.Stdin != nil {
		p.stdinReader, p.stdinWriter, err = os.Pipe()
		cmd.Stdin = p.stdinReader
	}
	if err != nil {
		p.close()
		return nil, err
	}
	return p, nil
}

func (p *commandPipes) serve(stdin []byte) <-chan struct{} {
	for _, pipe := range p.outputs {
		_ = pipe.writer.Close()
		go func() {
			defer close(pipe.done)
			_, _ = io.Copy(&pipe.output, pipe.reader)
		}()
	}
	if p.stdinReader != nil {
		_ = p.stdinReader.Close()
		p.stdinDone = make(chan struct{})
		go func() {
			defer close(p.stdinDone)
			defer p.stdinWriter.Close()
			_, _ = p.stdinWriter.Write(stdin)
		}()
	}
	drained := make(chan struct{})
	go func() {
		defer close(drained)
		for _, pipe := range p.outputs {
			<-pipe.done
		}
	}()
	return drained
}

func (p *commandPipes) close() {
	for _, pipe := range p.outputs {
		_ = pipe.reader.Close()
		_ = pipe.writer.Close()
	}
	if p.stdinReader != nil {
		_ = p.stdinReader.Close()
		_ = p.stdinWriter.Close()
	}
}

func (p *commandPipes) result() process.Result {
	result := process.Result{Stdout: p.outputs[0].output.Bytes()}
	if len(p.outputs) > 1 {
		result.Stderr = p.outputs[1].output.Bytes()
	}
	return result
}
