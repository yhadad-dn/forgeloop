# ForgeLoop Repo Configuration

Copy to `.claude/forgeloop.md` in your repo and edit. ForgeLoop skills read this file
before Stage 0; its values override the skills' defaults. Delete lines you don't need.

## Commands

- full_suite: `python3 -m pytest tests/ -q`
- targeted_test: `python3 -m pytest {test_path} -q`
- coverage: `python3 -m pytest --cov={module} --cov-report=term-missing {test_path}`

## Gates

- coverage_threshold: 70
- test_file_patterns: `tests/`, `test_*.py`, `*_test.py`, `conftest.py`
- forbidden_paths: `results/`, `outputs/`, `*.ckpt`
- codex_gate (debug-loop): required | fallback: <describe the explicit fallback>

## Run proof defaults

- gpu_partition: XAI
- default_timeout: 00:30:00

## Cluster (cluster-loop)

- node_map: ~/.claude/forgeloop/cluster_node_map.md
- subnet_router: 100.109.84.43
- slurm_host: dn@172.30.160.158   # des2-2; SLURM isn't installed on workstations
- job_name: ^yhadad_               # --mine keeps only matching jobs (the dn account is shared)

## Conventions

Repo-specific conventions go here. The ForgeLoop session hook adds this section to
every session in this repo, after the team defaults and your personal
`~/.claude/forgeloop/conventions.md`. Delete the section if you have none.
