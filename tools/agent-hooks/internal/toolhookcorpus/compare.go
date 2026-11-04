package toolhookcorpus

import (
	"bytes"
	"errors"
	"io"
	"math"
	"math/big"
	"slices"
	"strconv"
	"strings"

	"github.com/goccy/go-json/jsontext"
)

// SameJSON reports whether two JSON texts hold the same value, as Python's
// json and the harnesses read them: member order and escaping do not count;
// an integer literal is compared exactly, as a big integer (Python keeps it
// whole), and any other number as a double (Python and the harnesses read it
// so). Duplicate member names and invalid UTF-8 are allowed, so a legacy
// answer is read whatever it holds.
func SameJSON(a, b []byte) (bool, error) {
	left, err := readValue(a)
	if err != nil {
		return false, err
	}
	right, err := readValue(b)
	if err != nil {
		return false, err
	}
	return equal(left, right), nil
}

// value is a JSON value: an object (members by name), an array, a string, a
// number (its literal), or one of true, false, null.
type value struct {
	kind    byte // '{', '[', '"', '0', 't', 'f', 'n'
	members map[string]value
	items   []value
	text    string
}

func readValue(text []byte) (value, error) {
	decoder := jsontext.NewDecoder(bytes.NewReader(text), jsontext.AllowDuplicateNames(true), jsontext.AllowInvalidUTF8(true))
	v, err := read(decoder)
	if err != nil {
		return value{}, err
	}
	if _, err := decoder.ReadToken(); !errors.Is(err, io.EOF) {
		return value{}, errors.New("more than one JSON value")
	}
	return v, nil
}

func read(decoder *jsontext.Decoder) (value, error) {
	token, err := decoder.ReadToken()
	if err != nil {
		return value{}, err
	}
	switch kind := token.Kind(); kind {
	case '{':
		members := map[string]value{}
		for decoder.PeekKind() != '}' {
			nameToken, err := decoder.ReadToken()
			if err != nil {
				return value{}, err
			}
			name := nameToken.String() // read now: the next call voids the token
			member, err := read(decoder)
			if err != nil {
				return value{}, err
			}
			members[name] = member // the last of a duplicate name wins, as in Python
		}
		_, err := decoder.ReadToken()
		return value{kind: '{', members: members}, err
	case '[':
		var items []value
		for decoder.PeekKind() != ']' {
			item, err := read(decoder)
			if err != nil {
				return value{}, err
			}
			items = append(items, item)
		}
		_, err := decoder.ReadToken()
		return value{kind: '[', items: items}, err
	case '"':
		return value{kind: '"', text: token.String()}, nil
	case '0':
		return value{kind: '0', text: token.String()}, nil
	default:
		return value{kind: byte(kind)}, nil
	}
}

func equal(a, b value) bool {
	if a.kind != b.kind {
		return false
	}
	switch a.kind {
	case '{':
		if len(a.members) != len(b.members) {
			return false
		}
		for name, member := range a.members {
			other, ok := b.members[name]
			if !ok || !equal(member, other) {
				return false
			}
		}
		return true
	case '[':
		return slices.EqualFunc(a.items, b.items, equal)
	case '"':
		return a.text == b.text
	case '0':
		return sameNumber(a.text, b.text)
	default:
		return true
	}
}

// sameNumber compares two number literals as Python's json reads them and
// Python compares them: an integer literal is an exact integer, any other a
// double, and an integer and a double compare exactly (9007199254740993 is
// not 9007199254740993.0, which rounds to 9007199254740992).
func sameNumber(a, b string) bool {
	x, okX := pythonNumber(a)
	y, okY := pythonNumber(b)
	if !okX || !okY {
		return false
	}
	if x.inf != 0 || y.inf != 0 {
		return x.inf == y.inf
	}
	return x.exact.Cmp(y.exact) == 0
}

// number is a JSON number as Python holds it: exactly, or as an infinity (a
// double that overflowed; inf is its sign).
type number struct {
	exact *big.Rat
	inf   int
}

func pythonNumber(literal string) (number, bool) {
	if isInteger(literal) {
		n, ok := new(big.Int).SetString(literal, 10)
		if !ok {
			return number{}, false
		}
		return number{exact: new(big.Rat).SetInt(n)}, true
	}
	f, err := strconv.ParseFloat(literal, 64)
	if err != nil && !errors.Is(err, strconv.ErrRange) {
		return number{}, false
	}
	if math.IsInf(f, 0) {
		if f > 0 {
			return number{inf: 1}, true
		}
		return number{inf: -1}, true
	}
	exact := new(big.Rat)
	if exact.SetFloat64(f) == nil {
		return number{}, false
	}
	return number{exact: exact}, true
}

func isInteger(literal string) bool { return !strings.ContainsAny(literal, ".eE") }
