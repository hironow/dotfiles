// Command writerender records agent-hook render's public command corpus.
package main

import (
	"fmt"
	"os"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/rendercorpus"
)

func main() {
	if err := writeCorpus(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func writeCorpus() error {
	corpus, err := rendercorpus.Generate()
	if err != nil {
		return err
	}
	module, err := os.OpenRoot(".")
	if err != nil {
		return err
	}
	defer module.Close()
	return module.WriteFile("internal/rendercorpus/render.jsonl", corpus, 0o600)
}
