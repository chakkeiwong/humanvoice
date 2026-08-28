# Humanvoice: fewer wasted revision rounds

A technical document can be correct, compile without warnings, survive several
agent reviews, and still fail in its first five minutes with a human reader.
That happened to a funding proposal in this workspace. The reader could not
state its purpose, did not know what the file names and internal labels were
for, and could not tell what action the proposal requested. The document had
not failed because of a typo. It had asked a scarce expert reader to reconstruct
an argument that the author should have made explicit.

This is the economic problem humanvoice addresses. A senior reader's attention
is expensive, and rejection rarely ends the work. It begins another round of
diagnosis, revision, and rereading. Existing tools catch grammar, repeated
phrases, and some stylistic habits. A general language model can rewrite a
passage or comment on it. Neither can tell us that the right reader now
understands the purpose, trusts the evidence, and is willing to act. Worse, an
automatic rewrite can silently change a number, citation, assumption, or claim
while making the sentence sound smoother.

Humanvoice is a revision system for that gap. It does not try to manufacture a
generic "human" style. It helps an author move a technical document from a
draft that is locally fluent to one that a named reader can understand and
accept. It combines three jobs that are currently scattered across linters,
prompts, manual comparisons, and review notes.

First, it finds problems that can be located without pretending that they
measure quality. It points to internal project language that has leaked into
the manuscript, repetitive sentence and paragraph shapes, defensive
qualifications, suspicious citation metadata, and passages that may need a
substantive explanation. Every finding includes the source span and an
editorial question. It does not change the text.

Second, it protects the document while an author or editor revises it. The
system knows which equations, numbers, citation keys, labels, quotations, and
claims must survive. It compares each candidate with the prior version and
asks for an explanation of any substantive change. This makes aggressive
recomposition possible without asking the reader to trust a clean-looking
diff.

Third, it ends with a reader decision. A low-context reviewer receives the
document without the repository history that made its private language seem
normal to the author. The final authority remains a human reader who records
whether the document is accepted or what still prevents acceptance. Surface
scores can direct attention. They cannot promote a document.

Consider the failed funding proposal again. Humanvoice would first identify
the file paths, phase labels, and status vocabulary that ask the reader to
understand the project machinery. It would show the author where paragraph
openings and caveats repeat, but would not equate a low count with good prose.
During revision, it would preserve the proposal's quantitative assumptions and
citations. A fresh reader would then answer a short set of questions: What is
the problem? What is being proposed? Why this design rather than the obvious
alternative? What evidence supports it? What decision is requested? A wrong or
missing answer sends the document back for substantive repair, not another
round of synonym replacement.

The obvious alternative is to combine an ordinary prose linter, a general LLM
editor, and manual review. Humanvoice must earn its place against that baseline.
Its advantage is not another model or another list of disliked words. It is the
connection between located diagnosis, protected revision, and an observable
reader outcome. The baseline has useful components, and humanvoice should reuse
them where they work. The product is the disciplined journey between those
components.

The research makes this design plausible and also limits what may be promised.
Controlled studies show that generative assistance can make some writing and
knowledge-work tasks faster or better scored. The effects vary with the task
and the worker; experienced users can benefit less, and assistance outside a
model's capability frontier can reduce correctness. Studies of writing
feedback find that models often produce specific local comments while missing
the most important defect. Recent systematic reviews find more consistent
benefits for grammar, process, and surface accuracy than for argumentation,
organization, or creativity. Research on model judges adds order, length, and
self-preference biases. These findings support targeted assistance and direct
human evaluation. They do not establish that humanvoice will reduce revision
rounds for expert economics writing.

The software survey leads to the same product boundary. Mature tools already
provide markup-aware linting, LaTeX parsing, document conversion, visual diffs,
citation metadata, and local model execution. None has been shown to produce
reader acceptance. Humanvoice should therefore integrate replaceable
components rather than build a monolith or adopt a package on the strength of
its README. The first parser and diagnostic choices will be decided on held-out
documents with protected equations and human labels.

The proposed first investment is a bounded twelve-week build and feasibility
run. The team would implement a common document representation for Markdown
and LaTeX, three high-value diagnostic families, protected comparison, citation
identity checks, and a simple review workspace. It would also assemble a small
evaluation corpus from documents with recorded rejection and repair histories.
One live document would then pass through the complete system. That case would
test integration, privacy, logging, reviewer burden, and the stop rules. It
would not be reported as evidence of efficacy.

The outcome that matters is the number of human-feedback rounds required to
reach reader acceptance, subject to no increase in reader time or
meaning-preservation failures. The comparison is the current combination of
ordinary tools, ad hoc LLM editing, and manual review. Secondary measures such
as false-positive burden, time spent editing, reader reconstruction, and
substantive revision explain the result; they do not replace it. The later
efficacy study will be sized from observed baseline variation rather than from
an arbitrary document count and will report results separately for expert and
less-experienced writers.

The build should stop or change direction if diagnostics consume more review
time than they save, protected content changes without explanation, privacy
requirements cannot be met, or the workflow does not make reader acceptance
faster after two pilot cycles. Those are product failures even if every command
runs and every surface score improves.

The decision requested now is deliberately smaller than a deployment decision.
Authorize the MVP, the evaluation assets needed to test it, and one feasibility
document. At the end of that work, the project owner should receive a working
system, a measured account of its burden and failures, a priced plan for the
comparative study, and a clear recommendation to proceed, revise, or stop. The
current evidence supports learning whether this product works. It does not yet
support claiming that it does.
