// ruleid: naming.no-any-type-parameter-typescript
function process(data: any) { return data; }
// ok: naming.no-any-type-parameter-typescript
function processSafe(data: unknown) { return data; }
