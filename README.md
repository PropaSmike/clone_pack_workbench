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

The window opens no larger than the screen and works down to 720x480: a form
taller than the window scrolls, hints wrap, and the divider above **Output**
drags.

## Two ways to register

A pack with a plugin registers from code: the **Rust** tab writes a `lib.rs`
whose `main` builds a `Manifest` (or `ItemManifest`) from the other tabs and
calls `register`. A pack with no plugin registers from `fighter.toml`,
`item.toml` or `stage.toml`, which the **Identity** tab writes. Both carry the
same keys; if a pack has both, the engine reads the file first and the
manifest returns that kind.

A pack made from a one-slot mod keeps its plugin: tick **Plugin keeps its CSK
and ParamConfig code**. The manifest then says `own_css()` (the file
`css = false`), the plugin's `add_chara_db_entry_info` publishes the select
entry and its `param_config::update_*` calls set the `vl.prc` values, with
the clone's names in place of the base's. The Rust tab writes both calls.

## The tabs

**Identity**: the base, names, costumes (any number; ones the pack has no
files for reuse its lowest), articles (listed from the folder; click one,
pick its source fighter and weapon, Add) and, for a stage, every
`stage.toml` key. Writes `config.json` and the manifest file, keeping lines
you added by hand: the flat keys, `[[article]]`, `[kirby]` and `[params]`; a
`[[kirby.motion]]` table you wrote stays where it is.

**Rename files** changes a part's name everywhere the pack carries it: type
the new name, click the button, check the two names. Every folder and file
whose name holds the old one is renamed (`fighter/<old>/`, `ef_<old>.eff`,
`vc_<old>_c00`, `chara_0_<old>_00`, `<old>.marker`, Kirby's `copy_<old>` and
`<old>d00...` animations), and every line of `config.json`, the manifests,
`msg_name.xmsbt` and the saved state that mentions it is edited, whole word
only (`wawa` never touches `wawaman`). Files that hold the name inside their
bytes (`plugin.nro`, `.eff`, `.bntx`, `.prc`, sound banks) are listed, not
changed: rebuild the plugin with the new name, edit the others by hand.

**Files**: what the folder ships against what `config.json` declares.

**Parameters**: pick a table, click a field, type a value, Add. Which syntax
each table takes:

| Table | Syntax |
|---|---|
| a fighter's own `vl.prc` (`param_special_*`, ...) | ParamConfig: `param_config::update_*` on the Rust tab with the plugin flag, `.param(..)` on the Manifest or `[params]` without it |
| `fighter_param`, `param_motion`, `common`, `param_thrown` | engine: `.param(..)` on the Manifest or `[params]`; the game reads these past ParamConfig |
| an item's `item_common`, `item_owner_param` | `.common(..)` / `.owner_param(..)` on the ItemManifest or `[common]` / `[owner_params]`; label and name fields are Rust calls |
| an item's own `param.prc`, a stage | the files themselves |

Lists inside `vl.prc` (`hit_data`, ...) are not rules: ship your own
`vl.prc` under every costume.

**Lint**: runs the checker and lists what it found.

**Optimize**: **Scan** lists every costume file whose bytes equal a lower
costume's twin (models, textures, motions, cameras, sound banks, Kirby hats)
with the size it costs; **Apply** takes those copies out of the pack (each
kept in backups) and adds `share-to-added` lines to `config.json` so the name
still loads from the lower costume's file. `.marker` files, manifests and the
plugin are never touched; a name `config.json` already aliases is left as it
is; empty folders are dropped. Run **Lint** afterwards.

**Rust**: one `lib.rs` for the pack, following the other tabs as you edit;
copy it or save it as `lib.rs`. Every argument carries a comment. Per
fighter: `fighter!`, a `<NAME>_COSTUMES` constant that drives the manifest,
the CSK maps and the ParamConfig slots, the `Manifest` and `register` in
`main`, then the Smashline agents (the fighter, one per article, Kirby when
the clone has copy statuses). With the plugin flag: `register_css_entry`
(CSK's call, one layout per costume) and `register_params` (ParamConfig's
calls with the clone's kind). Per item: `item!`, the `ItemManifest` and
`register`, and `register_item_labels` for the label and name fields. With
several parts of a kind, each part's functions carry its name
(`register_css_entry_wawa`). Stages need no code.

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

The window needs nothing installed. The Rust it writes needs the engine that
carries the `v2` module (`Manifest`, `fighter!`, `item!`); so do
`fighter.toml` and the `[common]` and `[owner_params]` tables of `item.toml`.
An older engine ignores them; a pack for it registers by hand (the engine's
`DEPRECATED.md`). A call the engine lacks prints
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
donor's names. A `.stdat` is asked for by its file name, so yours keeps the
donor's name inside your own folder, for example
`stage/<place>/normal/param/zelda_greatbay.stdat` on a Great Bay donor; a
`.stdat` named after your place is loaded and never read, and the linter says
so. The linter also warns when another installed mod replaces a file your
stage borrows from the game: that combination loads a black screen, so ship
your own copy.

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
| `--pack-dir <dir>` | your mod folder; its files are declared as its own; with a `fighter.toml` inside, `--base`, `--clone` and the costume range come from it and a flag that disagrees is an error |
| `--color-start <n>`, `--color-count <n>` | the costumes, default those the pack ships, else 8 |
| `--merge` | keep the entries in `--out` that belong to other parts |
| `--kirby-copy-donor <fighter>` | use that fighter's Kirby copy model instead of the base's |
| `--kirby-copy-suffix <name>` | copy name suffix, default `fitkirby` |
| `--kirby-copy-donor-suffix <name>` | which of the donor's copy models is the hat, default found from its files |
| `--kirby-copy-motion-donor <fighter>` | also use that fighter's copy animations |
| `--verify-against <config.json>` | compare instead of writing |
| `--arc-index <dir>` | use another arc index |

The config mirrors the base's own directory tree from
`arc_index/arc_dir_files.tsv`: each directory the game loads for a costume
(the costume itself, `camera`, `result`, `movie`, `kirbycopy`, and Joker's
`append`) becomes the clone's, with the same files under the clone's names,
and each link (`cmn`, `camera`, the Kirby copy leaves) stays a link to the
base's. Effect files sit in every costume group. The base's Kirby hat is the
clone's by default, its `flip.prc` and `update.prc` included; a pack that
ships its own copy model, or names a donor, replaces it.

With `--pack-dir`, a file the pack ships is declared where the base keeps its
counterpart (a result-screen prop goes to `result/cNN`) and replaces the
base's: its own `ef_<clone>.eff` means none of the base's effects or trails, a
`model.numdlb` means none of the base's model files in that folder, a copy
model means none of the base's hat. Animations, cameras and sound files are
borrowed one by one, so a voice bank without its `.tonelabel` gets the base's,
and the crowd chant is the base's until you ship `vc_<clone>_cheer_cNN`. A
costume the pack has no file for takes it from the nearest costume below that
has it. Past `c07` the base's `c00` is borrowed. What cannot carry another
name is loaded from the base by the engine at match load: a `finalsmash/`
tree, Joker's cut-in effect under `append/effect/`, and the Final Smash
movies of Joker, Hero, Sephiroth and Steve under `prebuilt:/movie/`.

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
`item.toml`, the base links and `param.prc` agree. It reads the share tables
the way ARCropolis does: a target the pack also ships is an error (your file
never loads), so is a source that exists nowhere, a link to a directory that
does not exist, a linked directory given members, and a costume directory
that exists only as the parent of a link. A one-slot effect name
(`ef_<clone>_c00.eff`) with no `ef_<clone>.eff` is an error; an effect model
missing from some costume groups is a warning. A `fighter.toml` is read with
the engine's rules (an unknown key or table is an error with its line) and
checked against the folders: the base is a fighter, every `[[article]]` has
its files, the costume count covers the body model, a `[kirby]` table has a
copy model, `staffroll = true` has its texture. When the pack folder holds
its Rust source under `src/`, a custom work id past a base's `_TERM` is
warned about: a clone's work arrays are its base's size.

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

`arc_index/`: the file and folder paths inside `data.arc` (13.0.4), and
`arc_dir_files.tsv`, which files each fighter and item directory loads. Paths
only, no game data. Set `SSBU_ARC_INDEX` or pass `--arc-index` to use another.

`backups/`: appears once the window has written over a file. Safe to empty.

## Licence

GPL-3.0. See `LICENSE`.
