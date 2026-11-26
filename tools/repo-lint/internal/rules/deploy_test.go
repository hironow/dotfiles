package rules

import "testing"

const deployScript = `case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    cp -f ~/dotfiles/dump/gitignore-global ~/.config/git/ignore
    # shared.gitconfig stays manual (ADR 0021); a comment may name it
    printf '\tpath = ~/dotfiles/config/git/aliases.gitconfig\n'
    exit 0
    ;;
esac
cp ~/dotfiles/dump/gitignore-global ~/.config/git/ignore
`

func TestDeploySharedConfig(t *testing.T) {
	base := func() Inputs { return Inputs{deployScriptPath: deployScript} }
	d := deployScriptPath
	runCases(t, deploySharedConfig(), base, []ruleCase{
		{"the Unix path reads a host's gitignore", edit(d, "cp ~/dotfiles/dump/gitignore-global", "cp ~/dotfiles/dump/$host/gitignore-global"), "dump/"},
		{"a braced host variable", edit(d, "cp ~/dotfiles/dump/gitignore-global", "cp ~/dotfiles/dump/${host}/gitignore-global"), "dump/"},
		{"the Windows path includes shared.gitconfig", edit(d, "path = ~/dotfiles/config/git/aliases.gitconfig", "path = ~/dotfiles/config/git/shared.gitconfig"), "shared.gitconfig"},
		{"the Unix path includes shared.gitconfig", edit(d, "esac\n", "esac\ngit config --global include.path=x\nprintf 'path = ~/dotfiles/config/git/shared.gitconfig'\n"), "shared.gitconfig"},
	})
}
