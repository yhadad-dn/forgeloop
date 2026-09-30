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
