#!/usr/bin/env python3
"""Ready-made modes for a menu pack: the [[mode]] row and the Lua its script runs."""

from __future__ import annotations

PRESETS = ("duel", "pick", "boss", "movie")
DESCRIPTIONS = {
    "duel": "a battle straight from the modes page: your fighter against a CPU",
    "pick": "the players pick fighters, then fight on the stage and rules set here",
    "boss": "the game's own boss battle: intro, HP bar and victory screen",
    "movie": "a movie full screen, closed when it ends or B is pressed",
}
BOSSES = ("galleom", "masterhand", "crazyhand", "ganonboss", "dracula", "dracula2", "marx",
          "lioleusboss", "kiila", "darz")
DEFAULTS = {"fighter": "ui_chara_mario", "cpu": "ui_chara_luigi", "stage": "ui_stage_battle_field",
            "boss": "galleom"}


def mode_row(preset: str, mode_id: str, name: str, namespace: str) -> dict:
    """The [[mode]] row, as the Modes table holds rows: key to TOML text."""
    text = DESCRIPTIONS[preset]
    row = {"id": '"%s"' % mode_id, "name": '"%s"' % name, "description": '"%s%s."' % (text[0].upper(), text[1:]),
           "script": '"menu/%s/%s"' % (namespace, mode_id)}
    if preset in ("duel", "boss"):
        row.update(runs_as='"melee_normal"', scene='"IngameCallSequenceScene"')
    elif preset == "pick":
        row.update(runs_as='"melee_normal"', skip='["rules", "stage_select"]', after_battle='"menu"')
    return row


def lua_source(preset: str, name: str, values: dict) -> str:
    """The mode's script: Lua that sets the battle up by name, or plays the movie."""
    value = dict(DEFAULTS, **{key: text for key, text in values.items() if text})
    nobody = ['  for slot = %d, PLAYERS - 1 do' % (1 if preset == "boss" else 2),
              '    prg_func.engine_call("engine.battle_player", slot, "none", 0, -1)',
              '  end']
    if preset == "duel":
        body = ['-- %s: %s.' % (name, DESCRIPTIONS[preset]),
                'local mode = {}', '', 'local PLAYERS = 8', '',
                'function mode.decide(host)',
                '  prg_func.engine_call("engine.battle_player", 0, "human", "%s", host:pad())' % value["fighter"],
                '  prg_func.engine_call("engine.battle_player", 1, "cpu", "%s", -1)' % value["cpu"]] + nobody + [
                '  prg_func.engine_call("engine.battle_stage", "%s")' % value["stage"],
                '  prg_func.engine_call("engine.battle_rules", "stock", 2, 0, 0)',
                '  return true', 'end']
    elif preset == "pick":
        body = ['-- %s: %s.' % (name, DESCRIPTIONS[preset]),
                'local mode = {}', '',
                'function mode.decide(host)',
                '  prg_func.engine_call("engine.battle_stage", "%s")' % value["stage"],
                '  prg_func.engine_call("engine.battle_rules", "stock", 2, 120, 0)',
                '  return true', 'end']
    elif preset == "boss":
        body = ['-- %s: %s, against %s.' % (name, DESCRIPTIONS[preset], value["boss"]),
                'local mode = {}', '', 'local PLAYERS = 8', '',
                'function mode.decide(host)',
                '  prg_func.engine_call("engine.battle_player", 0, "human", "%s", host:pad())' % value["fighter"]
                ] + nobody + [
                '  prg_func.engine_call("engine.battle_stage", "%s")' % value["stage"],
                '  prg_func.engine_call("engine.battle_rules", "stock", 2, 0, 0)',
                '  local result = prg_func.engine_call("engine.battle_boss", "%s")' % value["boss"],
                '  return not (type(result) == "number" and result < 0)', 'end']
    else:
        body = ['-- %s: %s.' % (name, DESCRIPTIONS[preset]),
                'local mode = {}', '',
                'function mode.enter(host, resumed)',
                '  UiSoundManager:stop_bgm()',
                '  local result = prg_func.engine_call("engine.movie_play", "%s", 0)' % value.get("movie", ""),
                '  if type(result) == "number" and result < 0 then',
                '    host:close()', '  end', 'end', '',
                'function mode.update(host, keys)',
                '  if keys.cancel then',
                '    prg_func.engine_call("engine.movie_stop")', '  end',
                '  if prg_func.engine_call("engine.movie_state") ~= 1 then',
                '    host:close()', '  end', 'end', '',
                'function mode.leave(host)',
                '  prg_func.engine_call("engine.movie_stop")',
                '  UiSoundManager:play_menu_bgm()', 'end']
    return "\n".join(body + ['', 'return mode', ''])
