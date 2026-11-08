package logline

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"math"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

func projectDirectory(f Firing) string {
	if f.Call != nil {
		if cwd := f.Call.Fields[ir.FieldCwd]; cwd.IsString {
			return cwd.Text
		}
		if workspaces := f.Call.Lists[ir.ListWorkspaces]; len(workspaces) > 0 && workspaces[0].IsString {
			return workspaces[0].Text
		}
	}
	return f.Wd
}

func typed(value ir.Value) string {
	if value.IsString {
		return "s" + value.Text
	}
	return "j" + value.Text
}

func identityHash(salt []byte, fields ...string) string {
	mac := hmac.New(sha256.New, salt)
	for _, field := range fields {
		// Clamp the length to four bytes on both 32-bit and 64-bit targets.
		count := binary.BigEndian.AppendUint32(nil, uint32(min(uint64(len(field)), math.MaxUint32)))
		mac.Write(count)
		mac.Write([]byte(field))
	}
	return hex.EncodeToString(mac.Sum(nil))
}

func (l *Line) identify(f Firing, salt []byte) {
	if len(salt) != SaltSize {
		return
	}
	if dir := projectDirectory(f); dir != "" {
		l.Project = identityHash(salt, "project", dir)[:16]
	}
	if f.Call == nil {
		return
	}
	session, hasSession := f.Call.Fields[ir.FieldSessionID]
	call, hasCall := f.Call.Fields[ir.FieldCallID]
	if hasSession && hasCall {
		l.TraceID = identityHash(salt, "trace", l.Harness, typed(session), typed(call))[:32]
	}
}
