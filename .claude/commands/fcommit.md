# Fast commit task

- Automatically group the changed files into separate, logical commits. Keep the grouping criteria implicit—let the LLM decide what belongs together.
- For each group, generate **3** commit message suggestions following the same format as the commit task.
- Automatically use the **first** suggestion without asking the user.
- Immediately commit the group with `git commit -m "<first-suggestion>"`.
- Repeat until all changes are committed.
- All other behaviors remain the same as the commit task (format, package names, staged files only).
- **Do NOT** add Claude co-authorship footer to commits
- Push the commits to the remote repository
