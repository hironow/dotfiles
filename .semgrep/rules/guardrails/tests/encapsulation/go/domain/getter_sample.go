package domain
// ruleid: breach-encapsulation.getter-method-domain-go
func (u *User) GetName() string { return u.name }
// ok: breach-encapsulation.getter-method-domain-go
func (u *User) BreachEncapsulationOfName() string { return u.name }
