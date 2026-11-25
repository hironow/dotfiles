// ruleid: complexity.deep-inheritance-3-levels-typescript
class Animal {
    name: string = "";
}

class Mammal extends Animal {
    legs: number = 4;
}

class Dog extends Mammal {
    breed: string = "";
}
