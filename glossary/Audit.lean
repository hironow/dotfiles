import Glossary

/-! Prints the axioms the proofs use. `just lean-check` rejects `sorryAx` and friends.
Add one line for every theorem that a claim cites as evidence. -/

#print axioms Glossary.check_sound
#print axioms Glossary.check_add
#print axioms Glossary.Progress.resolvable
#print axioms Glossary.DeploySync.terms_wellFormed
#print axioms Glossary.DeploySync.book_check
#print axioms Glossary.Architecture.terms_wellFormed
#print axioms Glossary.Architecture.selfSource_outranks_thirdParty
#print axioms Glossary.Architecture.prek_hooks_readonly_no_prepush
#print axioms Glossary.Architecture.mcp_secret_never_auto_registered
#print axioms Glossary.Architecture.book_check
