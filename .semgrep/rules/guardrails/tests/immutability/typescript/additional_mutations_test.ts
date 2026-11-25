const arr = [1, 2, 3];
const obj = { name: "test", nested: { key: "val" } };

// ruleid: immutability.no-array-unshift-typescript
arr.unshift(0);

// ruleid: immutability.no-array-fill-typescript
arr.fill(0);

// ruleid: immutability.no-array-copywithin-typescript
arr.copyWithin(0, 1);

// ruleid: immutability.no-delete-property-typescript
delete obj.name;

// ok: immutability.no-array-unshift-typescript
const newArr = [0, ...arr];

// ok: immutability.no-delete-property-typescript
const { name, ...rest } = obj;
