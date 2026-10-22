# Human–AI co-design: a bounded GNN retrieval experiment

Author: Dahe Chen. October 22, 2026.

## Human direction

The student requested an experiment within the existing AutoTriager system,
not a replacement application or an unrelated graph example. The following
is an English translation of the student's instruction:

> Try GNNs and test whether they help. Design the system around our project's
> characteristics. If there is no improvement, or it solves only a particular
> problem, analyze why and continue experimenting. Run at most three versions.
> Show how my prompts guided the human–AI collaboration and result analysis.

This instruction sets the objective, scope, failure-analysis procedure and
iteration limit. It is not a student judgment that a particular model,
relevance label or generated answer is correct.

An earlier accepted design decision also applies: first establish whether an
undocumented dependency exists, then conditionally inspect its health. Thus,
embedding similarity may prioritize evidence but cannot create a verified
dependency or establish the cause of an incident.

## AI implementation proposal

Use the existing Shop knowledge graph and reviewed passages. Apply a small
mean-aggregation GraphSAGE encoder to a documented projection of that graph.
Keep original source records and edge conditions available for evidence lookup.
The learned representation is a retrieval signal, not a replacement for evidence.

The first experiment compares the original retriever with GNN reranking on the
same candidate pool, questions and top-k budget. The three questions were
previously inspected; all results are development observations. No held-out
diagnostic accuracy or benefit to engineers is claimed.

## Bounded iteration policy

1. Freeze V1 before its measured results are inspected.
2. Diagnose a specific failure or limitation before proposing V2. Record the
   hypothesis and the single main change before rerunning.
3. Use V3 only to test a remaining, stated explanation. Stop after V3 or sooner
   if the evidence does not justify another attempt.

Do not rewrite earlier results, tune relevance labels, train on evaluation
questions or convert training-loss improvement into retrieval improvement.
Every version must retain its configuration, input hashes, rankings and failure
analysis. A negative result is an acceptable coursework observation.

No additional LLM generation, paid API calls, fault injection or cloud graph
mutation is needed for this experiment. The existing GraphRAG answer stage is
retained; changed retrieval does not by itself demonstrate better answers.

## Human participation and limits

The student's verified contribution is the project objective, the bounded
experiment instruction and the earlier evidence policy. The AI is responsible
for the proposed architecture, implementation, measurements and technical
failure analysis. An independent AI agent reviews the implementation and claims.
That review is simulated scrutiny, not student evaluation or expert certification.

The student asked for an explanation of the assignment before proceeding. The
explanation distinguished graph retrieval, neighbor aggregation and downstream
LLM answers. Understanding of the numerical update and acceptance of a final GNN
version have not yet been assessed. Do not present those as completed activities.

No October 20 classroom notebook or exercise output has been supplied or found
in this workspace. New execution is labeled an independent project exercise on
October 22, rather than a claim of classroom participation or classroom results.
