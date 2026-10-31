# Clone Pack Tools

Tools for building a Clone Engine pack: fighters, items, stages, menus, Mii
hats and outfits, and enemies.

* **Clone Pack Workbench**, a window that does all of it.
* `make_clone_pack.py` writes the `config.json` for a fighter or item clone.
* `lint_clone_pack.py` checks a fighter or item pack.
* `lint_stage_pack.py` checks a stage pack and writes its `config.json`.
* `lint_menu_pack.py` checks a menu pack against every pack installed beside it.
* `lint_mii_pack.py` checks a Mii parts pack and writes its `config.json`.
* `lint_enemy_pack.py` checks an enemy pack and writes its `config.json`.

Needs Python 3.8 or newer. Works from wherever you unzip it.

## Starting

Double click `Clone Pack Workbench.cmd`, or run `python clone_pack_gui`. Open
your pack folder: the window reads what is there and fills itself in. Nothing
is written until you press a button, and every button prints the command it
ran. The **Help** tab (or F1) opens this guide.

- **Working on** picks the kind you are editing: fighter, item, stage, menu,
  Mii or enemy.
  A `*` marks the kinds already on disk.
- **Part** picks which one, since a pack may hold several of a kind. **New
  part** starts another; **Remove part** forgets one without touching its
  files.
- **Add this part to the pack** creates its folders and manifest.

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
manifest returns that kind. A menu pack registers from `menu.toml` alone; its
plugin, when it has one, answers its Lua and sets battles up. A Mii pack is
`mii.toml` and its files, with no plugin.

A pack made from a one-slot mod keeps its plugin: tick **Plugin keeps its CSK
and ParamConfig code**. Then:

- the manifest says `own_css()` (in the file, `css = false`);
- the plugin's `add_chara_db_entry_info` publishes the select entry and its
  `param_config::update_*` calls set the `vl.prc` values, with the clone's
  names in place of the base's; the Rust tab writes both calls;
- the select row copies the base's (`clone_from_ui_chara_id`) and sets every
  value with `Overwrite`: World of Light lists only copied rows, and on a
  copied row CSK keeps the base's value over an `Optional` one.

## The tabs

### Identity

The base, names, costumes (any number; ones the pack has no files for reuse
its lowest) and articles (listed from the folder; click one, pick its source
fighter and weapon, Add). The **Write** buttons write `config.json` and the
manifest, keeping lines you added by hand: the flat keys, `[kirby]`,
`[params]` and any `[[kirby.motion]]` or `[[kirby.mesh]]` table you wrote.

Each table panel reads back what the file holds. Add checks a row with the
engine's rules and replaces the row with the same name (or status, or article
and vertex); click a row to change it.

For a fighter:

- **Articles**: a **Platform (.lvd)** file in the article's model folder
  makes it a platform (`lvd`). **Article hurtboxes** and **Article platform
  vertices** list each article's `[[article.hurtbox]]` and
  `[[article.lvd_vertex]]` tables.
- **Switches with**: the one or two other clones sharing the player slot
  (`switch`).
- **Partner**: blank for the base's default, `none`, `copy` or another
  clone's name (`partner`).
- **Command inputs**: the game's own commands (`[commands] vanilla`), their
  tuning and the clone's own `[[command]]`s. Click one to change it; Add
  replaces the one of that name. Build an input on the stick: each click adds
  the direction under the pointer, the middle is neutral, right click or
  Undo takes the last one off. Its zones follow the stick ranges and the
  neutral threshold. **Faces the opponent** turns the fighter toward its
  opponent in a 1-on-1.
- **Float**: Peach's float, written into the plugin. Blank fields keep her
  values; **Throws mid-float** is the held item down special throws (her
  turnip is `peachdaikon`). Saved in `clone_pack_gui.json`, since
  `fighter.toml` has no float. A Peach or Daisy clone floats already.
- **Glide**: Brawl's glide with Meta Knight's, Pit's or Charizard's values,
  written into the plugin and saved in `clone_pack_gui.json`. It starts from
  the float's input, so ticking one clears the other.
- **Tether**: a donor's air tether and ledge grab (`[tether]`) and ledge
  boxes of your own (`[[tether.box]]`). It names the donor articles to mint.
- **HUD**: a borrowed HUD or the pack's own layout (`[hud]`).
- **Move list pages** and **Picture pages**: `[move_list]`, extra move list
  pages past the game's four, and the ones that show a picture.
- **Grab rules**, **Motions on every fighter** and **Partner follow
  params**: `[[grab]]`, `[[global_motion]]` and `[partner_params]`. A grab's
  status or **Then** can be `own N`, your fighter's own status N.
- **Kirby copy motions** and **Kirby hat pieces**: `[[kirby.motion]]` and
  `[[kirby.mesh]]`. **Extra copy model** is `model` in `[kirby]`. A copy
  motion keeps the keys it has no column for.
- **Make Final Smash folders** makes `finalsmash/<name>/shared/` and
  `prebuilt;/movie/fighter/<name>/c00`; **Write config.json** declares what
  you put there, and the Rust tab shows the calls that start them.

For a stage, every `stage.toml` key, and:

- **Moving platform sets** (`dynamic_collisions`) and **Paused motions**
  (`paused_motions`).
- **Ladders**, **Barrel cannons**, **Springs** and **Doors**, written after
  the stage's keys. A table you did not change keeps its lines and comments.

For an item:

- **Base item** lists Assist Trophies, Pokemon and bosses too.
- **Family members**: every member's resource name in the base family's
  order, this item first, written to `item.toml` as `members`. **Fill
  family** writes them from the base: Galleom's family is Galleom, its
  missile and its shockwave, so a clone named `boss` gets `boss`,
  `boss_missile` and `boss_shockwave`.
- Each member loads its own files from `item/<member>/`, an Assist's from
  `assist/<member>/`.

For a menu:

- **Script folder**: `ui/script/menu/<this>/`.
- **Modes**, **Sequences** (`[[sequence]]`), **Layouts**, **Preloads** and
  **Script patches**: a table each. **Write menu.toml** rewrites them,
  keeping only the comments above the first.
- **Runs as** is one of the game's modes by name: `melee_normal` (Smash),
  `other_training` (Training) and the rest in the engine's
  `docs/wiki/MENUS.md`. A sequence needs only an **Id**; the engine picks
  its code.
- **Compile Lua** builds the `.lua` files in **Lua sources** (keep them
  outside the pack) into `ui/script/menu/<folder>/` with **SSBU luac**, or
  `SSBU_LUAC` when blank.
- **Ready-made mode** writes a mode's Lua into **Lua sources** and its row
  into **Modes**, with no plugin: `duel` (your fighter against a CPU,
  straight into the battle), `pick` (the players pick fighters, then fight on
  **Stage**), `boss` (the game's boss battle against **Boss**, a boss clone's
  name included) or `movie` (a `stream:/movie/...` WebM full screen).

For an enemy:

- **Name** and **Base enemy** go in `enemy.toml`; the engine clones it at
  boot.
- The other fields are for the Rust tab's plugin: when the enemy comes out,
  where, how long it stays, and Nabbit's walk speed. Off its home stage only
  Flying Man fights by itself, so a Nabbit clone gets the Rust tab's walk.
- **Write config.json** lists `enemy/<name>/` and `effect/enemy/<name>/`
  from what the pack ships. **Fix motion list** makes `motion_list.bin` name
  the enemy's own folder, or it plays the base's animations.

For Mii hats and outfits:

- **Hats** and **Outfits**: a table each. **Base** is the game's hat or outfit
  whose row the part copies; the other columns change that copy.
- **Write mii.toml** rewrites them. **Write folders to config.json** lists
  each part's folders and files from what the pack ships.

**Rename files** changes a part's name everywhere the pack carries it: type
the new name, click the button, check the two names.

- Every folder and file whose name holds the old one is renamed:
  `fighter/<old>/`, `ef_<old>.eff`, `vc_<old>_c00`, `chara_0_<old>_00`,
  Kirby's `copy_<old>`, `<old>body` animation folder and
  `vc_kirby_copy_<old>`.
- Files below a costume folder (`c00`, `c01`, ...) keep their names, since
  models and motion lists ask for them by name: textures, animations,
  `<old>.marker`. The paths that point at them keep those names too.
- Every line of `config.json`, the manifests, `msg_name.xmsbt` and the saved
  state that mentions it is edited, whole word only (`wawa` never touches
  `wawaman`).
- Files that hold the name inside their bytes (`plugin.nro`, `.eff`, `.bntx`,
  `.prc`, sound banks) are listed, not changed: rebuild the plugin with the
  new name, edit the others by hand.

**Renumber costumes** moves a fighter's costumes onto c00, c01, ... in the
order its body model ships them. The select screen the engine publishes
starts at c00, so a pack at c120 to c127 asks for folders that do not exist
and the match never finishes loading.

- Every folder and file that carries the costume moves: model, motion,
  camera, Kirby copy, `_cNN` sound banks, one-slot effects, trails.
- The lowest one-slot effect is copied to `ef_<name>.eff`, the name the
  engine loads.
- `ui/param/database/ui_chara_db.prcxml` goes to Backups (it patches the
  base's own row).
- The manifest and the saved state drop their first costume. `config.json` is
  not touched: write it again.

### Files

What the folder ships against what `config.json` declares.

### Parameters

Pick a table, click a field, type a value, Add. Which syntax each table takes:

| Table | Syntax |
|---|---|
| a fighter's own `vl.prc` (`param_special_*`, ...) | ParamConfig: `param_config::update_*` on the Rust tab with the plugin flag, `.param(..)` on the Manifest or `[params]` without it |
| `fighter_param`, `param_motion`, `common`, `param_thrown` | engine: `.param(..)` on the Manifest or `[params]`; the game reads these past ParamConfig |
| an item's `item_common`, `item_owner_param` | `.common(..)` / `.owner_param(..)` on the ItemManifest or `[common]` / `[owner_params]`; label and name fields are Rust calls |
| an item's own `param.prc`, a stage | the files themselves |

Lists inside `vl.prc` (`hit_data`, ...) are not rules: ship your own
`vl.prc` under every costume.

### Lint

Runs the checker and lists what it found.

### Optimize

**Scan** lists every costume file whose bytes equal a lower costume's twin
(models, textures, motions, cameras, sound banks, Kirby hats) with the size it
costs. **Apply** takes those copies out of the pack (each kept in backups) and
adds `share-to-added` lines to `config.json`, so the name still loads from the
lower costume's file. Run **Lint** afterwards.

- `.marker` files, manifests and the plugin are never touched.
- A name `config.json` already aliases is left as it is.
- Empty folders are dropped.

### Vtables

Every vtable entry the part can hook, with its address for the base and a
signature read off the game:

- a fighter: its own vtable, its agent's `L2CFighterCommon` entries, the
  entries Kirby runs while he holds its ability, and each article's weapon
  vtable and `L2CWeaponCommon`;
- an item: its own vtable and its agent's first ten entries;
- an enemy: its class vtable (77 entries, `CHANGE_STATUS` and
  `REQUEST_STATUS` named) and its copy of the enemy object vtable (163
  entries, `INITIALIZE`, `START`, `UPDATE_1` to `UPDATE_9` named).

Double-click an entry, or select several and **Hook selected**; each becomes a
`#[hook]` on the Rust tab that calls the original. The line under the table
shows the whole entry under the pointer, or else the selected one. The
fighter, weapon and item tables are this clone's own copies, so a hook there
runs for it alone. An enemy has no `#[hook]`: each entry becomes a function
that calls `original_entry` (or `original_object_entry`) and a
`set_vtable_entry` (or `set_object_vtable_entry`) line in main. The base's
own enemies keep the game's entries. On a Nabbit clone, `CHANGE_STATUS` and
`REQUEST_STATUS` call the engine's routing to its driver.

The signature comes from every implementation of the entry in the game:

- a declared integer argument the function does not use is harmless;
- floats are `f64`, so an `f32` passes through unchanged;
- the return is `u64`, `f64` or, for common entries 10 and 12, `L2CValue`;
- an entry whose return could not be settled (some implementations return an
  integer, others a float, or it returns a struct) is listed but not offered,
  except two whose callers were read: the game ignores what they return.

Weapon entry 39 (`UNK39`) is the weapon's on-damage call, checked in a match:
it runs on every hit, pushes that deal no damage included, and `a2` is the hit
record (damage at `+0x04`, hit position at `+0x30`, attacker's object id at
`+0x44`). Fighter entry 68 is `ON_DAMAGE`. Addresses are main offsets for
13.0.4.

The fighter and weapon addresses, slot names and notes are incredibleplays'
[`smash-vtables`](https://github.com/theincredibleplayer/smash-vtables); the
notes on weapon entry 39 and fighter entry 68 are ours.

### Rust

One `lib.rs` for the pack, following the other tabs as you edit; copy it or
save it as `lib.rs`. Every argument carries a comment.

Per fighter:

- `fighter!`, a `<NAME>_COSTUMES` constant that drives the manifest, the CSK
  maps and the ParamConfig slots, and the `Manifest` and `register` in `main`.
- The Smashline agents: the fighter, one per article and Kirby when the clone
  has copy statuses. An article's scripts and statuses go on
  `Agent::new("<fighter>_<article>")`, a Kirby copy article's on
  `Agent::new("kirby_<article>")`.
- A floating clone gets `float::register` and the float's agent; its two
  statuses are `own_status(0)` and `own_status(1)`, so yours start at
  `own_status(2)`. A gliding clone gets the glide's agent.
- Where only you can write the code, a blank function with the calls in
  comments: the tether's statuses (the donor's own calls, its articles by your
  names), the HUD (the calls the picked HUD takes) and a reader for each of
  your commands.
- What only a hand-written `fighter.toml` says (a `base_article`, `[kirby]`
  `first` and `model`, `[[kirby.motion]]` and `[[kirby.mesh]]`, `save_no`,
  `exhibit_year`) reaches the `Manifest` too, so a pack can drop the file and
  keep them, and so do article hurtboxes and platforms (`article_hurtbox`,
  `article_lvd`).
- `[[global_motion]]`, `[[grab]]`, `[hud]`, `[tether]`, `[partner_params]` and
  `[move_list]`, and `switch_with`, `partner` and `partner_with`, go in last,
  each behind a check of the engine's capability (`CAP_GLOBAL_MOTIONS`,
  `CAP_GRAB_RULES`, `CAP_HUD`, `CAP_TETHER`, `CAP_MOVE_LIST_PAGES`,
  `CAP_ENTRY_GROUPS`, and `CAP_ANY_BASE_GROUPS` for a partner or switch group
  beyond the game's own): an engine without the feature refuses the whole
  manifest.
- With the plugin flag: `register_css_entry` (CSK's call, one layout per
  costume) and `register_params` (ParamConfig's calls with the clone's kind).

Per item: `item!`, the `ItemManifest` and `register`, and
`register_item_labels` for the label and name fields. An item with family
members registers the family instead (`register_item_family`).

A stage with doors or paused motions gets the door code of the engine's stage
template; other stages need no code. A menu pack gets `<folder>.setup`, a call
its Lua makes to set up the next battle.

With several parts of a kind, each part's functions carry its name
(`register_css_entry_wawa`); the first fighter is `fighter!`, the others a
plain `static`, since `fighter!` also names the crate's default fighter. The
entries picked on the Vtables tab follow as `#[hook]` functions, installed with
`install_hooks!` after `register`; an enemy's follow as plain functions, set on
its kind right after `enemy::clone`.

## Converting an added-slot moveset

Every moveset made for a vanilla slot ships its files under the base's own
name (`fighter/ganon/...`) at costumes the base does not have, with a
`<name>.marker` in each `model/body/cNN`, eight `ef_ganon_cNN.eff`, a
reslotter `config.json` and often a `ui_chara_db.prcxml`. The window says so
when it opens the folder. In this order:

- **Rename files** first: pick the base's name on disk, type the clone's.
  The base becomes the clone's base on the Identity tab.
- **Renumber costumes** second.
- **Write fighter.toml**, then **Write config.json**. Entries of the old
  `config.json` named after the base are dropped, not merged.
- Last, rebuild the plugin from the Rust tab: the old `plugin.nro` hooks the
  base by kind and its marker files, and is left alone.

A `fighter/<name>/param/vl.prcxml` is not declared (it is a patch, never a
file); whether ARCropolis applies it to the clone's borrowed `vl.prc` is not
proven, so ship a `vl.prc` when the values matter.

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

The window needs nothing installed. What the packs it writes need:

- The engine's `v2` module (`Manifest`, `fighter!`, `item!`): the Rust tab's
  code, `fighter.toml`, and the `[common]` and `[owner_params]` tables of
  `item.toml`. An older engine ignores them; a pack for it registers by hand
  (the engine's `DEPRECATED.md`).
- Newer than `0.2.1-beta.1`: two or more `[[item]]` or `[[stage]]` blocks in
  one file. That engine skips the whole file, so for it keep one item or stage
  per pack folder; the window writes a single one flat, which every engine
  reads.
- Newer than `0.4.2-beta.1`: `[[global_motion]]` and `[[grab]]`.
- Newer than `0.5.0-beta.1`: `[[article.hurtbox]]`, `[[article.lvd_vertex]]`,
  `[hud]`, `[tether]`, `switch` and `partner`.
- `CAP_COMMAND_INPUTS`: `[commands]` and `[[command]]`.
- Newer than `0.6.0-beta.1`: `menu.toml`; ladders, barrels, springs and doors
  (`0.6.0-beta.1` refuses a `stage.toml` with them); `dynamic_collisions` and
  `paused_motions`; item families; `[move_list]`; article statuses on
  `smashline::Agent` (older engines take them through `article(..).status()`).
- A `clone_engine_api` that has `float` and `glide`: the float and the glide.

An engine refuses a `fighter.toml` with a feature it lacks, so the Rust tab
checks the capability first. A call the engine lacks prints
`was not applied: EngineUnavailable` in the log.

## Stage packs

Four `stage.toml` keys change what the game does: `resource_place`, `bgm`,
`bgm_setting_no` and `bgm_selector`. `content_donor`, `content_donor_tree` and
`carry_donor_scenery` only steer the tools when writing `config.json`.

A stage is tuned by its files. `stageparam_<place>.stprm` is a prc file:
camera, wind, colour correction, Final Smash cameras. `render/render_param.prc`
is the post-processing. Blast zones and collision are in the `.lvd`.

- The game finds `.lvd` and `.stprm` by extension, so name those as you like;
  yours replaces the donor's. Stages with numbered sets (Wuhu Island) keep the
  donor's names.
- A `.stdat` is asked for by its file name, so yours keeps the donor's name
  inside your own folder, for example
  `stage/<place>/normal/param/zelda_greatbay.stdat` on a Great Bay donor. A
  `.stdat` named after your place is loaded and never read; the linter says
  so.
- The linter also warns when another installed mod replaces a file your stage
  borrows from the game: that combination loads a black screen, so ship your
  own copy.

## Menu packs

A menu pack is `menu.toml`, its compiled Lua under `ui/script/menu/<folder>/`
and its layouts under `ui/layout/`, with no `config.json`. Its modes show on
the page of the `Clone Engine Modes` pack that comes with the engine. Every key
and call is in the engine's `docs/wiki/MENUS.md`; `custom_menus/template` is a
complete pack.

## Mii packs

A Mii pack adds hats and outfits to the Mii Fighter menus; it replaces none.
Every key is in the engine's `docs/wiki/MII_PARTS.md`.

### Files

| part | files |
| --- | --- |
| hat | `miihat/<id>/model/body/c00` to `c11`; swing bones in `miihat/<id>/motion/body/c00` |
| outfit | `fighter/<fighter>/model/<id>/c00` to `c11`, and `fighter/<fighter>/motion/<id>/c00` |
| hat icon | `ui/replace/mii_hat/mii_hat_0/mii_hat_0_<id>.bntx` |
| outfit icon | `ui/replace/mii_body/mii_body_0/mii_body_0_<icon name>.bntx` |
| names | `nam_mii_hat_<id>` and `nam_mii_body_<id>` in `ui/message/msg_name.xmsbt` |

- `c00` to `c11` are the twelve favourite colours; ship all twelve.
- An outfit's motion folder holds the base's `update.prc`, `ik.prc`,
  `flip.prc` and `scharge.prc`, plus `motion_list.bin` and `swing.prc` when
  the base has them.
- `config.json` lists each part's folder and colour folders; the window and
  `lint_mii_pack.py --fix-config` write it.

### Head

| `model_type` | the Mii's head |
| --- | --- |
| `normal` | full hair |
| `hat` | hair trimmed to fit under a hat |
| `face_only` | face only, no hair |
| `term` | none: the hat is the whole head |

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
`arc_index/arc_dir_files.tsv`:

- each directory the game loads for a costume (the costume itself, `camera`,
  `result`, `movie`, `kirbycopy`, and Joker's `append`) becomes the clone's,
  with the same files under the clone's names;
- each link (`cmn`, `camera`, the Kirby copy leaves) stays a link to the
  base's;
- effect files sit in every costume group;
- the base's Kirby hat is the clone's by default, its `flip.prc` and
  `update.prc` included; a pack that ships its own copy model, or names a
  donor, replaces it.

With `--pack-dir`, a file the pack ships is declared where the base keeps its
counterpart (a result-screen prop goes to `result/cNN`) and replaces the
base's:

- its own `ef_<clone>.eff` means none of the base's effects or trails, a
  `model.numdlb` none of the base's model files in that folder, a copy model
  none of the base's hat;
- a copy voice bank (`vc_kirby_copy_<clone>`) goes in every `kirbycopy/cNN`
  group;
- animations, cameras and sound files are borrowed one by one, so a voice bank
  without its `.tonelabel` gets the base's, and the crowd chant is the base's
  until you ship `vc_<clone>_cheer_cNN`;
- a costume the pack has no file for takes it from the nearest costume below
  that has it; past `c07` the base's `c00` is borrowed.

What cannot carry another name is loaded from the base by the engine at match
load: a `finalsmash/` tree, Joker's cut-in effect under `append/effect/`, and
the Final Smash movies of Joker, Hero, Sephiroth and Steve under
`prebuilt:/movie/`.

## lint_clone_pack.py

```
python lint_clone_pack.py "path/to/your/mod folder"
```

| option | meaning |
| --- | --- |
| `--arc-index <dir>` | use another arc index |
| `--cross-color-resource <name>` | an article folder every costume must have |

Prints `ERROR`, `WARN` and `INFO` lines; exit code 1 on any `ERROR`. It checks
declared files, costumes, Kirby copies and cameras.

Shares, read the way ARCropolis reads them:

- a target the pack also ships is an error (your file never loads), and so are
  a source that exists nowhere, a link to a directory that does not exist, a
  linked directory given members, and a costume directory that exists only as
  the parent of a link;
- a member that is neither shipped, in data.arc nor a share target is an error
  (the group never finishes loading), and so is a member ARCropolis never
  serves as a file: a `.prcxml` or `.xmsbt`, a tone inside a
  `<bank>.nus3audio/` folder, a dot-prefixed path.

Costumes and effects:

- the select screen offers costumes c00 to c(N-1): a fighter whose groups
  start higher, or have a gap, or a `color_start` in `fighter.toml`, is an
  error, and so is a costume group with no body `model.numdlb`;
- a shipped `ui_chara_db.prcxml` is an error in a clone pack; a vanilla
  item's files are a warning;
- a one-slot effect name (`ef_<clone>_c00.eff`) with no `ef_<clone>.eff` is an
  error, one beside a borrowed `ef_<clone>.eff` a warning (the pack's effects
  are not loaded); an effect model missing from some costume groups is a
  warning.

`fighter.toml` is read with the engine's rules (an unknown key or table is an
error with its line) and checked against the folders:

- the base is a fighter, every `[[article]]` has its files, the costume count
  covers the body model, a `[kirby]` table has a copy model, and
  `staffroll = true` has its texture;
- a global motion's `animation` is shipped in some fighter's motion folder (a
  `victim` one in the clone's own); a `[[grab]]` status is a number or one of
  the engine's names;
- a `switch` group is checked against the `fighter.toml` of the packs beside
  it: a member none of them declares is a warning (a plugin may register it);
  two fighters on one base, an Ice Climbers member, or Pyra, Mythra or a
  Trainer Pokemon mixed with other bases are an error; a group on other bases
  and a Pyra/Mythra or Trainer fighter no group lists get a note;
- a `partner` is checked the same way, with a note for one on the clone's own
  base and for the named fighter's own pack;
- `[partner_params]` keys must be the Ice Climbers' own names; off popo a key
  other than `nana_delay` and `nana_opt_dst` gets a note, and a `nana_delay`
  above 15 a warning;
- a Lucas tether gets a note about its `air_catch_pose`;
- a base of fighter kind 94 or above with articles is a warning: Smashline
  2.0 refuses them;
- a `[move_list]` page without its `nam_peculiar` labels in `msg_name.xmsbt`,
  or a picture page without its texture, is a warning.

Items:

- `item.toml`, the base links and `param.prc` must agree;
- an item's or Assist's `motion_list.bin` that does not name its own folder at
  offset 8 is a warning (one copied from the base plays the base's
  animations), and so is an Assist folder missing from `new-dir-infos`.

When the pack folder holds its Rust source under `src/`, a custom work id past
a base's `_TERM` is warned about: a clone's work arrays are its base's size.

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

- Ladders, barrels, springs and doors are read with the engine's rules: a
  value it refuses is an error, a key it ignores a warning.
- A missing model set or motion, a set drawn twice or also bound in
  `config_stage.toml`, and doors or paused motions with no `plugin.nro` are
  warnings.

## lint_menu_pack.py

```
python lint_menu_pack.py "path/to/your/mod folder"
```

| option | meaning |
| --- | --- |
| `--arc-index <dir>` | use another arc index |

- `menu.toml` is read with the engine's rules: an error means the engine
  skips the whole file.
- Every `menu.toml` in the mods folder is read in the engine's order: a code,
  sequence id or mode id another pack took first, or a list past its limit
  (32 modes, 64 codes, 16 layouts, 64 patches, 64 preloads), is an error. It lists your
  modes' rows on the page and warns when the Clone Engine Modes pack is
  missing.
- Scripts must be in the pack and compiled with 4-byte floats; a mode with no
  `runs_as` needs `enter` in its script.
- A picture layout needs `blyt/<folder>.bflyt`, and every layout's
  `timg/__Combined.bntx` must start on a 4096-byte boundary, or the main menu
  stops at load.
- Popup rows another pack also adds, popup booleans that are not `true` or
  `false`, movie paths past 62 bytes and `.lua` files in the pack are
  reported.

## lint_mii_pack.py

```
python lint_mii_pack.py "path/to/your/mod folder"
```

| option | meaning |
| --- | --- |
| `--arc-index <dir>` | use another arc index |
| `--fix-config` | write each part's folders into `config.json` first |

- `mii.toml` is read with the engine's rules: an error means the engine skips
  the whole file.
- An id the game already has, or a base it does not have, is an error.
- A missing colour folder, motion file, icon or name is reported.

## lint_enemy_pack.py

```
python lint_enemy_pack.py "path/to/your/mod folder"
```

| option | meaning |
| --- | --- |
| `--fix-config` | write each enemy's folders into `config.json` first |
| `--fix-motion-list` | make each `motion_list.bin` name its enemy's folder |

- `enemy.toml` is read with the engine's rules: an error means the engine
  skips the whole file.
- A folder missing from `config.json` and a motion list naming another
  folder are errors; an enemy with no model is reported.

## What else is in this folder

- `clone_pack_gui/data/`: fighter, item and weapon kinds, music playlists, the
  fighter param words, `ParamLabels.csv`, which names the hashes in a prc, and
  the `vtable_*.tsv` tables behind the Vtables tab. The fighter and weapon
  addresses, slot names and notes are incredibleplays'
  [`smash-vtables`](https://github.com/theincredibleplayer/smash-vtables)
  (13.0.4); the item, enemy and common tables and the signatures were read off
  the game's code.
- `docs/`: the parameter field lists for game version 13.0.4.
- `arc_index/`: the file and folder paths inside `data.arc` (13.0.4), and
  `arc_dir_files.tsv`, which files each fighter and item directory loads.
  Paths only, no game data. Set `SSBU_ARC_INDEX` or pass `--arc-index` to use
  another.
- `backups/`: appears once the window has written over a file. Safe to empty.

## Licence

GPL-3.0. See `LICENSE`.
