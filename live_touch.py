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

COORDS_MAP = {
    "2": (0.83, 0.53), "3": (0.50, 0.53), "4": (0.17, 0.53),
    "9": (0.83, 0.70), "8": (0.50, 0.70), "7": (0.17, 0.70),
    "1": (0.83, 0.88), "6": (0.50, 0.88), "5": (0.17, 0.88),
    "def_4": (0.17, 0.44), "def_3": (0.50, 0.44), "def_2": (0.83, 0.44),
    "def_7": (0.17, 0.28), "def_8": (0.50, 0.28), "def_9": (0.83, 0.28),
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
# STILE CSS AD ALTO CONTRASTO PER TOUCH TABLET
# ==========================================================
st.markdown("""
<style>
    .court-container {
        border: 2px solid #334155;
        border-radius: 8px;
        padding: 6px;
        background-color: #F8FAFC;
        margin-bottom: 8px;
    }
    .court-net {
        border-top: 3px solid #0F172A;
        margin: 4px 0px;
    }
    .court-attack-line {
        border-top: 1.5px dashed #94A3B8;
        margin: 4px 0px;
    }
    .stButton>button {
        font-weight: 700;
        border-radius: 6px;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================================
# BARRA SUPERIORE: FASI ROTAZIONE
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
            st.success("Ultima azione rimossa!")
            st.rerun()

st.markdown("---")

tab_scout, tab_coach = st.tabs(["📝 SCHERMO RILEVAZIONE (SCOUT TOUCH)", "📊 DASHBOARD LIVE DEI 6 CAMPI (COACH)"])

cur_rot = st.session_state["current_rot"]
rot_setup = ROTATION_LINEUPS[cur_rot]

# ==========================================================
# 1. SCHERMO RILEVAZIONE TOUCH (ORDINATO CRONOLOGICAMENTE)
# ==========================================================
with tab_scout:
    c_phase1, c_phase2, c_phase3, c_phase4 = st.columns([3, 3, 4, 2])

    # ----------------------------------------------------
    # 1. PRIMA FASE: BATTUTA & RICEZIONE
    # ----------------------------------------------------
    with c_phase1:
        st.subheader("1️⃣ Battuta & Ric.")
        
        st.session_state["our_server"][cur_rot] = st.text_input(
            f"Nostro Battitore in P{cur_rot}:", 
            value=st.session_state["our_server"][cur_rot]
        )

        st.markdown("**Battuta Busnago:**")
        b_srv1, b_srv2, b_srv3 = st.columns(3)
        if b_srv1.button("Ace (#)", use_container_width=True):
            st.session_state["match_data"]["our_stats"]["srv_ace"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "srv_ace"})
            st.rerun()
        if b_srv2.button("In (-)", use_container_width=True):
            st.session_state["match_data"]["our_stats"]["srv_in"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "srv_in"})
            st.rerun()
        if b_srv3.button("Err (=)", use_container_width=True):
            st.session_state["match_data"]["our_stats"]["srv_err"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "srv_err"})
            st.rerun()

        st.markdown("**Ricezione Busnago:**")
        b_rec1, b_rec2, b_rec3 = st.columns(3)
        if b_rec1.button("Pos (#+)", use_container_width=True):
            st.session_state["match_data"]["our_stats"]["rec_pos"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "rec_pos"})
            st.rerun()
        if b_rec2.button("Slash (!-)", use_container_width=True):
            st.session_state["match_data"]["our_stats"]["rec_neg"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "rec_neg"})
            st.rerun()
        if b_rec3.button("Ace Sub (=)", use_container_width=True):
            st.session_state["match_data"]["our_stats"]["rec_err"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "rec_err"})
            st.rerun()

        st.markdown(f"**Zona Battuta Loro in P{cur_rot}:**")
        s_row1 = st.columns(3)
        s_row2 = st.columns(3)
        s_row3 = st.columns(3)
        # Disposizione campo battuta: rete in alto, fondo campo in basso
        for idx_z, (col, zn) in enumerate(zip(
            [s_row1[0], s_row1[1], s_row1[2], s_row2[0], s_row2[1], s_row2[2], s_row3[0], s_row3[1], s_row3[2]],
            ["4", "3", "2", "7", "8", "9", "5", "6", "1"]
        )):
            cnt_s = st.session_state["match_data"]["rotations"][cur_rot]["serve_targets"][zn]
            if col.button(f"Z{zn} ({cnt_s})", key=f"srv_btn_{zn}", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["serve_targets"][zn] += 1
                st.session_state["history"].append({"type": "opp_serve", "rot": cur_rot, "key": zn})
                st.rerun()

    # ----------------------------------------------------
    # 2. SECONDA FASE: BASI CENTRALE & COSTRUZIONE
    # ----------------------------------------------------
    with c_phase2:
        st.subheader(f"2️⃣ Basi Centrale P{cur_rot}")
        st.caption(f"{rot_setup['label']} avversario")

        if rot_setup["type"] == 3:
            # Griglia Attacco a 3 (P1, P6, P5)
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
            # Griglia Attacco a 2 (P4, P3, P2)
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

        st.markdown(f"**Riepilogo Scelte P{cur_rot}:**")
        base_counts = st.session_state["match_data"]["rotations"][cur_rot]["bases"]
        tot_b = st.session_state["match_data"]["rotations"][cur_rot]["total_att"]
        if tot_b > 0:
            for b_k, b_v in sorted(base_counts.items(), key=lambda x: x[1], reverse=True):
                if b_v > 0:
                    pct = (b_v / tot_b) * 100
                    st.write(f"• **{b_k}**: {b_v} ({pct:.0f}%)")
        else:
            st.caption("Nessuna azione ancora registrata.")

    # ----------------------------------------------------
    # 3. TERZA FASE: TRAIETTORIA ATTACCO SUL CAMPO TOUCH
    # ----------------------------------------------------
    with c_phase3:
        st.subheader("3️⃣ Direzione Attacco")
        
        col_c_start, col_c_end = st.columns(2)

        # CAMPO 1: ORIGINE ATTACCO (Disposizione reale sul campo)
        with col_c_start:
            st.markdown(f"**Partenza (Attivo: Z{st.session_state['selected_start_z']})**")
            st.caption("Rete in alto ⬇️")
            
            # Sotto Rete (4, 3, 2)
            row_o1 = st.columns(3)
            if row_o1[0].button("Z4", type="primary" if st.session_state["selected_start_z"] == "4" else "secondary", use_container_width=True):
                st.session_state["selected_start_z"] = "4"; st.rerun()
            if row_o1[1].button("Z3", type="primary" if st.session_state["selected_start_z"] == "3" else "secondary", use_container_width=True):
                st.session_state["selected_start_z"] = "3"; st.rerun()
            if row_o1[2].button("Z2", type="primary" if st.session_state["selected_start_z"] == "2" else "secondary", use_container_width=True):
                st.session_state["selected_start_z"] = "2"; st.rerun()

            # Centro / Pipe (7, 8, 9)
            row_o2 = st.columns(3)
            if row_o2[0].button("Z7", type="primary" if st.session_state["selected_start_z"] == "7" else "secondary", use_container_width=True):
                st.session_state["selected_start_z"] = "7"; st.rerun()
            if row_o2[1].button("Z8 (Pipe)", type="primary" if st.session_state["selected_start_z"] == "8" else "secondary", use_container_width=True):
                st.session_state["selected_start_z"] = "8"; st.rerun()
            if row_o2[2].button("Z9", type="primary" if st.session_state["selected_start_z"] == "9" else "secondary", use_container_width=True):
                st.session_state["selected_start_z"] = "9"; st.rerun()

            # Fondo Campo (5, 6, 1)
            row_o3 = st.columns(3)
            if row_o3[0].button("Z5", type="primary" if st.session_state["selected_start_z"] == "5" else "secondary", use_container_width=True):
                st.session_state["selected_start_z"] = "5"; st.rerun()
            if row_o3[1].button("Z6", type="primary" if st.session_state["selected_start_z"] == "6" else "secondary", use_container_width=True):
                st.session_state["selected_start_z"] = "6"; st.rerun()
            if row_o3[2].button("Z1 (Opp)", type="primary" if st.session_state["selected_start_z"] == "1" else "secondary", use_container_width=True):
                st.session_state["selected_start_z"] = "1"; st.rerun()

        # CAMPO 2: ARRIVO DIFESA (Disposizione reale sul campo avversario)
        with col_c_end:
            st.markdown(f"**Arrivo Difesa (Attivo: Z{st.session_state['selected_end_z']})**")
            st.caption("Rete in alto ⬇️")

            # Rete difesa (4, 3, 2)
            row_d1 = st.columns(3)
            if row_d1[0].button("D4", type="primary" if st.session_state["selected_end_z"] == "4" else "secondary", use_container_width=True):
                st.session_state["selected_end_z"] = "4"; st.rerun()
            if row_d1[1].button("D3", type="primary" if st.session_state["selected_end_z"] == "3" else "secondary", use_container_width=True):
                st.session_state["selected_end_z"] = "3"; st.rerun()
            if row_d1[2].button("D2", type="primary" if st.session_state["selected_end_z"] == "2" else "secondary", use_container_width=True):
                st.session_state["selected_end_z"] = "2"; st.rerun()

            # Centro difesa (7, 8, 9)
            row_d2 = st.columns(3)
            if row_d2[0].button("D7", type="primary" if st.session_state["selected_end_z"] == "7" else "secondary", use_container_width=True):
                st.session_state["selected_end_z"] = "7"; st.rerun()
            if row_d2[1].button("D8", type="primary" if st.session_state["selected_end_z"] == "8" else "secondary", use_container_width=True):
                st.session_state["selected_end_z"] = "8"; st.rerun()
            if row_d2[2].button("D9", type="primary" if st.session_state["selected_end_z"] == "9" else "secondary", use_container_width=True):
                st.session_state["selected_end_z"] = "9"; st.rerun()

            # Fondo campo difesa (5, 6, 1)
            row_d3 = st.columns(3)
            if row_d3[0].button("D5", type="primary" if st.session_state["selected_end_z"] == "5" else "secondary", use_container_width=True):
                st.session_state["selected_end_z"] = "5"; st.rerun()
            if row_d3[1].button("D6", type="primary" if st.session_state["selected_end_z"] == "6" else "secondary", use_container_width=True):
                st.session_state["selected_end_z"] = "6"; st.rerun()
            if row_d3[2].button("D1", type="primary" if st.session_state["selected_end_z"] == "1" else "secondary", use_container_width=True):
                st.session_state["selected_end_z"] = "1"; st.rerun()

        st.markdown(f"**Registra Esito Traiettoria (Z{st.session_state['selected_start_z']} ➔ D{st.session_state['selected_end_z']}):**")
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

    # ----------------------------------------------------
    # 4. QUARTA FASE: MURO & RENDIMENTO FASI NOSTRE
    # ----------------------------------------------------
    with c_phase4:
        st.subheader("4️⃣ Muro & Fasi")
        st_data = st.session_state["match_data"]["our_stats"]

        st.markdown("**Muro Busnago:**")
        if st.button("Muro Punto (#)", use_container_width=True):
            st_data["blk_pts"] += 1; st.session_state["history"].append({"type": "our_stat", "key": "blk_pts"}); st.rerun()
        if st.button("Tocco Difeso", use_container_width=True):
            st_data["blk_touch"] += 1; st.session_state["history"].append({"type": "our_stat", "key": "blk_touch"}); st.rerun()
        if st.button("Invasione/Fallo", use_container_width=True):
            st_data["blk_fault"] += 1; st.session_state["history"].append({"type": "our_stat", "key": "blk_fault"}); st.rerun()

        st.markdown("**Nostro Cambio Palla (CP):**")
        cp_c1, cp_c2 = st.columns(2)
        if cp_c1.button("CP Kill (#)", use_container_width=True):
            st_data["cp_kill"] += 1; st.session_state["history"].append({"type": "our_stat", "key": "cp_kill"}); st.rerun()
        if cp_c2.button("CP Err (=)", use_container_width=True):
            st_data["cp_err"] += 1; st.session_state["history"].append({"type": "our_stat", "key": "cp_err"}); st.rerun()

        st.markdown("**Nostro Contrattacco (BP):**")
        bp_c1, bp_c2 = st.columns(2)
        if bp_c1.button("BP Kill (#)", use_container_width=True):
            st_data["bp_kill"] += 1; st.session_state["history"].append({"type": "our_stat", "key": "bp_kill"}); st.rerun()
        if bp_c2.button("BP Err (=)", use_container_width=True):
            st_data["bp_err"] += 1; st.session_state["history"].append({"type": "our_stat", "key": "bp_err"}); st.rerun()

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
    st.header(f"📊 Monitor Coach: I 6 Campi Live vs {st.session_state['opp_team']} (Set {st.session_state['current_set']})")

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

    st.subheader("🎯 Modello di Prestazione B1 (Busnago Live)")
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
                srv_name = st.session_state["our_server"][p]
                st.write(f"**Nostro Battitore:** `{srv_name}`")

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

                st.write("**Zone Battuta Loro:**")
                srv_map = rot_d["serve_targets"]
                if srv_map:
                    top_srv = sorted(srv_map.items(), key=lambda x: x[1], reverse=True)[:2]
                    srv_str = ", ".join([f"Z{z}: {c}" for z, c in top_srv])
                    st.write(f"• {srv_str}")
                else:
                    st.caption("Nessuna battuta.")

            st.markdown("---")
