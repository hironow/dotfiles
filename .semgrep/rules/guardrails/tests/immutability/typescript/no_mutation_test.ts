const arr = [1, 2, 3];

// ruleid: immutability.no-array-push-typescript
arr.push(4);

// ruleid: immutability.no-array-pop-typescript
arr.pop();

// ruleid: immutability.no-array-splice-typescript
arr.splice(0, 1);

// ruleid: immutability.no-array-sort-inplace-typescript
arr.sort();

// ruleid: immutability.no-array-reverse-inplace-typescript
arr.reverse();

// ruleid: immutability.no-param-property-mutation-typescript
function updateUser(user: any, name: string) {
    user.name = name;
    return user;
}

// ok: immutability.no-array-push-typescript
const newArr = [...arr, 4];

// ok: immutability.no-array-sort-inplace-typescript
const sorted = [...arr].sort();

// ok: immutability.no-array-reverse-inplace-typescript
const reversed = [...arr].reverse();

// ok: immutability.no-param-property-mutation-typescript
function updateUserSafe(user: any, name: string) {
    return { ...user, name };
}
