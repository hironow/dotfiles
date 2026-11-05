//go:build unix

package logsink

import (
	"crypto/rand"
	"errors"
	"fmt"
	"io"
	"os"
	"syscall"
)

// Salt reads the machine's salt, making it under a non-blocking lock if needed.
// Unsafe files, invalid lengths, and a busy lock leave the salt unavailable.
func (s *FileSink) Salt() ([]byte, bool) {
	salt, err := s.readSalt()
	if err == nil {
		return salt, true
	}
	if !errors.Is(err, os.ErrNotExist) && !errors.Is(err, extraLinks) {
		return nil, false
	}
	lock, err := openFile(s.hooks, "salt.lock", os.O_RDWR, s.uid, true)
	if err != nil {
		return nil, false
	}
	defer lock.Close()
	if err := syscall.Flock(int(lock.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		return nil, false
	}
	if err := removeIfPresent(s.hooks, "salt.new"); err != nil {
		return nil, false
	}
	salt, err = s.readSalt()
	if err == nil {
		return salt, true
	}
	if !errors.Is(err, os.ErrNotExist) {
		return nil, false
	}
	if err := s.makeSalt(); err != nil {
		return nil, false
	}
	salt, err = s.readSalt()
	return salt, err == nil
}

func (s *FileSink) readSalt() ([]byte, error) {
	file, err := openFile(s.hooks, "salt", os.O_RDONLY, s.uid, false)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	salt, err := io.ReadAll(io.LimitReader(file, SaltSize+1))
	if err != nil {
		return nil, err
	}
	if len(salt) != SaltSize {
		return nil, fmt.Errorf("salt must have %d bytes", SaltSize)
	}
	return salt, nil
}

func (s *FileSink) makeSalt() error {
	file, err := s.hooks.OpenFile("salt.new", os.O_CREATE|os.O_EXCL|os.O_WRONLY|syscall.O_NONBLOCK, 0o600)
	if err != nil {
		return err
	}
	defer file.Close()
	if err := checkFile(s.hooks, file, "salt.new", s.uid); err != nil {
		return err
	}
	if err := writeSalt(file); err != nil {
		return err
	}
	linkErr := s.hooks.Link("salt.new", "salt")
	return errors.Join(linkErr, removeIfPresent(s.hooks, "salt.new"))
}

func writeSalt(file *os.File) error {
	salt := make([]byte, SaltSize)
	if _, err := rand.Read(salt); err != nil {
		return err
	}
	n, err := file.Write(salt)
	if err != nil {
		return err
	}
	if n != len(salt) {
		return io.ErrShortWrite
	}
	return file.Sync()
}

func removeIfPresent(root *os.Root, name string) error {
	err := root.Remove(name)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	return err
}
