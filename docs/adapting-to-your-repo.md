# Adapting ForgeLoop

Before using ForgeLoop in a new repo:

1. Define authoritative sources: source files, specs, papers, official docs.
2. Define generated-result paths that agents must not edit.
3. Define the full-suite test command.
4. Define how run proofs execute: the CPU/GPU commands tasks should use, and the SLURM
   cluster `cluster-loop` targets for GPU runs.
5. Decide whether Codex CLI is mandatory or optional for `debug-loop`.
6. Tune the coverage threshold in `coverage-gate.md`.
7. Add repo-specific reviewer notes only where they are truly general.

Keep task files specific. Keep the skill generic.

