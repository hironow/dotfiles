import Glossary.Render
import Glossary.DeploySync
import Glossary.Architecture

/-!
# Registry

List here every glossary that the checks and the generated documents cover.

To add a glossary: add its `import` line above, and add `<Domain>.book.view labels` to `books`.
To choose the language of the generated documents: change the one line `def labels` below
(`Labels.en`, `Labels.ja`, or your own).
-/

namespace Glossary

def labels : Labels := Labels.ja

def books : List BookView :=
  [DeploySync.book.view labels, Architecture.book.view labels]

/-- The comparison with a tool-less control (workflow step 5, Tier 3): `.run` once an
`experiments/<name>/` has `protocol.md` committed before `result.md`, or `.skipped "<reason>"`. -/
def control : Control :=
  .skipped "Tier 1（必須項目）の構築を優先したため、Tier 3 の対照実験は未実施"

end Glossary
