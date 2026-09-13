# AGENTS.md - Project Management Rules

## Always do this at the start of every task

1. Read `.ai/PROJECT_CONTEXT.md`
2. Read `.ai/PLAN.md`
3. Read `.ai/TASKS.md`
4. Read `.ai/PROGRESS.md`
5. Read `.ai/DECISIONS.md` if it exists
6. Read `.agents/CONTEXT.md` for project vocabulary

## Main responsibilities

- Understand the current project state
- Select the next logical task from `.ai/TASKS.md`
- Before changing files, explain your plan and wait for user approval
- Keep tasks small and testable
- Avoid unnecessary changes
- Do not refactor unrelated code unless explicitly asked

## After completing a task

1. Update `.ai/TASKS.md` (mark task as done)
2. Update `.ai/PROGRESS.md` (add completed task)
3. Update `.ai/DECISIONS.md` if a major decision was made
4. Suggest a git commit message

## Safety rules

- Never run destructive commands without explicit approval
- Never run: rm -rf, git push --force, sudo, chmod -R, chown -R
- Never expose API keys, tokens, passwords, or secrets
- Do not modify .env files unless explicitly approved

## Available Skills

You have access to these engineering skills in `.agents/skills/`:
- `/grill-me` - Interview user about requirements
- `/tdd` - Test-Driven Development workflow
- `/diagnosing-bugs` - Systematic bug debugging
- `/code-review` - Code quality review

## Git workflow

- Before major changes, check git status
- After a successful task, suggest a commit message
- Do not push to remote unless explicitly requested

## Response style

- Be concise
- First explain what you understood
- Then show the plan
- Wait for approval before editing important files
- After completion, update project management files
