package main

// ok: structure.multiple-exported-structs-go
type UserRepository struct {
	db string
}

// Private type - ok to coexist
type internalHelper struct {
	cache map[string]string
}
