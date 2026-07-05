# Team Sandbox — where everyone plays together

Ross 2026-07-03 16:20Z: "you can all play together lol" — shared scratch space
for the whole Council. Claude, Wren, Forge, Sage, Mira, Pip, Hermes, Auger,
iQuest, iris, receptionist, TP, Acer — anyone drops experiments here.

## THE ONE RULE — "Sandbox Exit Gate"

Ross 2026-07-03 16:21Z verbatim: "anything out of the sandbox much reach 100 
percent compatable and working before it can leave any sandbox for anyone 
then can be coded or used"

Before ANY sandbox artifact moves to a production path:
  1. It must run WITHOUT error in the sandbox first (100% working there).
  2. It must be COMPATIBLE with the target file/module it'll land in
     (imports resolve, function signatures match, no missing deps).
  3. It must be TESTED — run a smoke test that exercises the actual code path.
  4. Only then does it graduate: copy to production, auto-backup fires,
     ship notice goes to F47 with the sandbox path + test evidence.

Anything failing (1) (2) (3) stays in the sandbox and either gets fixed or
gets dropped. The sandbox is a graveyard for what didn't work AND a workshop
for what will.

## Layout

  data/team_sandbox/            — shared workspace
  data/claude_sandbox/          — Claude's private scratch  
  data/wren_sandbox/            — Wren's private scratch
  _archive/wren_backups/        — auto-backups from wren_edit_file direct mode
  _archive/claude_backups/      — auto-backups from Claude's ships (future)
