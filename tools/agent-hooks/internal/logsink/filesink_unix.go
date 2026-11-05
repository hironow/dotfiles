//go:build unix

package logsink

import (
	"errors"
	"fmt"
	"io"
	"os"
	"syscall"
	"time"
)

// FileSink stores lines through directory handles that survive ancestor renames.
type FileSink struct {
	hooks *os.Root
	logs  *os.Root
	uid   int
}

// OpenFileSink opens base/dotfiles/agent-hooks/logs and checks the owned levels.
// The base is made when missing and is not checked. uid is the required owner.
func OpenFileSink(base string, uid int) (*FileSink, error) {
	if err := os.MkdirAll(base, 0o700); err != nil {
		return nil, err
	}
	root, err := os.OpenRoot(base)
	if err != nil {
		return nil, err
	}
	defer root.Close()
	dotfiles, err := openDirectory(root, "dotfiles", uid, false)
	if err != nil {
		return nil, err
	}
	defer dotfiles.Close()
	hooks, err := openDirectory(dotfiles, "agent-hooks", uid, true)
	if err != nil {
		return nil, err
	}
	logs, err := openDirectory(hooks, "logs", uid, true)
	if err != nil {
		return nil, errors.Join(err, hooks.Close())
	}
	return &FileSink{hooks: hooks, logs: logs, uid: uid}, nil
}

// Close releases both directory handles.
func (s *FileSink) Close() error {
	return errors.Join(s.logs.Close(), s.hooks.Close())
}

func openDirectory(parent *os.Root, name string, uid int, private bool) (*os.Root, error) {
	if err := parent.Mkdir(name, 0o700); err != nil && !errors.Is(err, os.ErrExist) {
		return nil, err
	}
	root, err := parent.OpenRoot(name)
	if err != nil {
		return nil, err
	}
	if err := checkDirectory(parent, root, name, uid, private); err != nil {
		return nil, errors.Join(err, root.Close())
	}
	return root, nil
}

func checkDirectory(parent, root *os.Root, name string, uid int, private bool) error {
	dir, err := root.Open(".")
	if err != nil {
		return err
	}
	defer dir.Close()
	info, err := dir.Stat()
	if err != nil {
		return err
	}
	if err := checkName(parent, name, info); err != nil {
		return err
	}
	if !private {
		return nil
	}
	stat, ok := info.Sys().(*syscall.Stat_t)
	if !ok || !info.IsDir() || int64(stat.Uid) != int64(uid) {
		return fmt.Errorf("%s: directory owner or type is unsafe", name)
	}
	// An ACL could reach past the mode bits, and its inheritable entries
	// would pass to every file made in the directory (clearACL).
	if err := clearACL(dir); err != nil {
		return fmt.Errorf("%s: %w", name, err)
	}
	if info.Mode().Perm()&0o077 != 0 {
		return dir.Chmod(0o700)
	}
	return nil
}

func checkName(parent *os.Root, name string, opened os.FileInfo) error {
	info, err := parent.Lstat(name)
	if err != nil {
		return err
	}
	if info.Mode()&os.ModeSymlink != 0 || !os.SameFile(info, opened) {
		return fmt.Errorf("%s: linked or replaced name", name)
	}
	return nil
}

func openFile(root *os.Root, name string, flags, uid int, create bool) (*os.File, error) {
	file, err := root.OpenFile(name, flags|syscall.O_NONBLOCK, 0)
	if create && errors.Is(err, os.ErrNotExist) {
		file, err = root.OpenFile(name, flags|syscall.O_NONBLOCK|os.O_CREATE|os.O_EXCL, 0o600)
		if errors.Is(err, os.ErrExist) {
			file, err = root.OpenFile(name, flags|syscall.O_NONBLOCK, 0)
		}
	}
	if err != nil {
		return nil, err
	}
	if err := checkFile(root, file, name, uid); err != nil {
		return nil, errors.Join(err, file.Close())
	}
	return file, nil
}

func checkFile(root *os.Root, file *os.File, name string, uid int) error {
	info, err := file.Stat()
	if err != nil {
		return err
	}
	stat, ok := info.Sys().(*syscall.Stat_t)
	if !ok || !info.Mode().IsRegular() || int64(stat.Uid) != int64(uid) {
		return fmt.Errorf("%s: file owner or type is unsafe", name)
	}
	if err := checkName(root, name, info); err != nil {
		return err
	}
	if stat.Nlink != 1 {
		return extraLinks
	}
	if err := clearACL(file); err != nil {
		return fmt.Errorf("%s: %w", name, err)
	}
	if info.Mode().Perm()&0o077 != 0 {
		return file.Chmod(0o600)
	}
	return nil
}

type fileProblem string

func (p fileProblem) Error() string { return string(p) }

const extraLinks fileProblem = "file has more than one link"

// Write appends one line to now's UTC day file through the saved logs handle.
func (s *FileSink) Write(now time.Time, line []byte) error {
	if len(line) == 0 || len(line) >= MaxLine || line[len(line)-1] != '\n' {
		return fmt.Errorf("log line must end in a newline and contain 1 to %d bytes", MaxLine-1)
	}
	file, err := openFile(s.logs, now.UTC().Format("2006-01-02")+".jsonl", os.O_APPEND|os.O_WRONLY, s.uid, true)
	if err != nil {
		return err
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil {
		return err
	}
	if info.Size() > DayCap-int64(len(line)) {
		return fmt.Errorf("day file would exceed %d bytes", DayCap)
	}
	n, err := file.Write(line)
	if err != nil {
		return err
	}
	if n != len(line) {
		return io.ErrShortWrite
	}
	return s.retain(now)
}
