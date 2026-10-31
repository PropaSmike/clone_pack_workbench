#!/usr/bin/env python3
"""The Rust tab's code for enemy.toml enemies: the clone, its driver and when it comes out."""

from __future__ import annotations

from . import vtables

BASE_CONSTANTS = {"yellow_devil": "YELLOW_DEVIL", "yellowdevil": "YELLOW_DEVIL",
                  "dark_emperor": "DARK_EMPEROR", "subetenoyaminoou": "DARK_EMPEROR",
                  "flying_man": "FLYING_MAN", "flyingman": "FLYING_MAN",
                  "metal_face": "METAL_FACE", "metalface": "METAL_FACE", "nabbit": "NABBIT"}
BASES = ("nabbit", "flying_man", "yellow_devil", "dark_emperor", "metal_face")
NABBIT_NATIVE = (0, 21, 23, 24)
DEFAULTS = {"arrive_frame": 120, "arrive_x": 0.0, "arrive_y": 30.0, "stay_seconds": 30, "walk_speed": 0.8}
ATOMIC = "core::sync::atomic"
SMASH = "smashline::skyline_smash"


def number(state: dict, key: str, cast):
    try:
        return cast(state.get(key))
    except (TypeError, ValueError):
        return cast(DEFAULTS[key])


def float_text(value: float) -> str:
    text = repr(float(value))
    return text if "." in text or "e" in text else text + ".0"


def tag(name: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in name).strip("_").upper() or "ENEMY"


def enemy_lines(state: dict, taken: set | None = None) -> tuple[list[str], list[str], list[str]]:
    """One enemy's declarations, its lines in main and its functions, with a
    function and its registration for each entry picked on the Vtables tab."""
    name = state.get("name") or "my_enemy"
    base = BASE_CONSTANTS.get(str(state.get("base") or "nabbit").lower(), "NABBIT")
    upper = tag(name)
    lower = upper.lower()
    driven = base == "NABBIT"
    frame = number(state, "arrive_frame", int)
    stay = number(state, "stay_seconds", int) * 60
    decls = [
        "// %s: when it comes out and where, and how long it stays" % name,
        "const %s_ARRIVE_FRAME: u64 = %d;" % (upper, frame),
        "const %s_ARRIVE_AT: (f32, f32) = (%s, %s);" % (upper, float_text(number(state, "arrive_x", float)),
                                                     float_text(number(state, "arrive_y", float))),
        "const %s_STAY_FRAMES: u64 = %d;" % (upper, stay),
        "static %s_KIND: %s::AtomicU32 = %s::AtomicU32::new(u32::MAX);" % (upper, ATOMIC, ATOMIC),
        "static %s_SERIAL: %s::AtomicU32 = %s::AtomicU32::new(u32::MAX);" % (upper, ATOMIC, ATOMIC),
        "static %s_REQUEST: %s::AtomicU32 = %s::AtomicU32::new(u32::MAX);" % (upper, ATOMIC, ATOMIC),
        "static %s_OBJECT: %s::AtomicU32 = %s::AtomicU32::new(clone_engine_api::enemy::NO_OBJECT);"
        % (upper, ATOMIC, ATOMIC),
        "static %s_ARRIVED: %s::AtomicU64 = %s::AtomicU64::new(0);" % (upper, ATOMIC, ATOMIC),
        "static %s_DONE: %s::AtomicBool = %s::AtomicBool::new(false);" % (upper, ATOMIC, ATOMIC),
    ]
    if driven:
        decls += [
            "// Nabbit's class statuses the game keeps: 0 hit and grab reactions, 21 its fall once knocked "
            "down, 23 its wait while knocked out, 24 a state every enemy shares",
            "const %s_NATIVE: &[u32] = &[%s];" % (upper, ", ".join(str(status) for status in NABBIT_NATIVE)),
            "const %s_WALK_SPEED: f32 = %s; // units per frame" % (upper, float_text(number(state, "walk_speed", float))),
            "const %s_TURN_FRAMES: u32 = 120; // frames before it turns round" % upper,
            "static %s_WALKED: %s::AtomicU32 = %s::AtomicU32::new(0);" % (upper, ATOMIC, ATOMIC),
        ]
    decls.append("")
    main = ['    if let Ok(kind) = clone_engine_api::enemy::clone(clone_engine_api::enemy::%s, "%s") { '
            "// the base, the name enemy.toml gives it" % (base, name),
            "        %s_KIND.store(kind, %s::Ordering::Release);" % (upper, ATOMIC)]
    if driven:
        main.append("        let _ = clone_engine_api::enemy::drive(kind, Some(drive_%s), "
                    "clone_engine_api::enemy::statuses(%s_NATIVE)); // its own logic in drive_%s"
                    % (lower, upper, lower))
    else:
        main.append("        // the game's own logic: Flying Man fights on any stage; the others are made for "
                    "their home stage")
    registrations, hooks = vtables.enemy_hook_source(state, upper, lower, taken if taken is not None else set())
    if registrations:
        main += registrations
    else:
        main.append("        // clone_engine_api::enemy::set_vtable_entry(kind, clone_engine_api::enemy::slot::CHANGE_STATUS, "
                    "my_change as *const ()); // one class slot of this clone (the Vtables tab writes these); "
                    "original_entry gives the base's")
        main.append("        // clone_engine_api::enemy::set_object_vtable_entry(kind, clone_engine_api::enemy::object_slot::UPDATE_9, "
                    "my_update as *const ()); // one object slot; original_object_entry gives the game's")
    main += ['        smashline::Agent::new("fighter").on_line(smashline::Main, %s_frame).install(); '
             "// every fighter, once per frame" % lower,
             "    }"]
    tail = []
    if driven:
        tail.append("\n".join([
            "// %s's own logic, every frame it is in a status the base does not keep" % name,
            "unsafe extern \"C\" fn drive_%s(_object: u32, module_accessor: usize, _status: i32) {" % lower,
            "    use %s::app::lua_bind::*;" % SMASH,
            "    let boma = module_accessor as *mut %s::app::BattleObjectModuleAccessor;" % SMASH,
            "    if MotionModule::motion_kind(boma) != %s::hash40(\"run\") {" % SMASH,
            "        MotionModule::change_motion(boma, %s::phx::Hash40::new(\"run\"), 0.0, 1.0, false, 0.0, false, "
            "false);" % SMASH,
            "    }",
            "    let walked = %s_WALKED.fetch_add(1, %s::Ordering::Relaxed);" % (upper, ATOMIC),
            "    if walked %% %s_TURN_FRAMES == %s_TURN_FRAMES - 1 {" % (upper, upper),
            "        PostureModule::reverse_lr(boma);",
            "        PostureModule::update_rot_y_lr(boma);",
            "    }",
            "    let step = %s::phx::Vector3f { x: %s_WALK_SPEED * PostureModule::lr(boma), y: 0.0, z: 0.0 };"
            % (SMASH, upper),
            "    PostureModule::add_pos(boma, &step);",
            "}",
            ""]))
    tail.append("\n".join([
        "// player 1's frame brings %s out, then takes it off after its stay" % name,
        "unsafe extern \"C\" fn %s_frame(fighter: &mut %s::lua2cpp::L2CFighterCommon) {" % (lower, SMASH),
        "    use %s::app::lua_bind::WorkModule;" % SMASH,
        "    use %s::Ordering;" % ATOMIC,
        "    use clone_engine_api::{enemy, menu};",
        "    if WorkModule::get_int(fighter.module_accessor, *%s::lib::lua_const::FIGHTER_INSTANCE_WORK_ID_INT_ENTRY_ID) != 0 {"
        % SMASH,
        "        return;",
        "    }",
        "    let (Ok(serial), Ok(frame)) = (menu::battle_serial(), menu::battle_frame()) else {",
        "        return;",
        "    };",
        "    if %s_SERIAL.swap(serial, Ordering::AcqRel) != serial {" % upper,
        "        %s_REQUEST.store(u32::MAX, Ordering::Release); // a new battle" % upper,
        "        %s_OBJECT.store(enemy::NO_OBJECT, Ordering::Release);" % upper,
        "        %s_DONE.store(false, Ordering::Release);" % upper,
        "    }",
        "    if %s_DONE.load(Ordering::Acquire) {" % upper,
        "        return;",
        "    }",
        "    if frame >= %s_ARRIVE_FRAME && %s_REQUEST.load(Ordering::Acquire) == u32::MAX {" % (upper, upper),
        "        let (x, y) = %s_ARRIVE_AT;" % upper,
        "        match enemy::spawn(%s_KIND.load(Ordering::Acquire), x, y, 0.0, 1.0) { // kind, x, y, z, facing"
        % upper,
        "            Ok(request) => %s_REQUEST.store(request, Ordering::Release)," % upper,
        "            Err(_) => %s_DONE.store(true, Ordering::Release)," % upper,
        "        }",
        "    }",
        "    let request = %s_REQUEST.load(Ordering::Acquire);" % upper,
        "    let mut object = %s_OBJECT.load(Ordering::Acquire);" % upper,
        "    if request != u32::MAX && object == enemy::NO_OBJECT {",
        "        let Some(started) = enemy::start(request) else { return }; // None until it is made",
        "        object = started;",
        "        %s_OBJECT.store(object, Ordering::Release);" % upper,
        "        %s_ARRIVED.store(frame, Ordering::Release);" % upper,
        "    }",
        "    if object != enemy::NO_OBJECT && frame >= %s_ARRIVED.load(Ordering::Acquire) + %s_STAY_FRAMES {"
        % (upper, upper),
        "        enemy::remove(object);",
        "        %s_DONE.store(true, Ordering::Release);" % upper,
        "    }",
        "}",
        ""]))
    tail += hooks
    return decls, main, tail


def enemy_part(states: list[dict], taken: set | None = None) -> dict | None:
    """Every enemy of the pack in one part: their clones, then one arm with all their kinds."""
    states = [state for state in states if state.get("name")]
    if not states:
        return None
    taken = set() if taken is None else taken
    decls: list[str] = []
    main: list[str] = []
    tail: list[str] = []
    for state in states:
        more_decls, more_main, more_tail = enemy_lines(state, taken)
        decls += more_decls
        main += more_main
        tail += more_tail
    kinds = ", ".join("%s_KIND.load(%s::Ordering::Acquire)" % (tag(state["name"]), ATOMIC) for state in states)
    main.append("    let _ = clone_engine_api::enemy::arm(clone_engine_api::enemy::kinds(&[%s])); "
                "// loaded in every battle from the next one on" % kinds)
    return {"uses": set(), "decls": decls, "main": main, "tail": tail, "name": states[0]["name"]}
