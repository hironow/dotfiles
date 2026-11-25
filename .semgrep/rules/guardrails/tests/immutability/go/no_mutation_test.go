package main

// ruleid: immutability.no-param-slice-append-go
func AddItem(items []string, item string) []string {
	return append(items, item)
}

// ruleid: immutability.no-pointer-field-mutation-go
func UpdateUser(user *User, name string) *User {
	user.Name = name
	return user
}

// ok: immutability.no-param-slice-append-go
func AddItemSafe(items []string, item string) []string {
	newItems := make([]string, len(items)+1)
	copy(newItems, items)
	newItems[len(items)] = item
	return newItems
}

// ok: immutability.no-pointer-field-mutation-go
func UpdateUserSafe(user User, name string) User {
	return User{
		Name: name,
		Age:  user.Age,
	}
}

type User struct {
	Name string
	Age  int
}
