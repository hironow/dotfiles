// ruleid: naming.ambiguous-suffix-class-typescript
class UserManager {
    users: string[] = [];
}

// ruleid: naming.ambiguous-suffix-class-typescript
class TaskEngine {
    tasks: string[] = [];
}

// ruleid: naming.ambiguous-suffix-interface-typescript
interface ConnectionService {
    connect(): void;
}

// ruleid: naming.ambiguous-suffix-type-alias-typescript
type AppRuntime = {
    name: string;
};

// ok: naming.ambiguous-suffix-class-typescript
class UserRegistry {
    users: string[] = [];
}

// ok: naming.ambiguous-suffix-interface-typescript
interface DataStore {
    get(): string;
}

// ok: naming.ambiguous-suffix-type-alias-typescript
type TaskExecutor = {
    run(): void;
};
