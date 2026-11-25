// ok: structure.multiple-exported-classes-typescript
export class UserRepository {
    db: string = "";
}

// Private class - ok to coexist
class InternalHelper {
    cache: Map<string, string> = new Map();
}
