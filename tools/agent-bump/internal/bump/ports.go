package bump

import "context"

// Releases answers questions about GitHub repositories and their tags.
type Releases interface {
	// Latest is the newest non-prerelease release tag.
	Latest(ctx context.Context, repo string) (string, error)
	// Commit is the commit a ref points at; it fails when the ref is missing.
	Commit(ctx context.Context, repo, ref string) (string, error)
	// Tree lists every file and directory at ref.
	Tree(ctx context.Context, repo, ref string) ([]TreeEntry, error)
	// File is one file's content at ref.
	File(ctx context.Context, repo, ref, path string) ([]byte, error)
}

// TreeEntry is one path in a repository tree.
type TreeEntry struct {
	Path string
	Dir  bool
	SHA  string
}

// Registry answers questions about published npm packages.
type Registry interface {
	// Versions are the newest version and every published one.
	Versions(ctx context.Context, pkg string) (latest string, all []string, err error)
}

// Repo reads and writes the dotfiles checkout.
type Repo interface {
	Read(path string) (string, error)
	Write(path, content string) error
}

// Machine installs and checks the declarations on this machine.
type Machine interface {
	// Baseline checks the item's kind before any write: a red check would
	// make the bump's own verification fail for an unrelated reason.
	Baseline(ctx context.Context, it Item) error
	// Install makes this machine follow the declarations for the item.
	Install(ctx context.Context, it Item, t Target) error
	// Verify checks that this machine now has the item at t.
	Verify(ctx context.Context, it Item, t Target) error
	// EGMRequiredPaths are the files the Pi installer requires in a bundle.
	EGMRequiredPaths(ctx context.Context) ([]string, error)
}
