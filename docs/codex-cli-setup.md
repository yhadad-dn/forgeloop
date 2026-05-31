# Codex CLI Setup

ForgeLoop's Stage C expects an external review command. The default template uses:

```bash
codex exec review -m "gpt-5.5"
```

If your environment uses a different model or command, edit:

```text
skill/.claude/skills/implement-loop/review-gates.md
```

If Codex is unavailable, make your fallback explicit in repo policy. Do not silently treat
an unavailable external review as a pass.

