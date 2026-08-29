# Agent Tool Surface

The agent supports dedicated file operations plus a controlled terminal surface for inspection, development, testing, package management and version control.

Common terminal aliases include `type`, `cat`, `dir`, `ls`, `pwd`, `where`, `findstr`, `fc`, `tree`, `echo`, `python`, `pytest`, `pip`, `git`, `node`, `npm`, `npx`, `vite`, `dotnet`, `java`, `go`, `cargo` and related development commands.

Destructive shell operations remain blocked. File mutation should use the dedicated workspace-bounded tools so execution evidence can verify the result.