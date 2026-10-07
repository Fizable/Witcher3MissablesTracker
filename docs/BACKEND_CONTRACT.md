# Backend <-> UI contract (Tauri v2, `withGlobalTauri: true`)

UI calls `window.__TAURI__.core.invoke(cmd, args)` and listens with `window.__TAURI__.event.listen('view', e => render(e.payload))`.
The backend emits `view` (same payload as `get_view`) whenever a new save appears or something changes. All JSON keys are snake_case.

## Commands
- `get_view() -> View`
- `get_detail(id: string) -> Detail`
- `search(q: string) -> SearchHit[]`            (q length >= 2)
- `check_quest(short: string) -> Verdict`
- `toggle_tick(id: string) -> View`             (manual tick / override)
- `set_level(level: number) -> View`
- `set_pin(pin: boolean) -> void`               (always on top)
- `open_url(url: string) -> void`

## View
```
{
  "save": { "name": "QuickSave_...sav", "age_secs": 140, "error": "" },
  "level": 0,                       // 0 = unknown
  "sections": ["White Orchard", ...],           // play order
  "steps": [ Step, ... ],                        // every route node, play order
  "todo": ["ve_invite", ...],                    // ordered ids for DO NEXT (full list)
  "holdoff": [ { "kind": "event"|"hold", "name": "...", "status": ""|"Active"|"Not started", "why": "...", "missing": [ {"id","title"} ] } ],
  "alerts":  [ { "level": "stop"|"warn", "msg": "...", "missing": [ {"id","title"} ] } ],
  "objectives": { "<step id>": ["Find daughter", ...] }   // readable objectives active in the quest log right now
}
Step = {
  "id","title","section","lv" (string, may be ""), "status": "Done"|"Active"|"Not started"|"Failed"|"Assumed",
  "manual": bool,            // true = the save cannot show it; the user ticks it
  "opt": bool,               // optional extra, not on the main route (hide from progress list)
  "conf": "high"|"med"|"low"|"", "note": "...",      // note = the "DON'T MISS" text
  "start": "where/how to start it (wiki text, may be empty)",
  "kind": "main"|"side"|"gwent"|"dlc"|"contract"|"treasure",
  "conditional": bool,       // only exists in some playthroughs
  "locked": [ {"id","title"} ],   // hard prerequisites not done
  "held": null | { "why": "...", "blockers": [ {"id","title"} ] },
  "lost": bool
}
```

## Detail
```
{ "step": Step, "kb": null | { "title","start","needs_before":[{"quest","strength":"hard"|"soft","why"}],
    "must_finish_before":[{"event","why"}], "fails_or_locks_when": "...", "unverified":[...], "sources":[urls] },
  "guide": null | { "summary","available_when","how_to":[...],"missable","sources":[...],"verified":"yes"|"partial"|"no" },
  "tracking": "text describing how the step is tracked", "overridden": bool }
```

## Search / Verdict
```
SearchHit = { "short": "mq1015lynch", "display": "Lynch Mob", "status": "Not started" }
Verdict   = { "verdict": "safe"|"warn"|"stop"|"info", "headline": "...", "details": ["..."], "display": "Lynch Mob" }
```
