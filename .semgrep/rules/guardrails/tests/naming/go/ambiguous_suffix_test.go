package main

// ruleid: naming.ambiguous-suffix-struct-go
type UserManager struct {
	users []string
}

// ruleid: naming.ambiguous-suffix-struct-go
type TaskEngine struct {
	tasks []string
}

// ruleid: naming.ambiguous-suffix-struct-go
type ConnectionUtil struct{}

// ruleid: naming.ambiguous-suffix-struct-go
type UserFacade struct{}

// ruleid: naming.ambiguous-suffix-struct-go
type AuthService struct{}

// ruleid: naming.ambiguous-suffix-struct-go
type AppRuntime struct{}

// ok: naming.ambiguous-suffix-struct-go
type UserRegistry struct{}

// ok: naming.ambiguous-suffix-struct-go
type TaskScheduler struct{}

// ok: naming.ambiguous-suffix-struct-go
type AuthPolicy struct{}

// ok: naming.ambiguous-suffix-struct-go
type OrderFactory struct{}

// ruleid: naming.ambiguous-suffix-interface-go
type DataManager interface {
	Get() string
}

// ok: naming.ambiguous-suffix-interface-go
type DataStore interface {
	Get() string
}
