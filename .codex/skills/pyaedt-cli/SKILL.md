---
name: pyaedt-cli
description: "Use when Codex needs to interact with Ansys Electronics Desktop through the PyAEDT command line: inspect or start AEDT sessions, manage open projects and designs, run Python or IronPython scripts in AEDT, export screenshots or design configuration, install PyAEDT panels, open PyAEDT documentation, or troubleshoot pyaedt CLI usage from a workspace or virtual environment."
---

# PyAEDT CLI

Use this skill for terminal-driven AEDT automation through the `pyaedt` CLI. Use `pyaedt-aedt` instead when the task is mainly to write direct PyAEDT API code or reason about solver classes and methods.

## Preflight

Resolve the CLI before running commands:

```powershell
pyaedt --json version
```

If `pyaedt` is not on `PATH`, try the workspace virtual environment:

```powershell
.\.venv\Scripts\pyaedt --json version
```

On Linux or macOS, try:

```bash
.venv/bin/pyaedt --json version
```

If the command is unavailable, tell the user to install PyAEDT with CLI dependencies:

```bash
pip install "pyaedt[all]"
```

Use `--json` for non-interactive commands and parse the result before acting:

```json
{"status": "ok", "data": {}}
{"status": "error", "error": "message"}
```

If `status` is `error`, report the error and stop that workflow.

## Safety

- Inspect existing sessions with `pyaedt --json session list` before starting a new AEDT instance.
- Ask before stopping AEDT sessions, closing projects, overwriting exported files, or running long solves.
- Use a task-specific temporary directory for generated scripts, screenshots, configs, and intermediate exports unless the user requests a destination.
- Do not assume there is an active project or active design. Use explicit `--project`, `--design`, and `--port` when needed.
- If CLI behavior differs from this skill, run `pyaedt --help` or `<command> --help` and follow the installed CLI.

## CLI Shape

General form:

```bash
pyaedt [--json] <command-or-group> [subcommand] [options]
```

Main commands and groups:

- `version`: show the PyAEDT version.
- `aedt-versions`: list installed AEDT versions.
- `session`: start, list, stop, or attach to AEDT sessions.
- `project`: list, open, create, save, and close AEDT projects and designs.
- `run`: execute a script inside AEDT.
- `export`: export screenshots or design configuration.
- `panels`: install PyAEDT panels into AEDT.
- `doc`: open PyAEDT documentation resources.
- `test-config`: manage `tests/local_config.json`.

Do not invent command groups. Check help when an operation is not listed:

```bash
pyaedt --help
pyaedt session --help
pyaedt project --help
pyaedt run --help
pyaedt export --help
```

## Session Workflow

Discover sessions first:

```bash
pyaedt --json session list
```

Decision rules:

- If no usable session exists and the user wants automation, start one.
- If exactly one usable session exists, reuse its port.
- If multiple sessions exist, present the ports, versions, and PIDs, then ask which to use.

Start AEDT:

```bash
pyaedt --json session start --version 2026.1 --non-graphical
pyaedt --json session start --version 2026.1 --port 50051
pyaedt --json session start --port 0
```

Stop AEDT only when requested or confirmed:

```bash
pyaedt --json session stop --port 50051
pyaedt --json session stop --all
```

Use `session attach` for exploratory or debugging work:

```bash
pyaedt session attach --port 50051
pyaedt session attach --port 50051 --project MyProject --design MyDesign
```

Inside an attached interactive console, prefer one-line commands. Wrap multi-line Python blocks in `exec("...\n...")`; raw pasted indentation often fails in interactive consoles.

## Project Workflow

Project commands require `--port`.

Inspect open projects and designs:

```bash
pyaedt --json project list --port 50051
```

Open a project:

```bash
pyaedt --json project open "D:/path/to/project.aedt" --port 50051
```

Create a project:

```bash
pyaedt --json project create --port 50051 --project DemoProject
```

Create a design in a project:

```bash
pyaedt --json project create --port 50051 --project DemoProject --design Filter1 --type Hfss
```

Supported design types include:

```text
Hfss, Maxwell2d, Maxwell3d, Q3d, Q2d, Icepak, Circuit, TwinBuilder,
Mechanical, Emit, Rmxprt, Hfss3dLayout, MaxwellCircuit
```

Save or close:

```bash
pyaedt --json project save --port 50051
pyaedt --json project save --port 50051 --path "D:/path/to/copy.aedt"
pyaedt --json project close --port 50051 --project DemoProject
```

Ask before closing projects or saving over user files.

## Script Execution

Use `run` for defined, repeatable automation:

```bash
pyaedt --json run "D:/temp/generated_script.py" --port 50051
```

Use IronPython only when the script targets the native AEDT API:

```bash
pyaedt --json run "D:/temp/native_script.py" --ironpython --port 50051
```

For generated scripts:

- Determine the target port first.
- Use a temporary script path unless the user asks for a repository artifact.
- Write scripts intended for existing AEDT sessions with `new_desktop=False` or the equivalent PyAEDT constructor option.
- Report script path, target port, and output artifacts.

## Export Workflow

Export screenshots:

```bash
pyaedt --json export screenshot --port 50051 --path "D:/temp/preview.jpg"
pyaedt --json export screenshot --port 50051 --project DemoProject --design Filter1 --path "D:/temp/preview.jpg"
```

Export design configuration:

```bash
pyaedt --json export config --port 50051 --output "D:/temp/config.json"
pyaedt --json export config --port 50051 --project DemoProject --design Filter1 --output "D:/temp/config.json"
```

If selection is ambiguous, inspect with `project list` and ask for the missing project or design.

## Panels And Docs

Install panels only when the user asks:

```bash
pyaedt panels add --personal-lib "C:\Users\username\AppData\Roaming\Ansoft\PersonalLib"
pyaedt panels add --personal-lib "C:\Users\username\AppData\Roaming\Ansoft\PersonalLib" --reset
pyaedt panels add --personal-lib "C:\Users\username\AppData\Roaming\Ansoft\PersonalLib" --minimal
```

Use documentation shortcuts when the task is about discovery:

```bash
pyaedt doc
pyaedt doc getting-started
pyaedt doc installation
pyaedt doc user-guide
pyaedt doc api
pyaedt doc examples
pyaedt doc github
pyaedt doc issues
pyaedt doc search hfss mesh
```

## Common Flows

Start, inspect, and stop:

```bash
pyaedt --json session start --version 2026.1 --port 50051
pyaedt --json session list
pyaedt --json project list --port 50051
pyaedt --json session stop --port 50051
```

Run automation against an existing or new session:

```bash
pyaedt --json session list
pyaedt --json session start --non-graphical --port 50051
pyaedt --json run "D:/temp/generated_script.py" --port 50051
```

Export design data:

```bash
pyaedt --json project list --port 50051
pyaedt --json export screenshot --port 50051 --project DemoProject --design Filter1 --path "D:/temp/filter1.jpg"
pyaedt --json export config --port 50051 --project DemoProject --design Filter1 --output "D:/temp/filter1.json"
```
