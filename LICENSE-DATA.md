# Licence for the research and route data

In the source checkout, the `data/` folder holds two different kinds of material. They are not under
the same licence. The release package ships only the generated data; the legacy files below stay in
the checkout.

## Generated route data

These files are produced by the scripts in `tools/` from the game's own journal files, level tables and
phase graphs:

- `route.json`, `derived.json`, `quest_graph.json`, `quest_sections.json`, `route_overrides.json`
- `cutoffs.json`, `prereqs_review.json`, `prereq_relations.json`, `route_disputes.json`

They contain short quest-log names and objective strings read from the game. Those strings remain the
property of CD PROJEKT S.A. and are used here for identification and commentary; no ownership of the game's
text is claimed. To the extent the author can grant it, the compilation, annotations and reviewed decisions
in these files are made available under the MIT licence (see `LICENSE`). They are **not** a derivative of
the wiki and are **not** licensed under CC BY-SA.

## Legacy wiki-era research

These files are the older per-quest research. In the source checkout they are kept on disk for
comparison and are never loaded by the app; they are not part of the release package:

- `audit_*.json`, `guide_*.json`, `guide_alias.json` (removed from the checkout on 2026-11-01; still
  in git history under this licence)
- `legacy_route.json`, `legacy_events.json`, `legacy_feed.json` (frozen 0.1.9 inputs, used only as an
  acceptance corpus and never loaded by the app)

They are licensed under the **Creative Commons Attribution-ShareAlike 3.0 Unported** licence (CC BY-SA 3.0):
<https://creativecommons.org/licenses/by-sa/3.0/>

You may share and adapt them, including commercially, provided that you give appropriate credit, link to the
licence, indicate if changes were made, and distribute your contributions under the same licence.

## Attribution

The legacy research contains information from the contributors of **The Witcher Wiki**
(<https://witcher.fandom.com>), whose text is available under CC BY-SA 3.0.

## Changes made

The wiki text was read, summarised and reorganised into structured data (prerequisites, cutoffs, mappings to
quest journal files). This work was done with AI assistance (see `NOTICE.txt`). The result may contain errors
or omissions and has not been fully verified against the game.

## Other sources

Facts in the legacy research were also cross-checked against public walkthroughs (Gamer Guides, Fextralife,
ConsolePulse, TheGamer, GameBanshee). Those sites are not licensed for reuse and none of their text is
redistributed as such. If you are the owner of a consulted page and want a reference changed or removed,
please open an issue.

The program source code (everything outside `data/`) is licensed separately under the MIT licence, see
`LICENSE`.
