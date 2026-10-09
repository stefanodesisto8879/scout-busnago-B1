import io
import math
from collections import defaultdict
import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# ==========================================================
# CONFIGURAZIONE PAGINA TABLET
# ==========================================================
st.set_page_config(
    page_title="Busnago Live Touch Scout",
    page_icon="🏐",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Benchmark Serie B1 2026-27
BENCHMARK_B1 = {
    "serve": {"ace_min": 6.0, "err_max": 10.0},
    "reception": {"pos_min": 50.0, "slash_max": 35.0, "err_max": 7.0},
    "att_cp": {"kill_min": 35.0, "err_max": 15.0},
    "att_bp": {"kill_min": 30.0, "err_max": 15.0},
    "att_tot": {"kill_min": 32.0, "err_max": 16.0},
    "block": {"eff_min": 15.0, "fault_max": 33.0}
}

ROTATION_LINEUPS = {
    1: {"type": 3, "label": "Attacco a 3"},
    6: {"type": 3, "label": "Attacco a 3"},
    5: {"type": 3, "label": "Attacco a 3"},
    4: {"type": 2, "label": "Attacco a 2"},
    3: {"type": 2, "label": "Attacco a 2"},
    2: {"type": 2, "label": "Attacco a 2"},
}

ATTACK_ZONES = ["4", "3", "2", "8", "1", "6", "5", "9", "7"]

COORDS_MAP = {
    "2": (0.17, 0.53), "3": (0.50, 0.53), "4": (0.83, 0.53),
    "9": (0.17, 0.70), "8": (0.50, 0.70), "7": (0.83, 0.70),
    "1": (0.17, 0.88), "6": (0.50, 0.88), "5": (0.83, 0.88),
    "def_4": (0.17, 0.44), "def_3": (0.50, 0.44), "def_2": (0.83, 0.44),
    "def_9": (0.17, 0.28), "def_8": (0.50, 0.28), "def_7": (0.83, 0.28),
    "def_5": (0.17, 0.11), "def_6": (0.50, 0.11), "def_1": (0.83, 0.11),
}

# ==========================================================
# INIZIALIZZAZIONE SESSION STATE
# ==========================================================
if "history" not in st.session_state:
    st.session_state["history"] = []

if "current_rot" not in st.session_state:
    st.session_state["current_rot"] = 1

if "current_set" not in st.session_state:
    st.session_state["current_set"] = 1

if "opp_team" not in st.session_state:
    st.session_state["opp_team"] = "Avversario"

if "our_server" not in st.session_state:
    st.session_state["our_server"] = {1: "#", 6: "#", 5: "#", 4: "#", 3: "#", 2: "#"}

if "selected_start_z" not in st.session_state:
    st.session_state["selected_start_z"] = "4"

if "selected_end_z" not in st.session_state:
    st.session_state["selected_end_z"] = "5"

if "match_data" not in st.session_state:
    st.session_state["match_data"] = {
        "rotations": {
            p: {
                "bases": defaultdict(int),
                "attacks": [],
                "serve_targets": defaultdict(int),
                "opp_rec": defaultdict(int),
                "total_att": 0
            }
            for p in range(1, 7)
        },
        "our_stats": {
            "srv_ace": 0, "srv_in": 0, "srv_err": 0,
            "rec_pos": 0, "rec_neg": 0, "rec_err": 0,
            "cp_kill": 0, "cp_in": 0, "cp_err": 0,
            "bp_kill": 0, "bp_in": 0, "bp_err": 0,
            "blk_pts": 0, "blk_touch": 0, "blk_fault": 0
        }
    }

# ==========================================================
# CSS TOUCH PER TABLET
# ==========================================================
st.markdown("""
<style>
    .zone-btn {
        width: 100%;
        height: 55px;
        font-size: 1.15rem;
        font-weight: bold;
    }
    .metric-box {
        background-color: #1E293B;
        border-radius: 8px;
        padding: 10px;
        color: white;
        margin-bottom: 8px;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================================
# HEADER: SELEZIONE RAPIDA ROTAZIONI E COMANDI
# ==========================================================
top1, top2, top3 = st.columns([3, 6, 3])

with top1:
    st.session_state["opp_team"] = st.text_input("Squadra Avversaria:", value=st.session_state["opp_team"])

with top2:
    st.write("**SELEZIONA FASE DI GIOCO (P IN ZONA):**")
    r_cols = st.columns(6)
    for idx, p in enumerate([1, 6, 5, 4, 3, 2]):
        b_type = "primary" if st.session_state["current_rot"] == p else "secondary"
        if r_cols[idx].button(f"P{p}", key=f"r_btn_{p}", type=b_type, use_container_width=True):
            st.session_state["current_rot"] = p
            st.rerun()

with top3:
    st.session_state["current_set"] = st.selectbox("Set:", [1, 2, 3, 4, 5], index=st.session_state["current_set"] - 1)
    if st.button("↩️ Annulla Ultimo Evento", use_container_width=True):
        if st.session_state["history"]:
            last = st.session_state["history"].pop()
            t_rot = last.get("rot", st.session_state["current_rot"])
            if last["type"] == "base":
                st.session_state["match_data"]["rotations"][t_rot]["bases"][last["key"]] -= 1
                st.session_state["match_data"]["rotations"][t_rot]["total_att"] -= 1
            elif last["type"] == "opp_attack":
                if st.session_state["match_data"]["rotations"][t_rot]["attacks"]:
                    st.session_state["match_data"]["rotations"][t_rot]["attacks"].pop()
                    st.session_state["match_data"]["rotations"][t_rot]["total_att"] -= 1
            elif last["type"] == "opp_serve":
                st.session_state["match_data"]["rotations"][t_rot]["serve_targets"][last["key"]] -= 1
            elif last["type"] == "our_stat":
                st.session_state["match_data"]["our_stats"][last["key"]] -= 1
            st.success("Ultima azione rimossa con successo!")
            st.rerun()

st.markdown("---")

tab_scout, tab_coach = st.tabs(["📝 SCHERMO RILEVAZIONE (SCOUT TOUCH)", "📊 DASHBOARD LIVE DEI 6 CAMPI (COACH)"])

cur_rot = st.session_state["current_rot"]
rot_setup = ROTATION_LINEUPS[cur_rot]

# ==========================================================
# 1. SCHERMO RILEVAZIONE TOUCH (SCOUT)
# ==========================================================
with tab_scout:
    c_left, c_center, c_right = st.columns([4, 4, 4])

    # --- COLONNA 1: MATRICE BASI CENTRALE & BATTITORE ---
    with c_left:
        st.subheader(f"⚡ FASE P{cur_rot} - {rot_setup['label']}")
        
        st.session_state["our_server"][cur_rot] = st.text_input(
            f"Nostro Battitore in P{cur_rot}:", 
            value=st.session_state["our_server"][cur_rot]
        )

        st.write("**Tocca Combinazione Base Centrale:**")
        if rot_setup["type"] == 3:
            # Attacco a 3
            g1, g2 = st.columns(2)
            if g1.button("Base 1", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["1"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "1"})
                st.rerun()
            if g2.button("Base 7", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["7"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "7"})
                st.rerun()

            g3, g4 = st.columns(2)
            if g3.button("1 - 2", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["1-2"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "1-2"})
                st.rerun()
            if g4.button("1 - 4", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["1-4"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "1-4"})
                st.rerun()

            g5, g6 = st.columns(2)
            if g5.button("7 - 2", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["7-2"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "7-2"})
                st.rerun()
            if g6.button("7 - 4", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["7-4"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "7-4"})
                st.rerun()
        else:
            # Attacco a 2
            g1, g2 = st.columns(2)
            if g1.button("Base 2", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["2"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "2"})
                st.rerun()
            if g2.button("Base 1", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["1"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "1"})
                st.rerun()

            g3, g4 = st.columns(2)
            if g3.button("Base F (Fast)", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["F"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "F"})
                st.rerun()
            if g4.button("F - 6 (Pipe)", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["F-6"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "F-6"})
                st.rerun()

            g5, g6 = st.columns(2)
            if g5.button("1 - 1", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["1-1"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "1-1"})
                st.rerun()
            if g6.button("1 - 4", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["1-4"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "1-4"})
                st.rerun()

            g7, g8 = st.columns(2)
            if g7.button("F - 4", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["F-4"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "F-4"})
                st.rerun()
            if g8.button("F - 1", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["F-1"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "F-1"})
                st.rerun()

        st.markdown("---")
        st.write("**Battuta Avversaria in P" + str(cur_rot) + ":**")
        st.caption("Tocca dove batte l'avversario:")
        srv_c1, srv_c2, srv_c3 = st.columns(3)
        for idx_z, z_srv in enumerate(["1", "6", "5", "9", "8", "7", "2", "3", "4"]):
            target_col = [srv_c1, srv_c2, srv_c3][idx_z % 3]
            cnt_s = st.session_state["match_data"]["rotations"][cur_rot]["serve_targets"][z_srv]
            if target_col.button(f"Z{z_srv} ({cnt_s})", key=f"srv_btn_{z_srv}", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["serve_targets"][z_srv] += 1
                st.session_state["history"].append({"type": "opp_serve", "rot": cur_rot, "key": z_srv})
                st.rerun()

    # --- COLONNA 2: TASTIERA TOUCH CAMPO A 9 SOTTOZONE (ATTACCO) ---
    with c_center:
        st.subheader("🏐 Campo Touch: Traiettoria Attacco")
        
        # 1. Selezione Zona Partenza Attacco
        st.markdown(f"**1. Origine Attacco (Attivo: Posto {st.session_state['selected_start_z']}):**")
        z_o1, z_o2, z_o3 = st.columns(3)
        if z_o1.button("Posto 4", type="primary" if st.session_state["selected_start_z"] == "4" else "secondary", use_container_width=True):
            st.session_state["selected_start_z"] = "4"; st.rerun()
        if z_o2.button("Posto 3 (C)", type="primary" if st.session_state["selected_start_z"] == "3" else "secondary", use_container_width=True):
            st.session_state["selected_start_z"] = "3"; st.rerun()
        if z_o3.button("Posto 2", type="primary" if st.session_state["selected_start_z"] == "2" else "secondary", use_container_width=True):
            st.session_state["selected_start_z"] = "2"; st.rerun()

        z_o4, z_o5, z_o6 = st.columns(3)
        if z_o4.button("Pipe (Z8)", type="primary" if st.session_state["selected_start_z"] == "8" else "secondary", use_container_width=True):
            st.session_state["selected_start_z"] = "8"; st.rerun()
        if z_o5.button("Zona 6", type="primary" if st.session_state["selected_start_z"] == "6" else "secondary", use_container_width=True):
            st.session_state["selected_start_z"] = "6"; st.rerun()
        if z_o6.button("Zona 1 (Opp)", type="primary" if st.session_state["selected_start_z"] == "1" else "secondary", use_container_width=True):
            st.session_state["selected_start_z"] = "1"; st.rerun()

        # 2. Selezione Zona Arrivo Difesa
        st.markdown(f"**2. Destinazione Difesa (Attivo: Zona {st.session_state['selected_end_z']}):**")
        d_row1 = st.columns(3)
        if d_row1[0].button("Z4 (Rete)", type="primary" if st.session_state["selected_end_z"] == "4" else "secondary", use_container_width=True):
            st.session_state["selected_end_z"] = "4"; st.rerun()
        if d_row1[1].button("Z3 (Centro)", type="primary" if st.session_state["selected_end_z"] == "3" else "secondary", use_container_width=True):
            st.session_state["selected_end_z"] = "3"; st.rerun()
        if d_row1[2].button("Z2 (Rete)", type="primary" if st.session_state["selected_end_z"] == "2" else "secondary", use_container_width=True):
            st.session_state["selected_end_z"] = "2"; st.rerun()

        d_row2 = st.columns(3)
        if d_row2[0].button("Zona 9", type="primary" if st.session_state["selected_end_z"] == "9" else "secondary", use_container_width=True):
            st.session_state["selected_end_z"] = "9"; st.rerun()
        if d_row2[1].button("Zona 8", type="primary" if st.session_state["selected_end_z"] == "8" else "secondary", use_container_width=True):
            st.session_state["selected_end_z"] = "8"; st.rerun()
        if d_row2[2].button("Zona 7", type="primary" if st.session_state["selected_end_z"] == "7" else "secondary", use_container_width=True):
            st.session_state["selected_end_z"] = "7"; st.rerun()

        d_row3 = st.columns(3)
        if d_row3[0].button("Zona 5 (Fondo)", type="primary" if st.session_state["selected_end_z"] == "5" else "secondary", use_container_width=True):
            st.session_state["selected_end_z"] = "5"; st.rerun()
        if d_row3[1].button("Zona 6 (Fondo)", type="primary" if st.session_state["selected_end_z"] == "6" else "secondary", use_container_width=True):
            st.session_state["selected_end_z"] = "6"; st.rerun()
        if d_row3[2].button("Zona 1 (Fondo)", type="primary" if st.session_state["selected_end_z"] == "1" else "secondary", use_container_width=True):
            st.session_state["selected_end_z"] = "1"; st.rerun()

        # 3. Conferma Esito con Pulsantoni Colorati
        st.write(f"**3. Registra Esito Traiettoria (Z{st.session_state['selected_start_z']} ➔ Z{st.session_state['selected_end_z']}):**")
        es1, es2, es3 = st.columns(3)
        if es1.button("🟢 PUNTO (#)", use_container_width=True):
            st.session_state["match_data"]["rotations"][cur_rot]["attacks"].append(
                (st.session_state["selected_start_z"], st.session_state["selected_end_z"], "#")
            )
            st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
            st.session_state["history"].append({"type": "opp_attack", "rot": cur_rot})
            st.rerun()

        if es2.button("🟡 IN GIOCO (!)", use_container_width=True):
            st.session_state["match_data"]["rotations"][cur_rot]["attacks"].append(
                (st.session_state["selected_start_z"], st.session_state["selected_end_z"], "!")
            )
            st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
            st.session_state["history"].append({"type": "opp_attack", "rot": cur_rot})
            st.rerun()

        if es3.button("🔴 ERRORE (=)", use_container_width=True):
            st.session_state["match_data"]["rotations"][cur_rot]["attacks"].append(
                (st.session_state["selected_start_z"], st.session_state["selected_end_z"], "=")
            )
            st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
            st.session_state["history"].append({"type": "opp_attack", "rot": cur_rot})
            st.rerun()

    # --- COLONNA 3: STATISTICHE SQUADRA BUSNAGO ---
    with c_right:
        st.subheader("🛡️ Rendimento Busnago")
        st_data = st.session_state["match_data"]["our_stats"]

        st.write("**Battuta Busnago:**")
        srv_c = st.columns(3)
        if srv_c[0].button("Ace (#)", use_container_width=True):
            st_data["srv_ace"] += 1; st.session_state["history"].append({"type": "our_stat", "key": "srv_ace"}); st.rerun()
        if srv_c[1].button("In Gioco (-)", use_container_width=True):
            st_data["srv_in"] += 1; st.session_state["history"].append({"type": "our_stat", "key": "srv_in"}); st.rerun()
        if srv_c[2].button("Errore (=)", use_container_width=True):
            st_data["srv_err"] += 1; st.session_state["history"].append({"type": "our_stat", "key": "srv_err"}); st.rerun()

        st.write("**Ricezione Busnago:**")
        rec_c = st.columns(3)
        if rec_c[0].button("Positiva (#+)", use_container_width=True):
            st_data["rec_pos"] += 1; st.session_state["history"].append({"type": "our_stat", "key": "rec_pos"}); st.rerun()
        if rec_c[1].button("Slash/Neg (!-)", use_container_width=True):
            st_data["rec_neg"] += 1; st.session_state["history"].append({"type": "our_stat", "key": "rec_neg"}); st.rerun()
        if rec_c[2].button("Ace Subito (=)", use_container_width=True):
            st_data["rec_err"] += 1; st.session_state["history"].append({"type": "our_stat", "key": "rec_err"}); st.rerun()

        st.write("**Attacco Cambio Palla (CP):**")
        cp_c = st.columns(3)
        if cp_c[0].button("CP Kill (#)", use_container_width=True):
            st_data["cp_kill"] += 1; st.session_state["history"].append({"type": "our_stat", "key": "cp_kill"}); st.rerun()
        if cp_c[1].button("CP Gioco (!)", use_container_width=True):
            st_data["cp_in"] += 1; st.session_state["history"].append({"type": "our_stat", "key": "cp_in"}); st.rerun()
        if cp_c[2].button("CP Err/Mur (=)", use_container_width=True):
            st_data["cp_err"] += 1; st.session_state["history"].append({"type": "our_stat", "key": "cp_err"}); st.rerun()

        st.write("**Attacco Contrattacco (BP):**")
        bp_c = st.columns(3)
        if bp_c[0].button("BP Kill (#)", use_container_width=True):
            st_data["bp_kill"] += 1; st.session_state["history"].append({"type": "our_stat", "key": "bp_kill"}); st.rerun()
        if bp_c[1].button("BP Gioco (!)", use_container_width=True):
            st_data["bp_in"] += 1; st.session_state["history"].append({"type": "our_stat", "key": "bp_in"}); st.rerun()
        if bp_c[2].button("BP Err/Mur (=)", use_container_width=True):
            st_data["bp_err"] += 1; st.session_state["history"].append({"type": "our_stat", "key": "bp_err"}); st.rerun()

        st.write("**Muro Busnago:**")
        blk_c = st.columns(3)
        if blk_c[0].button("Muro Punto (#)", use_container_width=True):
            st_data["blk_pts"] += 1; st.session_state["history"].append({"type": "our_stat", "key": "blk_pts"}); st.rerun()
        if blk_c[1].button("Tocco Difeso", use_container_width=True):
            st_data["blk_touch"] += 1; st.session_state["history"].append({"type": "our_stat", "key": "blk_touch"}); st.rerun()
        if blk_c[2].button("Invasione/Fallo", use_container_width=True):
            st_data["blk_fault"] += 1; st.session_state["history"].append({"type": "our_stat", "key": "blk_fault"}); st.rerun()

# ==========================================================
# FUNZIONE GRAFICA: DISEGNO MINI-CAMPO VETTORIALE (MATPLOTLIB)
# ==========================================================
def render_court_plot(attacks_list):
    fig, ax = plt.subplots(figsize=(2.8, 3.8))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # Bordo Campo
    rect = patches.Rectangle((0, 0), 1, 1, linewidth=1.5, edgecolor="black", facecolor="white")
    ax.add_patch(rect)

    # Rete
    ax.plot([0, 1], [0.5, 0.5], color="black", linewidth=2.5)

    # Linee 3 metri
    ax.plot([0, 1], [0.67, 0.67], color="black", linewidth=1.0)
    ax.plot([0, 1], [0.33, 0.33], color="black", linewidth=1.0)

    # Sottozone tratteggiate
    for x_val in [0.33, 0.67]:
        ax.plot([x_val, x_val], [0, 1], color="#BDC3C7", linestyle="--", linewidth=0.8)
    for y_val in [0.17, 0.83]:
        ax.plot([0, 1], [y_val, y_val], color="#BDC3C7", linestyle="--", linewidth=0.8)

    # Disegna traiettorie
    for sz, ez, ev in attacks_list:
        start_pt = COORDS_MAP.get(sz, (0.5, 0.6))
        end_key = f"def_{ez}"
        end_pt = COORDS_MAP.get(end_key, (0.5, 0.2))

        col = "#27AE60" if ev == "#" else ("#E74C3C" if ev == "=" else "#F39C12")
        ax.annotate(
            "",
            xy=end_pt,
            xytext=start_pt,
            arrowprops=dict(arrowstyle="-|>", color=col, lw=1.6, mutation_scale=10)
        )

    plt.tight_layout(pad=0)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=100, bbox_inches="tight", transparent=True)
    plt.close(fig)
    buf.seek(0)
    return buf

# ==========================================================
# 2. DASHBOARD LIVE DEI 6 CAMPI (COACH)
# ==========================================================
with tab_coach:
    st.header(f"📊 Quadro Tattico Live Coach vs {st.session_state['opp_team']} (Set {st.session_state['current_set']})")

    # 1. SEMAFORO BENCHMARK SQUADRA B1
    st_d = st.session_state["match_data"]["our_stats"]
    tot_srv = st_d["srv_ace"] + st_d["srv_in"] + st_d["srv_err"]
    tot_rec = st_d["rec_pos"] + st_d["rec_neg"] + st_d["rec_err"]
    tot_cp = st_d["cp_kill"] + st_d["cp_in"] + st_d["cp_err"]
    tot_bp = st_d["bp_kill"] + st_d["bp_in"] + st_d["bp_err"]
    tot_att = tot_cp + tot_bp
    tot_kill = st_d["cp_kill"] + st_d["bp_kill"]
    tot_att_err = st_d["cp_err"] + st_d["bp_err"]

    ace_pct = (st_d["srv_ace"] / tot_srv * 100) if tot_srv > 0 else 0
    err_srv_pct = (st_d["srv_err"] / tot_srv * 100) if tot_srv > 0 else 0
    rec_pos_pct = (st_d["rec_pos"] / tot_rec * 100) if tot_rec > 0 else 0
    rec_err_pct = (st_d["rec_err"] / tot_rec * 100) if tot_rec > 0 else 0
    cp_kill_pct = (st_d["cp_kill"] / tot_cp * 100) if tot_cp > 0 else 0
    bp_kill_pct = (st_d["bp_kill"] / tot_bp * 100) if tot_bp > 0 else 0
    tot_kill_pct = (tot_kill / tot_att * 100) if tot_att > 0 else 0
    tot_eff_pct = ((tot_kill - tot_att_err) / tot_att * 100) if tot_att > 0 else 0

    st.subheader("🎯 Modello Prestazione B1: Rendimento Busnago Live")
    k_cols = st.columns(5)
    k_cols[0].metric("Attacco CP (Kill)", f"{cp_kill_pct:.0f}%", f"Target: ≥{BENCHMARK_B1['att_cp']['kill_min']:.0f}%")
    k_cols[1].metric("Attacco BP (Kill)", f"{bp_kill_pct:.0f}%", f"Target: ≥{BENCHMARK_B1['att_bp']['kill_min']:.0f}%")
    k_cols[2].metric("Attacco Tot (Kill)", f"{tot_kill_pct:.0f}%", f"Target: ≥{BENCHMARK_B1['att_tot']['kill_min']:.0f}%")
    k_cols[3].metric("Ricezione Pos (#+)", f"{rec_pos_pct:.0f}%", f"Target: ≥{BENCHMARK_B1['reception']['pos_min']:.0f}%")
    k_cols[4].metric("Errori Battuta", f"{err_srv_pct:.0f}%", f"Target: ≤{BENCHMARK_B1['serve']['err_max']:.0f}%", delta_color="inverse")

    st.markdown("---")

    # 2. I 6 CAMPI ROTAZIONE AVVERSARI (P1, P6, P5, P4, P3, P2)
    st.subheader("🗺️ Mappa Grafica dei 6 Campi (Distribuzione Basi & Traiettorie per Rotazione)")
    st.caption("Visualizzazione grafica istantanea di ogni fase: traiettorie sul campo, scelte Basi del palleggiatore e zone di battuta.")

    # Griglia a 3 colonne x 2 righe
    r1_col1, r1_col2, r1_col3 = st.columns(3)
    r2_col1, r2_col2, r2_col3 = st.columns(3)
    row_layout = [r1_col1, r1_col2, r1_col3, r2_col1, r2_col2, r2_col3]

    for idx, p in enumerate([1, 6, 5, 4, 3, 2]):
        col_container = row_layout[idx]
        rot_d = st.session_state["match_data"]["rotations"][p]
        tot_rot_att = rot_d["total_att"]

        with col_container:
            st.markdown(f"### 📍 FASE P{p} (P in Z{p})")
            
            box_c1, box_c2 = st.columns([5, 6])
            
            # Mini-Campo Vettoriale con traiettorie
            with box_c1:
                court_img = render_court_plot(rot_d["attacks"])
                st.image(court_img, use_container_width=True)
                st.caption(f"Tot attacchi: **{tot_rot_att}**")

            # Dati Tattici Affiancati
            with box_c2:
                # Nostro Battitore
                srv_name = st.session_state["our_server"][p]
                st.write(f"**Nostro Battitore:** `{srv_name}`")

                # Distribuzione Basi Centrale
                st.write("**Basi Centrale ➔ Alzata:**")
                if tot_rot_att > 0 and rot_d["bases"]:
                    top_b = max(rot_d["bases"], key=rot_d["bases"].get)
                    top_b_pct = (rot_d["bases"][top_b] / tot_rot_att) * 100
                    st.info(f"Top: **{top_b}** ({top_b_pct:.0f}%)")
                    for b_k, b_v in sorted(rot_d["bases"].items(), key=lambda x: x[1], reverse=True)[:3]:
                        if b_v > 0:
                            pct_val = (b_v / tot_rot_att) * 100
                            st.write(f"• **{b_k}**: {pct_val:.0f}% ({b_v}p)")
                else:
                    st.caption("Nessuna base registrata.")

                # Battute Avversarie
                st.write("**Zone Battuta Loro:**")
                srv_map = rot_d["serve_targets"]
                if srv_map:
                    top_srv = sorted(srv_map.items(), key=lambda x: x[1], reverse=True)[:2]
                    srv_str = ", ".join([f"Z{z}: {c}" for z, c in top_srv])
                    st.write(f"• {srv_str}")
                else:
                    st.caption("Nessuna battuta.")

            st.markdown("---")
