package main

import (
	"bytes"
	"errors"
	"regexp"
	"strconv"
)

const bunFixSource = "https://github.com/oven-sh/bun/commit/2a5cbbcb084770dec7d7e2f21cdfd4f7f49b1ee3"

// A comparison concerns a string candidate, never an attested binary version.
type RuntimeReview struct {
	CandidateVersion string `json:"candidate_version"`
	Comparison       string `json:"comparison"`
	BinaryIdentity   string `json:"binary_identity"`
	PatchStatus      string `json:"patch_status"`
	CVE              string `json:"cve"`
	ReviewedRelease  string `json:"reviewed_release"`
	ReviewedAt       string `json:"reviewed_at"`
	Source           string `json:"source"`
}

var stableBunVersion = regexp.MustCompile(`^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(\+[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$`)

func reviewBun(candidate string) RuntimeReview {
	review := RuntimeReview{CandidateVersion: candidate, Comparison: "unverified-version", BinaryIdentity: "unverified", PatchStatus: "unverified", CVE: "CVE-2026-111497", ReviewedRelease: "1.4.4", ReviewedAt: "2026-10-24", Source: bunFixSource}
	match := stableBunVersion.FindStringSubmatch(candidate)
	if match == nil {
		return review
	}
	var version [3]uint64
	for i := range version {
		n, err := strconv.ParseUint(match[i+1], 10, 64)
		if err != nil {
			return review
		}
		version[i] = n
	}
	review.Comparison = "at-or-above-reviewed-release-threshold"
	floor := [3]uint64{1, 4, 4}
	for i := range version {
		if version[i] < floor[i] {
			review.Comparison = "below-reviewed-release-threshold"
			break
		}
		if version[i] > floor[i] {
			break
		}
	}
	return review
}

func bunReviews(evidence []Evidence) []RuntimeReview {
	var reviews []RuntimeReview
	for _, e := range evidence {
		if e.Kind == "bun-version-string" {
			reviews = append(reviews, reviewBun(e.Detail))
		}
	}
	return reviews
}

type bunScanner struct {
	tail     []byte
	token    []byte
	reading  bool
	overlong bool
	versions []string
	seen     map[string]bool
	err      error
}

func newBunScanner() *bunScanner { return &bunScanner{seen: map[string]bool{}} }

func versionByte(b byte) bool {
	return b >= '0' && b <= '9' || b >= 'A' && b <= 'Z' || b >= 'a' && b <= 'z' || b == '.' || b == '+' || b == '-' || b == '_'
}

func (s *bunScanner) feed(chunk []byte) {
	s.tail = append(s.tail, chunk...)
	data := s.tail
	s.tail = nil
	for len(data) > 0 && s.err == nil {
		if s.reading {
			n := 0
			for n < len(data) && versionByte(data[n]) {
				n++
			}
			keep := min(n, 256-len(s.token))
			s.token = append(s.token, data[:keep]...)
			if n > keep {
				s.overlong = true
			}
			data = data[n:]
			if len(data) == 0 {
				return
			}
			s.endToken(false)
			data = data[1:]
			continue
		}
		index := bytes.Index(data, []byte("Bun v"))
		other := bytes.Index(data, []byte("bun-v"))
		if index < 0 || other >= 0 && other < index {
			index = other
		}
		if index < 0 {
			s.tail = append([]byte(nil), data[max(0, len(data)-4):]...)
			return
		}
		data = data[index+5:]
		s.reading = true
	}
}

func (s *bunScanner) endToken(interrupted bool) {
	value := string(s.token)
	if s.overlong || interrupted {
		value += "<truncated>"
	}
	if len(value) > 0 && value[0] >= '0' && value[0] <= '9' && !s.seen[value] {
		if len(s.versions) == 16 {
			s.err = errors.New("bun candidate limit exceeded (16); remaining candidates uninspected")
		} else {
			s.versions = append(s.versions, value)
			s.seen[value] = true
		}
	}
	s.reading = false
	s.overlong = false
	s.token = nil
}

func (s *bunScanner) finish(complete bool) {
	if s.reading {
		s.endToken(!complete)
	}
}

func (s *bunScanner) evidence() []Evidence {
	var result []Evidence
	for _, version := range s.versions {
		result = append(result, Evidence{"bun-version-string", version})
	}
	return result
}
