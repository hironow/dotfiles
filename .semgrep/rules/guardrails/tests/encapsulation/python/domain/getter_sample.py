class User:
    # ruleid: breach-encapsulation.getter-method-domain-python
    def get_name(self):
        return self._name
    # ok: breach-encapsulation.getter-method-domain-python
    def breach_encapsulation_of_name(self):
        return self._name
