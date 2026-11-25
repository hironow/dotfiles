package main

// ruleid: complexity.deep-embedding-3-levels-go
type Base struct {
	ID string
}

type Middle struct {
	Base
	Name string
}

type Leaf struct {
	Middle
	Value int
}
