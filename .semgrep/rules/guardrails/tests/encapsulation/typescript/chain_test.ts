// ruleid: demeter.method-chain-3-levels-typescript
const city = order.getCustomer().getAddress().getCity();
// ok: demeter.method-chain-3-levels-typescript
const result = arr.filter(x => x > 0).map(x => x * 2);
