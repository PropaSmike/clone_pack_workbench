# Clone Pack Tools

Tools for building a Clone Engine pack: fighters, items and stages.

* **Clone Pack Workbench**, a window that does all of it.
* `make_clone_pack.py` writes the `config.json` for a fighter or item clone.
* `lint_clone_pack.py` checks a fighter or item pack.
* `lint_stage_pack.py` checks a stage pack and writes its `config.json`.

Needs Python 3.8 or newer. Works from wherever you unzip it.

## Starting

Double click `Clone Pack Workbench.cmd`, or run `python clone_pack_gui`. Open
your pack folder: the window reads what is there and fills itself in. Nothing
is written until you press a button, and every button prints the command it
ran. The **Help** tab (or F1) opens this guide.

**Working on** picks the kind you are editing: fighter, item or stage. A `*`
marks the kinds already on disk. **Part** picks which one, since a pack may
hold several of a kind; **New part** starts another and **Remove part** forgets
one without touching its files. **Add this part to the pack** creates its
folders and manifest.

Rules and settings no manifest can hold go in `clone_pack_gui.json` inside the
pack. The game never reads it.

Before the window writes over any file in the pack, it copies the old one to
`backups/<pack>/<date and time>/` beside the tools, keeping its path. The
**Backups** button opens that folder. Nothing in the pack is ever deleted.

## The tabs

**Identity**: what the clone is. Its base, names, costumes (any number; ones
the pack has no files for reuse its lowest), and for a stage
every `stage.toml` key. Writes `config.json` and `item.toml` or `stage.toml`,
keeping lines you added by hand. Articles (a fighter's projectiles and props)
are listed from the folder; click one, pick its source fighter and weapon, Add.

**Files**: what the folder ships against what `config.json` declares.

**Parameters**: pick a table, click a field, type a value, Add. A fighter has
`fighter_param`, `param_motion`, `common`, `param_thrown` and its own `vl.prc`.
An item has `item_common`, `item_owner_param` and its own `param.prc`. A stage
has none: it is tuned by the files it ships (see Stage packs).

**Lint**: runs the checker and lists what it found.

**Rust**: the code a `plugin.nro` needs, for every part: registration, articles
and every rule from Parameters. It follows the other tabs as you edit. Copy it
or save it as `registration.rs`. Items and stages need no code unless you want
behaviour the manifest cannot give.
With several parts of a kind, each part's functions carry its name
(`register_item_wawablade`).

## Values

Every table read from a prc file shows each name's value and bytes:

    hit_data/part           hash40   body   0x04dba80bb2
    param_cannonball/life   i32      180    0x000000b4

* A fighter's `vl.prc`: your own file's values. The Vanilla column is the
  game's default; a changed value is green.
* An item's `item_common`: put `item/common/param/param.prc` (extracted from
  the game) in **Values from** to see the base item's values.
* An item's `param.prc`: your own files, shown only. Change values in the file.

## Items that read a fighter's params

Some items take their numbers from a fighter (Steve's blocks read Steve's).
`item_owner_param` lists that fighter's values by name, with the bytes the
engine will write:

    param_pickelobject/life          i32   +518   3600   0x00000e10
    param_pickelobject/auto_damage   f32   +520   0.02   0x3ca3d70a

Click one, change the value, Add. The values are the game's defaults until the
fighter's own `vl.prc` is in the box. Change values that belong together: a
block lasting 600 frames needs `life` 600 and `auto_damage` 0.

## Engine versions

The window needs nothing installed. The Rust it writes needs Clone Engine
`0.2.1-beta.1` or newer for the item tables. A call the engine lacks prints
`was not applied: EngineUnavailable` in the log.

One item or stage per pack: `item.toml` and `stage.toml` are written flat,
which every engine reads. Two or more: one `[[item]]` or `[[stage]]` block
each, which needs an engine newer than `0.2.1-beta.1`. That engine skips the
whole file, so for it keep one item or stage per pack folder.

## Stage packs

Four `stage.toml` keys change what the game does: `resource_place`, `bgm`,
`bgm_setting_no` and `bgm_selector`. `content_donor`, `content_donor_tree` and
`carry_donor_scenery` only steer the tools when writing `config.json`.

A stage is tuned by its files. `stageparam_<place>.stprm` is a prc file:
camera, wind, colour correction, Final Smash cameras. `render/render_param.prc`
is the post-processing. Blast zones and collision are in the `.lvd`.

The game finds `.lvd` and `.stprm` by extension, so name those as you like;
yours replaces the donor's. Stages with numbered sets (Wuhu Island) keep the
donor's names. A `.stdat` is different: the donor's stage code asks for it by
its file name, so yours keeps the donor's name inside your own folder, for
example `stage/<place>/normal/param/zelda_greatbay.stdat` on a Great Bay
donor. The path is still yours, so the real Great Bay is untouched; a `.stdat`
named after your place is loaded and never read, and the linter says so. The
linter also warns when another installed mod replaces a file your stage
borrows from the game: that combination loads a black screen, so ship your
own copy.

## make_clone_pack.py

```
python make_clone_pack.py --base mario --clone mycharacter --out config.json
python make_clone_pack.py --kind item --base killsword --clone myitem --out config.json
```

| option | meaning |
| --- | --- |
| `--base <name>` | the vanilla fighter or item to clone |
| `--clone <name>` | your clone's resource name |
| `--kind fighter\|item` | default `fighter` |
| `--out <file>` | write here instead of printing |
| `--pack-dir <dir>` | your mod folder; its files are declared as its own |
| `--color-start <n>`, `--color-count <n>` | the costumes, default those the pack ships, else 8 |
| `--merge` | keep the entries in `--out` that belong to other parts |
| `--kirby-copy-donor <fighter>` | use that fighter's Kirby copy model |
| `--kirby-copy-suffix <name>` | copy name suffix, default `fitkirby` |
| `--kirby-copy-donor-suffix <name>` | the donor's own suffix, default `cap` |
| `--kirby-copy-motion-donor <fighter>` | also use that fighter's copy animations |
| `--verify-against <config.json>` | compare instead of writing |
| `--arc-index <dir>` | use another arc index |

With `--pack-dir`, a file the pack ships replaces the base's: its own `.eff`
means none of the base's effects or trails, a `model.numdlb` means none of the
base's model files in that folder, a sound bank means none of the base's. Base
animations, cameras and anything the pack has no folder for are still shared.
A costume the pack has no files for reuses the lowest one it ships, so a pack
shipping `c00` alone can declare 16 costumes. Past `c07` the base's `c00` is
borrowed.

It warns when the base owns files a clone cannot load; pick another base.

## lint_clone_pack.py

```
python lint_clone_pack.py "path/to/your/mod folder"
```

| option | meaning |
| --- | --- |
| `--arc-index <dir>` | use another arc index |
| `--cross-color-resource <name>` | an article folder every costume must have |

Prints `ERROR`, `WARN` and `INFO` lines. Exit code 1 on any `ERROR`. Checks
declared files, costumes, Kirby copies, cameras, and for each item that
`item.toml`, the base links and `param.prc` agree.

## lint_stage_pack.py

```
python lint_stage_pack.py "path/to/your/mod folder"
python lint_stage_pack.py "path/to/your/mod folder" --write-config
```

| option | meaning |
| --- | --- |
| `--write-config` | write `config.json` from the files on disk, then check |
| `--write-bank-id` | give the pack's sound bank a free id, then check |
| `--arc-index <dir>` | use another arc index |

Checks `stage.toml`, the trees, the sound bank and sequence, the stage-select
art, `config.json` and the mods installed beside the pack. Several stages are
checked in turn, and one `config.json` holds them all. `stage_bank_ids.py` and
`stage_sqb_tones.py` are data it reads.

## What else is in this folder

`clone_pack_gui/data/`: fighter, item and weapon kinds, music playlists, the
fighter param words, and `ParamLabels.csv`, which names the hashes in a prc.
`docs/`: the parameter field lists for game version 13.0.4.

`arc_index/`: the file and folder paths inside `data.arc` (13.0.4). Paths only,
no game data. Set `SSBU_ARC_INDEX` or pass `--arc-index` to use another.

`backups/`: appears once the window has written over a file. Safe to empty.

## Licence

GPL-3.0. See `LICENSE`.
