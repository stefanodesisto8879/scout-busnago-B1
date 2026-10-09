import io
import math
from collections import defaultdict
import streamlit as st
import pandas as pd
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

# Coordinate campo: ogni metà campo è un quadrato (0..1 x 0.5..1.0 e 0..1 x 0..0.5)
COORDS_MAP = {
    # Metà Attacco superiore (da y=0.5 a 1.0)
    "4": (0.17, 0.58), "3": (0.50, 0.58), "2": (0.83, 0.58),
    "7": (0.17, 0.75), "8": (0.50, 0.75), "9": (0.83, 0.75),
    "5": (0.17, 0.91), "6": (0.50, 0.91), "1": (0.83, 0.91),
    # Metà Difesa inferiore (da y=0.0 a 0.5)
    "def_4": (0.17, 0.42), "def_3": (0.50, 0.42), "def_2": (0.83, 0.42),
    "def_7": (0.17, 0.25), "def_8": (0.50, 0.25), "def_9": (0.83, 0.25),
    "def_5": (0.17, 0.09), "def_6": (0.50, 0.09), "def_1": (0.83, 0.09),
}

# ==========================================================
# INIZIALIZZAZIONE SESSION STATE SICURA E AUTO-RIPARANTE
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

if "att_team_target" not in st.session_state:
    st.session_state["att_team_target"] = "Avversario"

if "roster_df_busnago" not in st.session_state:
    st.session_state["roster_df_busnago"] = pd.DataFrame([
        {"Numero": "1", "Ruolo": "P"},
        {"Numero": "2", "Ruolo": "S1"},
        {"Numero": "3", "Ruolo": "C1"},
        {"Numero": "4", "Ruolo": "O"},
        {"Numero": "5", "Ruolo": "S2"},
        {"Numero": "6", "Ruolo": "C2"},
        {"Numero": "7", "Ruolo": "L"},
        {"Numero": "8", "Ruolo": "S"},
        {"Numero": "9", "Ruolo": "C"},
        {"Numero": "10", "Ruolo": "P"},
        {"Numero": "11", "Ruolo": "O"},
        {"Numero": "12", "Ruolo": "L"}
    ])

if "roster_df_opp" not in st.session_state:
    st.session_state["roster_df_opp"] = pd.DataFrame([
        {"Numero": "1", "Ruolo": "P"},
        {"Numero": "2", "Ruolo": "S1"},
        {"Numero": "3", "Ruolo": "C1"},
        {"Numero": "4", "Ruolo": "O"},
        {"Numero": "5", "Ruolo": "S2"},
        {"Numero": "6", "Ruolo": "C2"},
        {"Numero": "7", "Ruolo": "L"},
        {"Numero": "8", "Ruolo": "S"},
        {"Numero": "9", "Ruolo": "C"},
        {"Numero": "10", "Ruolo": "P"},
        {"Numero": "11", "Ruolo": "O"},
        {"Numero": "12", "Ruolo": "L"}
    ])

if "match_data" not in st.session_state or not isinstance(st.session_state["match_data"], dict):
    st.session_state["match_data"] = {}

m_data = st.session_state["match_data"]

if "rotations" not in m_data:
    m_data["rotations"] = {
        p: {
            "bases": defaultdict(int),
            "attacks": [],
            "serve_targets": defaultdict(int),
            "opp_rec": defaultdict(int),
            "total_att": 0
        }
        for p in range(1, 7)
    }

if "busnago_attacks" not in m_data:
    m_data["busnago_attacks"] = {p: [] for p in range(1, 7)}

if "money_time" not in m_data:
    m_data["money_time"] = {"4": 0, "3": 0, "2": 0}

if "rec_player_busnago" not in m_data:
    m_data["rec_player_busnago"] = defaultdict(lambda: {"#": 0, "!": 0, "=": 0})

if "rec_player_opp" not in m_data:
    m_data["rec_player_opp"] = defaultdict(lambda: {"#": 0, "!": 0, "=": 0})

if "our_stats" not in m_data:
    m_data["our_stats"] = {
        "srv_ace": 0, "srv_in": 0, "srv_err": 0,
        "rec_pos": 0, "rec_neg": 0, "rec_err": 0,
        "cp_kill": 0, "cp_in": 0, "cp_err": 0,
        "bp_kill": 0, "bp_in": 0, "bp_err": 0,
        "blk_pts": 0, "blk_err": 0
    }

if "opp_stats" not in m_data:
    m_data["opp_stats"] = {
        "srv_ace": 0, "srv_in": 0, "srv_err": 0,
        "rec_pos": 0, "rec_neg": 0, "rec_err": 0,
        "cp_kill": 0, "cp_in": 0, "cp_err": 0,
        "bp_kill": 0, "bp_in": 0, "bp_err": 0,
        "blk_pts": 0, "blk_err": 0
    }

def get_player_labels(df):
    labels = []
    for _, row in df.iterrows():
        num = str(row["Numero"]).strip()
        role = str(row["Ruolo"]).strip() if pd.notna(row["Ruolo"]) and str(row["Ruolo"]).strip() else ""
        if num:
            labels.append(f"#{num} ({role})" if role else f"#{num}")
    return labels if labels else ["#1", "#2", "#3", "#4", "#5", "#6"]

roster_labels_busnago = get_player_labels(st.session_state["roster_df_busnago"])
roster_labels_opp = get_player_labels(st.session_state["roster_df_opp"])

# ==========================================================
# STILE CSS PULITO: CARD CON BORDI E BOTTONI COMPATTI
# ==========================================================
st.markdown("""
<style>
    .section-card {
        background-color: #F8FAFC;
        border: 1.5px solid #CBD5E1;
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    
    .section-header {
        font-size: 1.05rem;
        font-weight: 800;
        padding-bottom: 6px;
        margin-bottom: 10px;
        border-bottom: 2px solid #E2E8F0;
        display: flex;
        align-items: center;
    }
    
    .stButton>button {
        font-weight: 700 !important;
        border-radius: 6px !important;
        padding: 9px 4px !important;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================================
# HEADER: FASI ROTAZIONE E COMANDI DI GARA
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
                m_data["rotations"][t_rot]["bases"][last["key"]] -= 1
                m_data["rotations"][t_rot]["total_att"] -= 1
            elif last["type"] == "opp_attack":
                if m_data["rotations"][t_rot]["attacks"]:
                    m_data["rotations"][t_rot]["attacks"].pop()
                    m_data["rotations"][t_rot]["total_att"] -= 1
            elif last["type"] == "busnago_attack":
                if m_data["busnago_attacks"][t_rot]:
                    m_data["busnago_attacks"][t_rot].pop()
            elif last["type"] == "money_time":
                m_data["money_time"][last["key"]] -= 1
            elif last["type"] == "our_stat":
                m_data["our_stats"][last["key"]] -= 1
            elif last["type"] == "opp_stat":
                m_data["opp_stats"][last["key"]] -= 1
            elif last["type"] == "rec_busnago":
                m_data["rec_player_busnago"][last["player"]][last["eval"]] -= 1
            elif last["type"] == "rec_opp":
                m_data["rec_player_opp"][last["player"]][last["eval"]] -= 1
            st.success("Ultima azione rimossa con successo!")
            st.rerun()

st.markdown("---")

tab_scout, tab_coach, tab_roster = st.tabs([
    "📝 RILEVAZIONE LIVE (TOUCH)", 
    "📊 DASHBOARD COMPARATIVA & 6 CAMPI (COACH)",
    "👥 GESTIONE NUMERI E RUOLI"
])

cur_rot = st.session_state["current_rot"]
rot_setup = ROTATION_LINEUPS[cur_rot]

# ==========================================================
# TAB 1: RILEVAZIONE LIVE TOUCH (CRONOLOGICA)
# ==========================================================
with tab_scout:
    c_p1, c_p2, c_p3, c_p4 = st.columns([3, 3, 3.8, 2.2])

    # 1. BATTUTA & RICEZIONE
    with c_p1:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-header" style="color: #0284C7;">1️⃣ SERVIZIO & RICEZIONE</div>', unsafe_allow_html=True)
        
        st.session_state["our_server"][cur_rot] = st.text_input(
            f"Nostro Battitore in P{cur_rot}:", 
            value=st.session_state["our_server"][cur_rot]
        )

        st.markdown("**Servizio Nostro Busnago:**")
        b_srv1, b_srv2, b_srv3 = st.columns(3)
        if b_srv1.button("Ace (#)", key="b_s_ace", use_container_width=True):
            m_data["our_stats"]["srv_ace"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "srv_ace"})
            st.rerun()
        if b_srv2.button("In gioco (!)", key="b_s_in", use_container_width=True):
            m_data["our_stats"]["srv_in"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "srv_in"})
            st.rerun()
        if b_srv3.button("Errore (≠)", key="b_s_err", use_container_width=True):
            m_data["our_stats"]["srv_err"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "srv_err"})
            st.rerun()

        st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1px dashed #CBD5E1;'>", unsafe_allow_html=True)

        st.markdown("**Ricezione Busnago:**")
        p_sel_bus = st.selectbox("Giocatrice Busnago:", roster_labels_busnago, key="sel_r_bus")
        r_b1, r_b2, r_b3 = st.columns(3)
        if r_b1.button("Pos (#)", key="r_bus_pos", use_container_width=True):
            m_data["rec_player_busnago"][p_sel_bus]["#"] += 1
            m_data["our_stats"]["rec_pos"] += 1
            st.session_state["history"].append({"type": "rec_busnago", "player": p_sel_bus, "eval": "#"})
            st.rerun()
        if r_b2.button("Slash (!)", key="r_bus_neg", use_container_width=True):
            m_data["rec_player_busnago"][p_sel_bus]["!"] += 1
            m_data["our_stats"]["rec_neg"] += 1
            st.session_state["history"].append({"type": "rec_busnago", "player": p_sel_bus, "eval": "!"})
            st.rerun()
        if r_b3.button("Ace Sub (≠)", key="r_bus_err", use_container_width=True):
            m_data["rec_player_busnago"][p_sel_bus]["="] += 1
            m_data["our_stats"]["rec_err"] += 1
            st.session_state["history"].append({"type": "rec_busnago", "player": p_sel_bus, "eval": "="})
            st.rerun()

        st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1.5px solid #CBD5E1;'>", unsafe_allow_html=True)

        st.markdown(f"**Battuta Loro in P{cur_rot}:**")
        p_sel_opp = st.selectbox("Ricevitore Avversario:", roster_labels_opp, key="sel_r_opp")
        r_o1, r_o2, r_o3 = st.columns(3)
        if r_o1.button("Pos (#)", key="r_opp_pos", use_container_width=True):
            m_data["rec_player_opp"][p_sel_opp]["#"] += 1
            m_data["opp_stats"]["rec_pos"] += 1
            st.session_state["history"].append({"type": "rec_opp", "player": p_sel_opp, "eval": "#"})
            st.rerun()
        if r_o2.button("Slash (!)", key="r_opp_neg", use_container_width=True):
            m_data["rec_player_opp"][p_sel_opp]["!"] += 1
            m_data["opp_stats"]["rec_neg"] += 1
            st.session_state["history"].append({"type": "rec_opp", "player": p_sel_opp, "eval": "!"})
            st.rerun()
        if r_o3.button("Ace Sub (≠)", key="r_opp_err", use_container_width=True):
            m_data["rec_player_opp"][p_sel_opp]["="] += 1
            m_data["opp_stats"]["rec_err"] += 1
            st.session_state["history"].append({"type": "rec_opp", "player": p_sel_opp, "eval": "="})
            st.rerun()

        st.caption("Zona di arrivo battuta avversaria:")
        s_row1 = st.columns(3)
        s_row2 = st.columns(3)
        s_row3 = st.columns(3)
        for idx_z, (col, zn) in enumerate(zip(
            [s_row1[0], s_row1[1], s_row1[2], s_row2[0], s_row2[1], s_row2[2], s_row3[0], s_row3[1], s_row3[2]],
            ["4", "3", "2", "7", "8", "9", "5", "6", "1"]
        )):
            cnt_s = m_data["rotations"][cur_rot]["serve_targets"][zn]
            if col.button(f"Z{zn} ({cnt_s})", key=f"srv_btn_{zn}", use_container_width=True):
                m_data["rotations"][cur_rot]["serve_targets"][zn] += 1
                st.session_state["history"].append({"type": "opp_serve", "rot": cur_rot, "key": zn})
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # 2. BASI CENTRALE
    with c_p2:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="section-header" style="color: #D97706;">2️⃣ BASI CENTRALE P{cur_rot}</div>', unsafe_allow_html=True)

        def record_base(b_name):
            m_data["rotations"][cur_rot]["bases"][b_name] += 1
            m_data["rotations"][cur_rot]["total_att"] += 1
            st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": b_name})
            st.rerun()

        st.write("**Basi Singole:**")
        bs1, bs2, bs3, bs4, bs5 = st.columns(5)
        if bs1.button("K1", use_container_width=True): record_base("K1")
        if bs2.button("K7", use_container_width=True): record_base("K7")
        if bs3.button("KC", use_container_width=True): record_base("KC")
        if bs4.button("K2", use_container_width=True): record_base("K2")
        if bs5.button("KF", use_container_width=True): record_base("KF")

        st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1px dashed #CBD5E1;'>", unsafe_allow_html=True)

        st.write("**Combinazioni con Alzata (Base - Uscita):**")
        b_k1_1, b_k1_2, b_k1_3 = st.columns(3)
        if b_k1_1.button("K1-4", use_container_width=True): record_base("K1-4")
        if b_k1_2.button("K1-2", use_container_width=True): record_base("K1-2")
        if b_k1_3.button("K1-6", use_container_width=True): record_base("K1-6")

        b_k7_1, b_k7_2, b_k7_3 = st.columns(3)
        if b_k7_1.button("K7-4", use_container_width=True): record_base("K7-4")
        if b_k7_2.button("K7-2", use_container_width=True): record_base("K7-2")
        if b_k7_3.button("K7-6", use_container_width=True): record_base("K7-6")

        b_kc_1, b_kc_2, b_kc_3 = st.columns(3)
        if b_kc_1.button("KC-4", use_container_width=True): record_base("KC-4")
        if b_kc_2.button("KC-2", use_container_width=True): record_base("KC-2")
        if b_kc_3.button("KC-6", use_container_width=True): record_base("KC-6")

        b_k2_1, b_k2_2, b_k2_3 = st.columns(3)
        if b_k2_1.button("K2-4", use_container_width=True): record_base("K2-4")
        if b_k2_2.button("K2-2", use_container_width=True): record_base("K2-2")
        if b_k2_3.button("K2-6", use_container_width=True): record_base("K2-6")

        b_kf_1, b_kf_2, b_kf_3 = st.columns(3)
        if b_kf_1.button("KF-4", use_container_width=True): record_base("KF-4")
        if b_kf_2.button("KF-2", use_container_width=True): record_base("KF-2")
        if b_kf_3.button("KF-6", use_container_width=True): record_base("KF-6")

        st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1.5px solid #CBD5E1;'>", unsafe_allow_html=True)
        st.write("🔥 **Money Time (20-25) Uscita Alzatore:**")
        mt_cols = st.columns(3)
        if mt_cols[0].button("Z4", key="mt_4", use_container_width=True):
            m_data["money_time"]["4"] += 1
            st.session_state["history"].append({"type": "money_time", "key": "4"})
            st.rerun()
        if mt_cols[1].button("Z3", key="mt_3", use_container_width=True):
            m_data["money_time"]["3"] += 1
            st.session_state["history"].append({"type": "money_time", "key": "3"})
            st.rerun()
        if mt_cols[2].button("Z2", key="mt_2", use_container_width=True):
            m_data["money_time"]["2"] += 1
            st.session_state["history"].append({"type": "money_time", "key": "2"})
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # 3. DIREZIONE ATTACCO CON ZONE ORIENTATE SECONDO IL FOGLIO
    with c_p3:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-header" style="color: #059669;">3️⃣ DIREZIONE ATTACCO</div>', unsafe_allow_html=True)
        
        target_team = st.radio(
            "Squadra in Attacco:",
            ["Avversario", "Busnago"],
            horizontal=True,
            key="att_team_radio"
        )
        st.session_state["att_team_target"] = target_team

        st.markdown("<hr style='margin: 6px 0; border: none; border-top: 1px solid #CBD5E1;'>", unsafe_allow_html=True)

        # Selezione Partenza Attacco (Zone secondo la disposizione standard del campo: Posto 4 a sx, 3 centro, 2 a dx)
        st.markdown(f"**📍 Origine Attacco (Attivo: Posto {st.session_state['selected_start_z']}):**")
        
        # Sotto Rete (Prima Linea): 4, 3, 2
        row_o1 = st.columns(3)
        if row_o1[0].button("Posto 4", type="primary" if st.session_state["selected_start_z"] == "4" else "secondary", use_container_width=True):
            st.session_state["selected_start_z"] = "4"; st.rerun()
        if row_o1[1].button("Posto 3 (C)", type="primary" if st.session_state["selected_start_z"] == "3" else "secondary", use_container_width=True):
            st.session_state["selected_start_z"] = "3"; st.rerun()
        if row_o1[2].button("Posto 2", type="primary" if st.session_state["selected_start_z"] == "2" else "secondary", use_container_width=True):
            st.session_state["selected_start_z"] = "2"; st.rerun()

        # Linea Mediana / Pipe: 7, 8, 9
        row_o2 = st.columns(3)
        if row_o2[0].button("Zona 7", type="primary" if st.session_state["selected_start_z"] == "7" else "secondary", use_container_width=True):
            st.session_state["selected_start_z"] = "7"; st.rerun()
        if row_o2[1].button("Pipe (Z8)", type="primary" if st.session_state["selected_start_z"] == "8" else "secondary", use_container_width=True):
            st.session_state["selected_start_z"] = "8"; st.rerun()
        if row_o2[2].button("Zona 9", type="primary" if st.session_state["selected_start_z"] == "9" else "secondary", use_container_width=True):
            st.session_state["selected_start_z"] = "9"; st.rerun()

        # Fondo Campo: 5, 6, 1
        row_o3 = st.columns(3)
        if row_o3[0].button("Zona 5", type="primary" if st.session_state["selected_start_z"] == "5" else "secondary", use_container_width=True):
            st.session_state["selected_start_z"] = "5"; st.rerun()
        if row_o3[1].button("Zona 6", type="primary" if st.session_state["selected_start_z"] == "6" else "secondary", use_container_width=True):
            st.session_state["selected_start_z"] = "6"; st.rerun()
        if row_o3[2].button("Zona 1 (Opp)", type="primary" if st.session_state["selected_start_z"] == "1" else "secondary", use_container_width=True):
            st.session_state["selected_start_z"] = "1"; st.rerun()

        # Separatore visivo netto tra origine e destinazione
        st.markdown("<hr style='margin: 10px 0; border: none; border-top: 2.5px solid #000000;'>", unsafe_allow_html=True)

        # Selezione Arrivo Difesa
        st.markdown(f"**🎯 Arrivo Difesa (Attivo: Zona {st.session_state['selected_end_z']}):**")
        
        # Sotto rete difesa: D4, D3, D2
        row_d1 = st.columns(3)
        if row_d1[0].button("D4 (Rete)", type="primary" if st.session_state["selected_end_z"] == "4" else "secondary", use_container_width=True):
            st.session_state["selected_end_z"] = "4"; st.rerun()
        if row_d1[1].button("D3 (Centro)", type="primary" if st.session_state["selected_end_z"] == "3" else "secondary", use_container_width=True):
            st.session_state["selected_end_z"] = "3"; st.rerun()
        if row_d1[2].button("D2 (Rete)", type="primary" if st.session_state["selected_end_z"] == "2" else "secondary", use_container_width=True):
            st.session_state["selected_end_z"] = "2"; st.rerun()

        # Centro campo difesa: D7, D8, D9
        row_d2 = st.columns(3)
        if row_d2[0].button("D7", type="primary" if st.session_state["selected_end_z"] == "7" else "secondary", use_container_width=True):
            st.session_state["selected_end_z"] = "7"; st.rerun()
        if row_d2[1].button("D8", type="primary" if st.session_state["selected_end_z"] == "8" else "secondary", use_container_width=True):
            st.session_state["selected_end_z"] = "8"; st.rerun()
        if row_d2[2].button("D9", type="primary" if st.session_state["selected_end_z"] == "9" else "secondary", use_container_width=True):
            st.session_state["selected_end_z"] = "9"; st.rerun()

        # Fondo campo difesa: D5, D6, D1
        row_d3 = st.columns(3)
        if row_d3[0].button("D5 (Fondo)", type="primary" if st.session_state["selected_end_z"] == "5" else "secondary", use_container_width=True):
            st.session_state["selected_end_z"] = "5"; st.rerun()
        if row_d3[1].button("D6 (Fondo)", type="primary" if st.session_state["selected_end_z"] == "6" else "secondary", use_container_width=True):
            st.session_state["selected_end_z"] = "6"; st.rerun()
        if row_d3[2].button("D1 (Fondo)", type="primary" if st.session_state["selected_end_z"] == "1" else "secondary", use_container_width=True):
            st.session_state["selected_end_z"] = "1"; st.rerun()

        st.markdown("<hr style='margin: 10px 0; border: none; border-top: 1.5px solid #CBD5E1;'>", unsafe_allow_html=True)

        st.markdown(f"**Registra Esito ({target_team}: Z{st.session_state['selected_start_z']} ➔ D{st.session_state['selected_end_z']}):**")
        es1, es2, es3 = st.columns(3)
        
        if es1.button("🟢 PUNTO (#)", key="att_btn_kill", use_container_width=True):
            entry = (st.session_state["selected_start_z"], st.session_state["selected_end_z"], "#")
            if target_team == "Avversario":
                m_data["rotations"][cur_rot]["attacks"].append(entry)
                m_data["rotations"][cur_rot]["total_att"] += 1
                m_data["opp_stats"]["cp_kill"] += 1
                st.session_state["history"].append({"type": "opp_attack", "rot": cur_rot})
            else:
                m_data["busnago_attacks"][cur_rot].append(entry)
                m_data["our_stats"]["cp_kill"] += 1
                st.session_state["history"].append({"type": "busnago_attack", "rot": cur_rot})
            st.rerun()

        if es2.button("🟡 IN GIOCO (!)", key="att_btn_in", use_container_width=True):
            entry = (st.session_state["selected_start_z"], st.session_state["selected_end_z"], "!")
            if target_team == "Avversario":
                m_data["rotations"][cur_rot]["attacks"].append(entry)
                m_data["rotations"][cur_rot]["total_att"] += 1
                m_data["opp_stats"]["cp_in"] += 1
                st.session_state["history"].append({"type": "opp_attack", "rot": cur_rot})
            else:
                m_data["busnago_attacks"][cur_rot].append(entry)
                m_data["our_stats"]["cp_in"] += 1
                st.session_state["history"].append({"type": "busnago_attack", "rot": cur_rot})
            st.rerun()

        if es3.button("🔴 ERRORE (=)", key="att_btn_err", use_container_width=True):
            entry = (st.session_state["selected_start_z"], st.session_state["selected_end_z"], "=")
            if target_team == "Avversario":
                m_data["rotations"][cur_rot]["attacks"].append(entry)
                m_data["rotations"][cur_rot]["total_att"] += 1
                m_data["opp_stats"]["cp_err"] += 1
                st.session_state["history"].append({"type": "opp_attack", "rot": cur_rot})
            else:
                m_data["busnago_attacks"][cur_rot].append(entry)
                m_data["our_stats"]["cp_err"] += 1
                st.session_state["history"].append({"type": "busnago_attack", "rot": cur_rot})
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # 4. MURO & FASI BREAK POINT
    with c_p4:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-header" style="color: #7C3AED;">4️⃣ MURO & BP</div>', unsafe_allow_html=True)

        st.markdown("**Muro Busnago:**")
        mb1, mb2 = st.columns(2)
        if mb1.button("Punto (#)", key="m_bus_pt", use_container_width=True):
            m_data["our_stats"]["blk_pts"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "blk_pts"})
            st.rerun()
        if mb2.button("Fallo (≠)", key="m_bus_err", use_container_width=True):
            m_data["our_stats"]["blk_err"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "blk_err"})
            st.rerun()

        st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1px dashed #CBD5E1;'>", unsafe_allow_html=True)

        st.markdown("**Muro Avversario:**")
        mo1, mo2 = st.columns(2)
        if mo1.button("Punto (#)", key="m_opp_pt", use_container_width=True):
            m_data["opp_stats"]["blk_pts"] += 1
            st.session_state["history"].append({"type": "opp_stat", "key": "blk_pts"})
            st.rerun()
        if mo2.button("Fallo (≠)", key="m_opp_err", use_container_width=True):
            m_data["opp_stats"]["blk_err"] += 1
            st.session_state["history"].append({"type": "opp_stat", "key": "blk_err"})
            st.rerun()

        st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1.5px solid #CBD5E1;'>", unsafe_allow_html=True)

        st.markdown("**Break Point Busnago:**")
        bp_b1, bp_b2 = st.columns(2)
        if bp_b1.button("Kill (#)", key="bp_bus_kill", use_container_width=True):
            m_data["our_stats"]["bp_kill"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "bp_kill"})
            st.rerun()
        if bp_b2.button("Err (≠)", key="bp_bus_err", use_container_width=True):
            m_data["our_stats"]["bp_err"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "bp_err"})
            st.rerun()

        st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1px dashed #CBD5E1;'>", unsafe_allow_html=True)

        st.markdown("**Break Point Avversario:**")
        bp_o1, bp_o2 = st.columns(2)
        if bp_o1.button("Kill (#)", key="bp_opp_kill", use_container_width=True):
            m_data["opp_stats"]["bp_kill"] += 1
            st.session_state["history"].append({"type": "opp_stat", "key": "bp_kill"})
            st.rerun()
        if bp_o2.button("Err (≠)", key="bp_opp_err", use_container_width=True):
            m_data["opp_stats"]["bp_err"] += 1
            st.session_state["history"].append({"type": "opp_stat", "key": "bp_err"})
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

# ==========================================================
# FUNZIONE GRAFICA VETTORIALE: RETTANGOLO 1:2 (DUE QUADRATI ESATTI)
# ==========================================================
def render_court_plot_with_corner_labels(attacks_list):
    # Proporzioni campo regolamentari (larghezza 1.0, altezza 2.0 -> due quadrati sovrapposti)
    fig, ax = plt.subplots(figsize=(2.4, 4.8))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.axis("off")

    # Bordo esterno rettangolare del campo (due quadrati uniti)
    rect = patches.Rectangle((0, 0), 1, 1, linewidth=2.0, edgecolor="#1E293B", facecolor="#FFFFFF")
    ax.add_patch(rect)

    # Rete centrale marcata (divide esattamente i due quadrati a metà y=0.5)
    ax.plot([0, 1], [0.5, 0.5], color="#000000", linewidth=3.2)

    # Linee dei 3 metri continue (a 1/3 e 2/3 di ogni quadrato da 0.5)
    ax.plot([0, 1], [0.666, 0.666], color="#1E293B", linewidth=1.4)
    ax.plot([0, 1], [0.333, 0.333], color="#1E293B", linewidth=1.4)

    # Linee interne tratteggiate verticali (suddivisione in 3 colonne)
    for x_val in [0.333, 0.666]:
        ax.plot([x_val, x_val], [0, 1], color="#94A3B8", linestyle="--", linewidth=0.9)

    # Linee interne tratteggiate orizzontali (suddivisione in 3 righe per quadrato)
    for y_val in [0.166, 0.833]:
        ax.plot([0, 1], [y_val, y_val], color="#94A3B8", linestyle="--", linewidth=0.9)

    # Numeri delle sottozone ancorati in alto a sinistra di ciascuna cella (orientamento reale)
    corner_labels = {
        # Metà attacco: Posto 4 a sinistra sotto rete, 2 a destra
        (0.02, 0.63): "4", (0.35, 0.63): "3", (0.68, 0.63): "2",
        (0.02, 0.79): "7", (0.35, 0.79): "8", (0.68, 0.79): "9",
        (0.02, 0.96): "5", (0.35, 0.96): "6", (0.68, 0.96): "1",
        # Metà difesa: D4 a sinistra sotto rete, D2 a destra
        (0.02, 0.46): "4", (0.35, 0.46): "3", (0.68, 0.46): "2",
        (0.02, 0.30): "7", (0.35, 0.30): "8", (0.68, 0.30): "9",
        (0.02, 0.13): "5", (0.35, 0.13): "6", (0.68, 0.13): "1",
    }
    for (lx, ly), ltxt in corner_labels.items():
        ax.text(lx, ly, ltxt, fontsize=6.2, color="#64748B", fontweight="bold")

    # Tracciamento traiettorie con freccia
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
    plt.savefig(buf, format="png", dpi=120, bbox_inches="tight", transparent=True)
    plt.close(fig)
    buf.seek(0)
    return buf

# ==========================================================
# TAB 2: DASHBOARD COMPARATIVA & 6 CAMPI RETTANGOLARI (COACH)
# ==========================================================
with tab_coach:
    st.header(f"📊 Dashboard Coach: Busnago vs {st.session_state['opp_team']} (Set {st.session_state['current_set']})")

    st.subheader("⚖️ Comparazione Fasi di Gioco (Noi vs Loro)")
    
    st_b = m_data.setdefault("our_stats", {
        "srv_ace": 0, "srv_in": 0, "srv_err": 0, "rec_pos": 0, "rec_neg": 0, "rec_err": 0,
        "cp_kill": 0, "cp_in": 0, "cp_err": 0, "bp_kill": 0, "bp_in": 0, "bp_err": 0,
        "blk_pts": 0, "blk_err": 0
    })
    st_o = m_data.setdefault("opp_stats", {
        "srv_ace": 0, "srv_in": 0, "srv_err": 0, "rec_pos": 0, "rec_neg": 0, "rec_err": 0,
        "cp_kill": 0, "cp_in": 0, "cp_err": 0, "bp_kill": 0, "bp_in": 0, "bp_err": 0,
        "blk_pts": 0, "blk_err": 0
    })

    tot_cp_b = st_b["cp_kill"] + st_b["cp_in"] + st_b["cp_err"]
    tot_cp_o = st_o["cp_kill"] + st_o["cp_in"] + st_o["cp_err"]
    cp_kill_b = (st_b["cp_kill"] / tot_cp_b * 100) if tot_cp_b > 0 else 0
    cp_kill_o = (st_o["cp_kill"] / tot_cp_o * 100) if tot_cp_o > 0 else 0
    cp_err_b = (st_b["cp_err"] / tot_cp_b * 100) if tot_cp_b > 0 else 0
    cp_err_o = (st_o["cp_err"] / tot_cp_o * 100) if tot_cp_o > 0 else 0

    tot_bp_b = st_b["bp_kill"] + st_b["bp_in"] + st_b["bp_err"]
    tot_bp_o = st_o["bp_kill"] + st_o["bp_in"] + st_o["bp_err"]
    bp_kill_b = (st_b["bp_kill"] / tot_bp_b * 100) if tot_bp_b > 0 else 0
    bp_kill_o = (st_o["bp_kill"] / tot_bp_o * 100) if tot_bp_o > 0 else 0
    bp_err_b = (st_b["bp_err"] / tot_bp_b * 100) if tot_bp_b > 0 else 0
    bp_err_o = (st_o["bp_err"] / tot_bp_o * 100) if tot_bp_o > 0 else 0

    tot_att_b = tot_cp_b + tot_bp_b
    tot_att_o = tot_cp_o + tot_bp_o
    tot_kill_b = (st_b["cp_kill"] + st_b["bp_kill"]) / tot_att_b * 100 if tot_att_b > 0 else 0
    tot_kill_o = (st_o["cp_kill"] + st_o["bp_kill"]) / tot_att_o * 100 if tot_att_o > 0 else 0
    tot_err_b = (st_b["cp_err"] + st_b["bp_err"]) / tot_att_b * 100 if tot_att_b > 0 else 0
    tot_err_o = (st_o["cp_err"] + st_o["bp_err"]) / tot_att_o * 100 if tot_att_o > 0 else 0

    comp_c1, comp_c2, comp_c3, comp_c4 = st.columns(4)

    with comp_c1:
        st.markdown("#### Cambio Palla (CP)")
        st.write(f"• **Punto (#):** Busnago **{cp_kill_b:.0f}%** vs Avv **{cp_kill_o:.0f}%**")
        st.write(f"• **Errore (≠):** Busnago **{cp_err_b:.0f}%** vs Avv **{cp_err_o:.0f}%**")
        st.caption(f"Volume: Busnago {tot_cp_b} | Avv {tot_cp_o}")

    with comp_c2:
        st.markdown("#### Break Point (BP)")
        st.write(f"• **Punto (#):** Busnago **{bp_kill_b:.0f}%** vs Avv **{bp_kill_o:.0f}%**")
        st.write(f"• **Errore (≠):** Busnago **{bp_err_b:.0f}%** vs Avv **{bp_err_o:.0f}%**")
        st.caption(f"Volume: Busnago {tot_bp_b} | Avv {tot_bp_o}")

    with comp_c3:
        st.markdown("#### Attacco Totale")
        st.write(f"• **Kill (#):** Busnago **{tot_kill_b:.0f}%** vs Avv **{tot_kill_o:.0f}%**")
        st.write(f"• **Errore (≠):** Busnago **{tot_err_b:.0f}%** vs Avv **{tot_err_o:.0f}%**")
        st.caption(f"Totale colpi: Bus {tot_att_b} | Avv {tot_att_o}")

    with comp_c4:
        st.markdown("#### Muro (# e ≠)")
        st.write(f"• **Punti (#):** Busnago **{st_b['blk_pts']}** vs Avv **{st_o['blk_pts']}**")
        st.write(f"• **Falli (≠):** Busnago **{st_b['blk_err']}** vs Avv **{st_o['blk_err']}**")

    st.markdown("---")

    # 2. RICEZIONE DI SQUADRA E INDIVIDUALE
    st.subheader("🛡️ Ricezione di Squadra & Individuale")
    rec_col1, rec_col2 = st.columns(2)

    with rec_col1:
        st.markdown("**Busnago: Riepilogo Squadra**")
        tot_r_b = st_b["rec_pos"] + st_b["rec_neg"] + st_b["rec_err"]
        if tot_r_b > 0:
            p_pos = (st_b["rec_pos"] / tot_r_b) * 100
            p_neg = (st_b["rec_neg"] / tot_r_b) * 100
            p_err = (st_b["rec_err"] / tot_r_b) * 100
            st.write(f"• Positiva (#): **{p_pos:.0f}%** ({st_b['rec_pos']}) | Slash (!): **{p_neg:.0f}%** | Ace Subiti (≠): **{p_err:.0f}%**")
        else:
            st.caption("Nessuna ricezione registrata.")

        st.markdown("**Ricezione Individuale Busnago:**")
        rec_b_data = []
        for pl, vals in m_data["rec_player_busnago"].items():
            tot_p = vals["#"] + vals["!"] + vals["="]
            if tot_p > 0:
                pos_pct = (vals["#"] / tot_p) * 100
                err_pct = (vals["="] / tot_p) * 100
                rec_b_data.append((pl, tot_p, pos_pct, err_pct))
        if rec_b_data:
            for pl, tot_p, pos_p, err_p in sorted(rec_b_data, key=lambda x: x[1], reverse=True):
                st.write(f"• **{pl}**: {tot_p} ric. | Pos: **{pos_p:.0f}%** | Err: **{err_p:.0f}%**")
        else:
            st.caption("Nessun dato individuale.")

    with rec_col2:
        st.markdown(f"**{st.session_state['opp_team']}: Riepilogo Squadra**")
        tot_r_o = st_o["rec_pos"] + st_o["rec_neg"] + st_o["rec_err"]
        if tot_r_o > 0:
            p_pos_o = (st_o["rec_pos"] / tot_r_o) * 100
            p_neg_o = (st_o["rec_neg"] / tot_r_o) * 100
            p_err_o = (st_o["rec_err"] / tot_r_o) * 100
            st.write(f"• Positiva (#): **{p_pos_o:.0f}%** ({st_o['rec_pos']}) | Slash (!): **{p_neg_o:.0f}%** | Ace Subiti (≠): **{p_err_o:.0f}%**")
        else:
            st.caption("Nessuna ricezione registrata.")

        st.markdown(f"**Ricezione Individuale {st.session_state['opp_team']}:**")
        rec_o_data = []
        for pl, vals in m_data["rec_player_opp"].items():
            tot_p = vals["#"] + vals["!"] + vals["="]
            if tot_p > 0:
                pos_pct = (vals["#"] / tot_p) * 100
                err_pct = (vals["="] / tot_p) * 100
                rec_o_data.append((pl, tot_p, pos_pct, err_pct))
        if rec_o_data:
            for pl, tot_p, pos_p, err_p in sorted(rec_o_data, key=lambda x: x[1], reverse=True):
                st.write(f"• **{pl}**: {tot_p} ric. | Pos: **{pos_p:.0f}%** | Err: **{err_p:.0f}%**")
        else:
            st.caption("Nessun dato individuale.")

    st.markdown("---")

    # 3. I 6 CAMPI GRAFICI ROTAZIONE RETTANGOLARI
    st.subheader("🗺️ Mappa Grafica dei 6 Campi (P1, P6, P5, P4, P3, P2)")
    st.caption("Campi verticali rettangolari regolamentari con traiettorie e distribuzione Basi:")

    r1_c1, r1_c2, r1_c3 = st.columns(3)
    r2_c1, r2_c2, r2_c3 = st.columns(3)
    row_layout = [r1_c1, r1_c2, r1_c3, r2_c1, r2_c2, r2_c3]

    for idx, p in enumerate([1, 6, 5, 4, 3, 2]):
        col_container = row_layout[idx]
        rot_d = m_data["rotations"][p]
        tot_rot_att = rot_d["total_att"]

        with col_container:
            st.markdown(f"### 📍 FASE P{p} (P in Z{p})")
            
            box_c1, box_c2 = st.columns([5, 6])
            
            with box_c1:
                court_img = render_court_plot_with_corner_labels(rot_d["attacks"])
                st.image(court_img, use_container_width=True)
                st.caption(f"Tot Attacchi Loro: **{tot_rot_att}**")

            with box_c2:
                srv_name = st.session_state["our_server"][p]
                st.write(f"**Nostro Battitore:** `{srv_name}`")

                st.write("**Basi Centrale ➔ Alzata:**")
                if tot_rot_att > 0 and rot_d["bases"]:
                    for b_k, b_v in sorted(rot_d["bases"].items(), key=lambda x: x[1], reverse=True)[:3]:
                        if b_v > 0:
                            pct_val = (b_v / tot_rot_att) * 100
                            st.write(f"• **{b_k}**: {pct_val:.0f}% ({b_v}p)")
                else:
                    st.caption("Nessuna base.")

                st.write("**Zone Battuta Loro:**")
                srv_map = rot_d["serve_targets"]
                if srv_map:
                    top_srv = sorted(srv_map.items(), key=lambda x: x[1], reverse=True)[:2]
                    srv_str = ", ".join([f"Z{z}: {c}" for z, c in top_srv])
                    st.write(f"• {srv_str}")
                else:
                    st.caption("Nessuna battuta.")

            st.markdown("---")

    # 4. RIEPILOGO MONEY TIME
    st.subheader("🔥 Riepilogo Money Time (Punti 20-25)")
    mt_dict = m_data["money_time"]
    tot_mt = sum(mt_dict.values())
    if tot_mt > 0:
        mt_c1, mt_c2, mt_c3 = st.columns(3)
        mt_c1.metric("Uscita in Posto 4", f"{mt_dict['4']} pal", f"{(mt_dict['4']/tot_mt*100):.0f}%")
        mt_c2.metric("Uscita in Posto 3", f"{mt_dict['3']} pal", f"{(mt_dict['3']/tot_mt*100):.0f}%")
        mt_c3.metric("Uscita in Posto 2", f"{mt_dict['2']} pal", f"{(mt_dict['2']/tot_mt*100):.0f}%")
    else:
        st.info("Nessuna azione ancora registrata nel Money Time.")

# ==========================================================
# TAB 3: GESTIONE NUMERI E RUOLI (ROSTER COMPATTO)
# ==========================================================
with tab_roster:
    st.header("👥 Inserimento Numero di Maglia e Ruolo")
    st.write("Inserisci solo il numero e scegli il ruolo[cite: 2]. Clicca su **Aggiungi riga** in fondo alla tabella se hai più giocatrici.")
    
    col_ros1, col_ros2 = st.columns(2)
    
    ruoli_disponibili = ["P", "O", "S1", "S2", "S", "C1", "C2", "C", "L"]
    
    with col_ros1:
        st.subheader("Busnago (Nostra Squadra)")
        edited_busnago = st.data_editor(
            st.session_state["roster_df_busnago"],
            column_config={
                "Numero": st.column_config.TextColumn("N° Maglia", required=True),
                "Ruolo": st.column_config.SelectboxColumn("Ruolo", options=ruoli_disponibili, required=False)
            },
            num_rows="dynamic",
            use_container_width=True,
            key="editor_busnago"
        )
        if st.button("💾 Salva Formazione Busnago"):
            st.session_state["roster_df_busnago"] = edited_busnago
            st.success("Formazione Busnago aggiornata!")
            st.rerun()

    with col_ros2:
        st.subheader(f"{st.session_state['opp_team']} (Avversario)")
        edited_opp = st.data_editor(
            st.session_state["roster_df_opp"],
            column_config={
                "Numero": st.column_config.TextColumn("N° Maglia", required=True),
                "Ruolo": st.column_config.SelectboxColumn("Ruolo", options=ruoli_disponibili, required=False)
            },
            num_rows="dynamic",
            use_container_width=True,
            key="editor_opp"
        )
        if st.button("💾 Salva Formazione Avversaria"):
            st.session_state["roster_df_opp"] = edited_opp
            st.success("Formazione Avversaria aggiornata!")
            st.rerun()
