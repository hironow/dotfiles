package domain
// ruleid: clean-architecture.domain-imports-infrastructure-go
import "myapp/infrastructure/database"
// ruleid: clean-architecture.domain-imports-adapter-go
import "myapp/adapter/http"
var _ = database.DB
var _ = http.Handler
