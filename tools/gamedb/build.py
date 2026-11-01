"""Build the game database from the REDkit files, the string database and the saves.

    py tools/gamedb/build.py                 everything, in order
    py tools/gamedb/build.py graph journal   only these stages (their tables are dropped first)
    py tools/gamedb/build.py --list          the stages

Output (git-ignored): db/w3db.sqlite, db/w3saves.sqlite and the LLM views under db/.
The schema and what every table means is in docs/DATABASE.md.
"""
import importlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

# order matters: later stages read earlier stages' tables
STAGES = ["strings", "graph", "journal", "scenes", "items", "saves", "semantic", "views"]


def tables_of(schema):
    out = []
    for line in schema.splitlines():
        s = line.strip().upper()
        if s.startswith("CREATE TABLE"):
            out.append(line.split("EXISTS")[-1].split("(")[0].strip())
    return out


def run(stages, verbose=True):
    con = common.connect()
    con.executescript(common.FILES_SCHEMA)
    for name in stages:
        mod = importlib.import_module(name)
        for t in tables_of(mod.SCHEMA):
            con.execute(f"DROP TABLE IF EXISTS {t}")
        con.executescript(mod.SCHEMA)
        t0 = time.time()
        if verbose:
            print(f"[{name}] building", flush=True)
        mod.build(con, verbose)
        con.commit()
        con.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (f"built:{name}", time.strftime("%Y-%m-%d %H:%M:%S")))
        con.commit()
        if verbose:
            print(f"[{name}] done in {time.time() - t0:.0f}s", flush=True)
    con.execute("PRAGMA optimize")
    con.close()


def main(argv):
    if "--list" in argv:
        print("\n".join(STAGES))
        return
    chosen = [a for a in argv if not a.startswith("-")] or STAGES
    bad = [s for s in chosen if s not in STAGES]
    if bad:
        raise SystemExit(f"unknown stage(s): {bad}; known: {STAGES}")
    run([s for s in STAGES if s in chosen])


if __name__ == "__main__":
    main(sys.argv[1:])
