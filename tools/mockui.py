"""Build ui/mock/ from one real save so the browser can exercise the app without Tauri.

This is a development aid, not part of the extraction pipeline and not part of the release: the
output directory is git-ignored. It runs the built exe headlessly with an isolated APPDATA and a
saves folder the caller copied a save into, so the user's own settings and save folder are never
read or written.

    py tools/mockui.py --exe target/debug/witcher3-missables-tracker.exe \
        --saves C:\\Temp\\w3profiles\\median\\saves --out ui/mock

Files written: view.json, cards.json, details.json (one entry per route step, so the detail pane
opens), verdicts.json (the short names whose detail carries a verdict, for search answers) and
search_index.json (the quest names and statuses the search box filters). `view.json` and
`cards.json` are the app's own payloads; nothing here invents a warning, a status or a name.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(exe, args, cwd, env):
    p = subprocess.run([str(exe), *args], cwd=str(cwd), env=env, capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit(f"{exe} {' '.join(args)} failed: {p.stderr.strip()}")
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True, help="built tracker exe")
    ap.add_argument("--saves", required=True, help="folder holding the copied .sav fixture")
    ap.add_argument("--out", default=str(ROOT / "ui" / "mock"))
    ap.add_argument("--game", default=os.environ.get("W3_GAME_DIR", r"C:\Steam\steamapps\common\The Witcher 3"))
    ap.add_argument("--settings", help="an existing profile's settings.json (for goals and guidance)")
    ap.add_argument("--limit", type=int, default=0, help="debug: detail only the first N steps")
    a = ap.parse_args()

    exe = Path(a.exe).resolve()
    saves = Path(a.saves).resolve()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if not any(saves.glob("*.sav")):
        sys.exit(f"no .sav in {saves}")

    tmp = Path(tempfile.mkdtemp(prefix="w3mockui-"))
    app = tmp / "appdata" / "Witcher3MissablesTracker"
    app.mkdir(parents=True)
    settings = json.loads(Path(a.settings).read_text(encoding="utf-8")) if a.settings else {}
    settings.update({"saves_dir": str(saves), "game_dir": a.game, "setup_v1": True})
    (app / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    env = dict(os.environ, APPDATA=str(tmp / "appdata"))

    run(exe, ["--view", str(out / "view.json")], ROOT, env)
    run(exe, ["--cards", str(out / "cards.json")], ROOT, env)
    view = json.loads((out / "view.json").read_text(encoding="utf-8"))
    steps = view["steps"]
    ids = [s["id"] for s in steps]
    if a.limit:
        ids = ids[: a.limit]

    details = {}
    for i, sid in enumerate(ids, 1):
        dest = tmp / "detail.json"
        run(exe, ["--detail", sid, str(dest)], ROOT, env)
        details[sid] = json.loads(dest.read_text(encoding="utf-8"))
        if i % 50 == 0:
            print(f"detail {i}/{len(ids)}", flush=True)

    # A search hit with no step id answers through check_quest(short); the detail it would open
    # already carries the same save-aware verdict, so reuse it rather than guessing one.
    verdicts = {}
    shorts = {}
    for s in steps:
        stems = s.get("stems") or []
        short = stems[0] if stems else ""
        shorts[s["id"]] = short
        d = details.get(s["id"])
        if short and d and isinstance(d.get("verdict"), dict):
            verdicts[short] = d["verdict"]

    index = []
    for s in steps:
        short = shorts.get(s["id"], "")
        if not short:
            continue
        index.append({
            "short": short,
            "display": s.get("game_title") or s.get("title") or short,
            "status": s.get("status") or "Not started",
            "step": s["id"],
        })

    for name, doc in (
        ("details.json", details),
        ("verdicts.json", verdicts),
        ("search_index.json", index),
    ):
        (out / name).write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {len(details)} details, {len(verdicts)} verdicts, {len(index)} search rows to {out}")
    print(f"fixture save: {view['save']['name'] or '(none)'}; profile: {tmp}")


if __name__ == "__main__":
    main()
