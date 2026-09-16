"""Bank id of every vanilla stage nus3bank, read from the four bytes in front of
the first `GRP ` chunk from offset 0x30. All 126 are unique: the id names the
bank SLOT, not the file, which is why two banks sharing an id alias each other.

Ids run 3000..3183 with an unused block at 3112..3169; the DLC stages sit above
it at 3171..3183. That block is the only place a minted stage can take an id
without displacing a stage the game ships.
"""

VANILLA_BANK_IDS = {
    3000: 'mario_castle64',
    3001: 'dk_jungle',
    3002: 'zelda_hyrule',
    3003: 'yoshi_story',
    3004: 'kirby_pupupu64',
    3005: 'poke_yamabuki',
    3006: 'mario_past64',
    3007: 'mario_castledx',
    3008: 'mario_rainbow',
    3009: 'dk_waterfall',
    3010: 'dk_lodge',
    3011: 'zelda_greatbay',
    3012: 'zelda_temple',
    3013: 'yoshi_cartboard',
    3014: 'yoshi_yoster',
    3015: 'kirby_fountain',
    3016: 'kirby_greens',
    3017: 'fox_corneria',
    3018: 'fox_venom',
    3019: 'metroid_zebesdx',
    3020: 'mother_onett',
    3021: 'poke_stadium',
    3022: 'metroid_kraid',
    3023: 'mother_fourside',
    3024: 'fzero_bigblue',
    3025: 'mario_pastusa',
    3026: 'mario_dolpic',
    3027: 'yoshi_island',
    3028: 'fox_lylatcruise',
    3029: 'zelda_oldin',
    3030: 'animal_village',
    3031: 'icarus_skyworld',
    3032: 'fe_siege',
    3033: 'wario_madein',
    3034: 'poke_stadium2',
    3035: 'kirby_halberd',
    3036: 'mg_shadowmoses',
    3037: 'mother_newpork',
    3038: 'ice_top',
    3039: 'metroid_norfair',
    3040: 'kart_circuitx',
    3041: 'metroid_orpheon',
    3042: 'pikmin_planet',
    3043: 'mario_pastx',
    3044: 'fzero_porttown',
    3045: 'luigimansion',
    3046: 'zelda_pirates',
    3047: 'poke_tengam',
    3048: '75m',
    3049: 'mariobros',
    3050: 'plankton',
    3051: 'sonic_greenhill',
    3052: 'mario_3dland',
    3053: 'mario_newbros2',
    3054: 'mario_paper',
    3055: 'zelda_gerudo',
    3056: 'zelda_train',
    3057: 'poke_unova',
    3058: 'poke_tower',
    3059: 'fe_arena',
    3060: 'icarus_uprising',
    3061: 'animal_island',
    3062: 'punchoutsb',
    3063: 'xeno_gaur',
    3064: 'nintendogs',
    3065: 'streetpass',
    3066: 'tomodachi',
    3067: 'pictochat2',
    3068: 'rock_wily',
    3069: 'mother_magicant',
    3070: 'kirby_gameboy',
    3071: 'balloonfight',
    3072: 'fzero_mutecity3ds',
    3073: 'mario_uworld',
    3074: 'mario_galaxy',
    3075: 'kart_circuitfor',
    3076: 'zelda_skyward',
    3077: 'kirby_cave',
    3078: 'poke_kalos',
    3079: 'fe_colloseum',
    3080: 'icarus_angeland',
    3081: 'wario_gamer',
    3082: 'pikmin_garden',
    3083: 'animal_city',
    3084: 'wiifit',
    3085: 'wreckingcrew',
    3086: 'pilotwings',
    3087: 'wufuisland',
    3088: 'sonic_windyhill',
    3089: 'pac_land',
    3090: 'flatzonex',
    3091: 'duckhunt',
    3092: 'sf_suzaku',
    3093: 'mario_maker',
    3094: 'ff_midgar',
    3095: 'bayo_clock',
    3096: 'battlefield',
    3097: 'battlefield_l',
    3098: 'end',
    3099: 'spla_parking',
    3100: 'dracula_castle',
    3101: 'zelda_tower',
    3102: 'mario_odyssey',
    3103: 'bossstage_ganonboss',
    3104: 'bossstage_dracula',
    3105: 'bossstage_galleom',
    3106: 'bossstage_marx',
    3107: 'bossstage_rathalos',
    3108: 'bonusgame',
    3109: 'bossstage_final1',
    3110: 'bossstage_final2',
    3111: 'bossstage_final3',
    3170: 'sp_edit',
    3171: 'jack_mementoes',
    3172: 'brave_altar',
    3173: 'buddy_spiral',
    3174: 'homeruncontest',
    3175: 'dolly_stadium',
    3176: 'fe_shrine',
    3177: 'tantan_spring',
    3178: 'pickel_world',
    3179: 'ff_cave',
    3180: 'xeno_alst',
    3181: 'battlefield_s',
    3182: 'demon_dojo',
    3183: 'trail_castle',
}

BAND = (3000, 3183)
FREE = [value for value in range(BAND[0], BAND[1] + 1) if value not in VANILLA_BANK_IDS]


def free_bank_id(place):
    """Deterministic free id for a place, so a pack keeps it across rebuilds."""
    seed = 0
    for character in place:
        seed = (seed * 31 + ord(character)) & 0xFFFFFFFF
    return FREE[seed % len(FREE)]


def read_bank_id(path):
    import struct
    with open(path, "rb") as handle:
        blob = handle.read()
    marker = blob.find(b"GRP ", 0x30)
    if marker < 0:
        return None
    return struct.unpack("<I", blob[marker - 4:marker])[0]


def write_bank_id(path, value):
    import struct
    with open(path, "rb") as handle:
        blob = bytearray(handle.read())
    marker = blob.find(b"GRP ", 0x30)
    if marker < 0:
        return False
    blob[marker - 4:marker] = struct.pack("<I", value)
    with open(path, "wb") as handle:
        handle.write(bytes(blob))
    return True
