# Security

Do not report secrets in public issues.

ForgeLoop is a workflow package. Security-sensitive areas include:

- shell command execution in generated prompts;
- filesystem writes and overwrite behavior;
- copied project policies that mention private infrastructure;
- reviewer prompts that include sensitive diffs.

If you find a security issue, contact the maintainer privately or open a minimal issue
without secrets.

