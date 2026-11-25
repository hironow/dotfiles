# ruleid: immutability.no-list-append-param-python
def add_item(items, item):
    items.append(item)
    return items

# ruleid: immutability.no-list-extend-param-python
def extend_items(items, other):
    items.extend(other)
    return items

# ruleid: immutability.no-dict-mutation-param-python
def update_user(user, name):
    user["name"] = name
    return user

# ruleid: immutability.no-list-sort-param-python
def sort_items(items):
    items.sort()
    return items

# ok: immutability.no-list-append-param-python
def add_item_safe(items, item):
    return [*items, item]

# ok: immutability.no-dict-mutation-param-python
def update_user_safe(user, name):
    return {**user, "name": name}

# ok: immutability.no-list-sort-param-python
def sort_items_safe(items):
    return sorted(items)
