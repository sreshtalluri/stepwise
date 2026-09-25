"""Labels corrected after looking at the contact sheets (search terms are not labels)."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("DANCE_GATE_DATA") or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".data")
os.chdir(DATA)
m = json.load(open(os.path.join(HERE, "manifest.json")))
moves = {"bollywood_palimpsest_india_and_europe_webm": "amb",          # documentary, no dance visible
         "breakdance_2011_07_30_break_dancer_ogv": "neg",              # fairground ride named Break Dancer
         "breakdance_la_mer_de_sable_ru_e_vers_l_or_ogv": "neg",       # amusement park
         "hiphop_huldiging_cardo_cdk_jr_webm": "neg",                  # local news ceremony
         "hiphop_garion_daman_garion_no_sound_ogv": "neg",             # rapper on stage
         "hiphop_hiplet_when_ballet_meets_hip_hop_webm": "amb",        # half dance, half interview
         "skateboard_louis_sarowsky_performing_at_gowanus_e_w": "amb", # performance art, unclear
         "concert_one_step_closer_live_in_philadelphia_web": "amb",    # moshing crowd
         "bharatanatyam_bharatanatyam_learn_asamyuta_hasta_video": "amb",  # title cards
         "hula_berlin_girl_turning_a_hula_hoop_berlin_2": "neg",       # hula hoop, not hula
         "hula_hula_1927_webm": "amb",                                 # film title cards
         "irish_pxl_20240317_111603131_ts_webm": "amb",                # parade float, no dance visible
         "flamenco_palmas_para_tangos_120_bpm_webm": "neg",            # close-up of clapping hands
         "lesson_single_hand_gestures_lesson_in_bharatana": "amb",     # talking head explaining mudras
         "line_n_rcon_sommar_2025_conga_line_of_furries": "amb",       # crowd, conga
         "hula_hoop_hula_hoop_fire_dance_video_turkey_2015_w": "amb",  # fire-hoop "dance", dark
         "drumming_drummers_at_the_ooni_s_palace_ogv": "amb"}          # procession, some may dance
for slug, lab in moves.items():
    if slug not in m or m[slug]["label"] == lab:
        continue
    old = m[slug]["label"]
    os.rename(f"clips/{old}/{slug}.mp4", f"clips/{lab}/{slug}.mp4")
    m[slug]["label"] = lab
    m[slug]["relabelled_from"] = old
json.dump(m, open(os.path.join(HERE, "manifest.json"), "w"), indent=1)
print("ok")
