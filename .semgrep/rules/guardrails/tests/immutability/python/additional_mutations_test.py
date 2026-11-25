# ruleid: immutability.no-list-insert-param-python
def insert_item(items, idx, item):
    items.insert(idx, item)
    return items

# ruleid: immutability.no-list-remove-param-python
def remove_item(items, item):
    items.remove(item)
    return items

# ruleid: immutability.no-list-clear-param-python
def clear_items(items):
    items.clear()

# ruleid: immutability.no-list-reverse-param-python
def reverse_items(items):
    items.reverse()
    return items

# ruleid: immutability.no-dict-update-param-python
def merge_dict(data, extra):
    data.update(extra)
    return data

# ruleid: immutability.no-dict-pop-param-python
def remove_key(data, key):
    data.pop(key)
    return data
