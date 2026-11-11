// Package registry is an in-memory stand-in for the npm registry.
package registry

import (
	"context"
	"fmt"
)

// Package is one published npm package.
type Package struct {
	Latest   string
	Versions []string
}

// Fake holds the packages it knows by name.
type Fake struct{ Packages map[string]Package }

func (f *Fake) Versions(_ context.Context, pkg string) (string, []string, error) {
	p, ok := f.Packages[pkg]
	if !ok {
		return "", nil, fmt.Errorf("npm: no package %s", pkg)
	}
	return p.Latest, p.Versions, nil
}
