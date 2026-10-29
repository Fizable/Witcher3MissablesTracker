# endings checker fixtures

`base/` is a small, internally consistent set of inputs for `tools/endings.py`:

- `endings.json` - one guided target with two requirements and one `not_guided_yet` target
- `branches.json` - the two scene choices those rows name
- `route.json` - the two route steps
- `quest_index.json` - the quest facts the requirements name
- `coverage.json` - a row for the `bob` pack
- `exclusive.json` - no edges

The ids, labels, scene paths and locIds are test values, not game data. `tools/test_endings.py`
copies this set to a temporary directory and changes one field per negative case, so a failure
names the rule it is testing. The temporary string database is created by the test, not checked in.

Run the suite with:

```
py tools/test_endings.py -v
```
