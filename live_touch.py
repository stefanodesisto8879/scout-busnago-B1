import io
import math
from collections import defaultdict
import streamlit as st
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.pdfgen import canvas

# ==========================================================
# CONFIGURAZIONE PAGINA (TOUCH TABLET FULL-WIDTH)
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

# Sestetti tipici per rotazione avversaria
ROTATION_LINEUPS = {
    1: {"p": "P", "c": "C2", "s": "S1", "o": "O", "c_back": "C1", "s_back": "S2", "type": 3},
    6: {"p": "P", "c": "C2", "s": "S1", "o": "O", "c_back": "C1", "s_back": "S2", "type": 3},
    5: {"p": "P", "c": "C1", "s": "S2", "o": "O", "c_back": "C2", "s_back": "S1", "type": 3},
    4: {"p": "P", "c": "C1", "s": "S2", "o": "O", "c_back": "C2", "s_back": "S1", "type": 2},
    3: {"p": "P", "c": "C1", "s": "S2", "o": "O", "c_back": "C2", "s_back": "S1", "type": 2},
    2: {"p": "P", "c": "C2", "s": "S1", "o": "O", "c_back": "C1", "s_back": "S2", "type": 2},
}

# ==========================================================
# GESTIONE DELLO STATO (SESSION STATE)
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

# Struttura Dati di Partita
if "match_data" not in st.session_state:
    st.session_state["match_data"] = {
        "rotations": {
            p: {
                "bases": defaultdict(int),
                "attacks": [],
                "serve_targets": defaultdict(int),
                "server_num": "",
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
    .touch-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 14px 10px;
        margin: 4px;
        border-radius: 8px;
        font-weight: 700;
        font-size: 1.1rem;
        cursor: pointer;
        text-align: center;
    }
    .metric-card {
        background-color: #1E293B;
        padding: 12px;
        border-radius: 8px;
        color: white;
        margin-bottom: 8px;
    }
    .badge-ok { color: #10B981; font-weight: bold; }
    .badge-warn { color: #EF4444; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ==========================================================
# BARRA SUPERIORE: COMANDI E CAMBIO ROTAZIONE
# ==========================================================
top_col1, top_col2, top_col3 = st.columns([3, 6, 3])

with top_col1:
    st.session_state["opp_team"] = st.text_input("Squadra Avversaria:", value=st.session_state["opp_team"])

with top_col2:
    st.write("**SELEZIONA FASE DI GIOCO (ROTAZIONE AVVERSARIA):**")
    rot_cols = st.columns(6)
    for idx, p in enumerate([1, 6, 5, 4, 3, 2]):
        btn_type = "primary" if st.session_state["current_rot"] == p else "secondary"
        if rot_cols[idx].button(f"P{p}", key=f"btn_rot_{p}", type=btn_type, use_container_width=True):
            st.session_state["current_rot"] = p
            st.rerun()

with top_col3:
    st.session_state["current_set"] = st.selectbox("Set:", [1, 2, 3, 4, 5], index=st.session_state["current_set"] - 1)
    if st.button("↩️ Annulla Ultimo Tocco", use_container_width=True):
        if st.session_state["history"]:
            last_action = st.session_state["history"].pop()
            # Rollback
            action_type = last_action["type"]
            rot = last_action.get("rot", st.session_state["current_rot"])
            if action_type == "base":
                st.session_state["match_data"]["rotations"][rot]["bases"][last_action["key"]] -= 1
                st.session_state["match_data"]["rotations"][rot]["total_att"] -= 1
            elif action_type == "our_stat":
                st.session_state["match_data"]["our_stats"][last_action["key"]] -= 1
            elif action_type == "opp_attack":
                st.session_state["match_data"]["rotations"][rot]["attacks"].pop()
                st.session_state["match_data"]["rotations"][rot]["total_att"] -= 1
            st.success("Ultimo inserimento annullato!")
            st.rerun()

st.markdown("---")

# ==========================================================
# CORPO PRINCIPALE: SPLIT SCREEN (SCOUT TOUCH vs DASHBOARD)
# ==========================================================
scout_tab, dash_tab = st.tabs(["📝 SCHERMO RILEVAZIONE (SCOUT)", "📊 DASHBOARD LIVE (COACH)"])

cur_rot = st.session_state["current_rot"]
rot_info = ROTATION_LINEUPS[cur_rot]

# ==========================================================
# VISTA 1: SCHERMO RILEVAZIONE TOUCH
# ==========================================================
with scout_tab:
    col_bases, col_att, col_team = st.columns([4, 4, 4])

    # ----------------------------------------------------
    # COLONNA 1: MATRICE COMBINAZIONI PALLEGGIATORE (BASI)
    # ----------------------------------------------------
    with col_bases:
        st.subheader(f"⚡ Basi Centrale P{cur_rot} ({'Attacco a 3' if rot_info['type'] == 3 else 'Attacco a 2'})")
        
        # Battitore nostro per questa rotazione
        srv_val = st.text_input(f"Nostro Battitore in P{cur_rot}:", value=st.session_state["our_server"][cur_rot])
        st.session_state["our_server"][cur_rot] = srv_val

        st.caption("Tocca per registrare la scelta del palleggiatore:")
        
        if rot_info["type"] == 3:
            # Griglia Attacco a 3 (P1, P6, P5)
            b_cols1 = st.columns(2)
            if b_cols1[0].button("Base 1", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["1"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "1"})
                st.rerun()
            if b_cols1[1].button("Base 7", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["7"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "7"})
                st.rerun()

            b_cols2 = st.columns(2)
            if b_cols2[0].button("1 - 2", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["1-2"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "1-2"})
                st.rerun()
            if b_cols2[1].button("1 - 4", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["1-4"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "1-4"})
                st.rerun()

            b_cols3 = st.columns(2)
            if b_cols3[0].button("7 - 2", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["7-2"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "7-2"})
                st.rerun()
            if b_cols3[1].button("7 - 4", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["7-4"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "7-4"})
                st.rerun()
        else:
            # Griglia Attacco a 2 (P4, P3, P2)
            b2_cols1 = st.columns(2)
            if b2_cols1[0].button("Base 2", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["2"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "2"})
                st.rerun()
            if b2_cols1[1].button("Base 1", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["1"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "1"})
                st.rerun()

            b2_cols2 = st.columns(2)
            if b2_cols2[0].button("Base F (Fast)", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["F"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "F"})
                st.rerun()
            if b2_cols2[1].button("F - 6 (Pipe)", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["F-6"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "F-6"})
                st.rerun()

            b2_cols3 = st.columns(2)
            if b2_cols3[0].button("1 - 1", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["1-1"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "1-1"})
                st.rerun()
            if b2_cols3[1].button("1 - 4", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["1-4"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "1-4"})
                st.rerun()

            b2_cols4 = st.columns(2)
            if b2_cols4[0].button("F - 4", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["F-4"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "F-4"})
                st.rerun()
            if b2_cols4[1].button("F - 1", use_container_width=True):
                st.session_state["match_data"]["rotations"][cur_rot]["bases"]["F-1"] += 1
                st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
                st.session_state["history"].append({"type": "base", "rot": cur_rot, "key": "F-1"})
                st.rerun()

        st.markdown("**Riepilogo Scelte in P" + str(cur_rot) + ":**")
        base_counts = st.session_state["match_data"]["rotations"][cur_rot]["bases"]
        tot_b = st.session_state["match_data"]["rotations"][cur_rot]["total_att"]
        if tot_b > 0:
            for b_k, b_v in sorted(base_counts.items(), key=lambda x: x[1], reverse=True):
                if b_v > 0:
                    pct = (b_v / tot_b) * 100
                    st.write(f"• **{b_k}**: {b_v} volte ({pct:.0f}%)")
        else:
            st.caption("Nessuna azione ancora registrata in questa fase.")

    # ----------------------------------------------------
    # COLONNA 2: TRAIETTORIE D'ATTACCO AVVERSARIE (TAP-TAP)
    # ----------------------------------------------------
    with col_att:
        st.subheader(f"🎯 Attacco Avversario in P{cur_rot}")
        
        att_start = st.selectbox("Zona Partenza Attacco:", ["Posto 4", "Posto 3 (Centro)", "Posto 2", "Pipe (Z8)"])
        att_end = st.selectbox("Bersaglio Difesa Nostra:", ["Zona 1", "Zona 6", "Zona 5", "Zona 7", "Zona 8", "Zona 9", "Zona 2", "Zona 3", "Zona 4"])
        
        st.write("**Seleziona Esito:**")
        esito_cols = st.columns(3)
        
        if esito_cols[0].button("🟢 Punto (#)", use_container_width=True):
            st.session_state["match_data"]["rotations"][cur_rot]["attacks"].append((att_start, att_end, "#"))
            st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
            st.session_state["history"].append({"type": "opp_attack", "rot": cur_rot})
            st.success("Punto avversario registrato!")
            st.rerun()

        if esito_cols[1].button("🟡 In Gioco (!)", use_container_width=True):
            st.session_state["match_data"]["rotations"][cur_rot]["attacks"].append((att_start, att_end, "!"))
            st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
            st.session_state["history"].append({"type": "opp_attack", "rot": cur_rot})
            st.info("Attacco difeso/rigiocato registrato!")
            st.rerun()

        if esito_cols[2].button("🔴 Errore (=)", use_container_width=True):
            st.session_state["match_data"]["rotations"][cur_rot]["attacks"].append((att_start, att_end, "="))
            st.session_state["match_data"]["rotations"][cur_rot]["total_att"] += 1
            st.session_state["history"].append({"type": "opp_attack", "rot": cur_rot})
            st.error("Errore/Murato avversario registrato!")
            st.rerun()

        st.markdown("---")
        st.write(f"**Attacchi totali registrati in P{cur_rot}: {len(st.session_state['match_data']['rotations'][cur_rot]['attacks'])}**")
        for a_s, a_e, a_ev in st.session_state["match_data"]["rotations"][cur_rot]["attacks"][-4:]:
            icon = "🟢" if a_ev == "#" else ("🔴" if a_ev == "=" else "🟡")
            st.write(f"{icon} Da {a_s} a {a_e}")

    # ----------------------------------------------------
    # COLONNA 3: STATISTICHE RAPIDE NOSTRE (MODELLO B1)
    # ----------------------------------------------------
    with col_team:
        st.subheader("🏐 Rendimento Busnago")
        st_data = st.session_state["match_data"]["our_stats"]

        # 1. Battuta
        st.write("**Battuta Nostra:**")
        b_srv = st.columns(3)
        if b_srv[0].button("Ace (#)", use_container_width=True):
            st_data["srv_ace"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "srv_ace"})
            st.rerun()
        if b_srv[1].button("In Gioco (-)", use_container_width=True):
            st_data["srv_in"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "srv_in"})
            st.rerun()
        if b_srv[2].button("Errore (=)", use_container_width=True):
            st_data["srv_err"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "srv_err"})
            st.rerun()

        # 2. Ricezione
        st.write("**Ricezione Nostra:**")
        b_rec = st.columns(3)
        if b_rec[0].button("Positiva (#+)", use_container_width=True):
            st_data["rec_pos"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "rec_pos"})
            st.rerun()
        if b_rec[1].button("Slash/Neg (!-)", use_container_width=True):
            st_data["rec_neg"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "rec_neg"})
            st.rerun()
        if b_rec[2].button("Ace Subito (=)", use_container_width=True):
            st_data["rec_err"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "rec_err"})
            st.rerun()

        # 3. Attacco Cambio Palla (CP)
        st.write("**Attacco Nostro Cambio Palla (CP):**")
        b_cp = st.columns(3)
        if b_cp[0].button("CP Kill (#)", use_container_width=True):
            st_data["cp_kill"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "cp_kill"})
            st.rerun()
        if b_cp[1].button("CP Gioco (!)", use_container_width=True):
            st_data["cp_in"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "cp_in"})
            st.rerun()
        if b_cp[2].button("CP Err/Mur (=)", use_container_width=True):
            st_data["cp_err"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "cp_err"})
            st.rerun()

        # 4. Attacco Contrattacco (BP)
        st.write("**Attacco Nostro Contrattacco (BP):**")
        b_bp = st.columns(3)
        if b_bp[0].button("BP Kill (#)", use_container_width=True):
            st_data["bp_kill"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "bp_kill"})
            st.rerun()
        if b_bp[1].button("BP Gioco (!)", use_container_width=True):
            st_data["bp_in"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "bp_in"})
            st.rerun()
        if b_bp[2].button("BP Err/Mur (=)", use_container_width=True):
            st_data["bp_err"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "bp_err"})
            st.rerun()

        # 5. Muro
        st.write("**Muro Nostro:**")
        b_blk = st.columns(3)
        if b_blk[0].button("Punto (#)", use_container_width=True):
            st_data["blk_pts"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "blk_pts"})
            st.rerun()
        if b_blk[1].button("Tocco Difeso", use_container_width=True):
            st_data["blk_touch"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "blk_touch"})
            st.rerun()
        if b_blk[2].button("Fallo/Invasione", use_container_width=True):
            st_data["blk_fault"] += 1
            st.session_state["history"].append({"type": "our_stat", "key": "blk_fault"})
            st.rerun()

# ==========================================================
# VISTA 2: DASHBOARD LIVE PER IL COACH (IMPATTO IMMEDIATO)
# ==========================================================
with dash_tab:
    st.header(f"📊 Monitor Tattico Live vs {st.session_state['opp_team']} (Set {st.session_state['current_set']})")
    
    st_d = st.session_state["match_data"]["our_stats"]
    tot_srv = st_d["srv_ace"] + st_d["srv_in"] + st_d["srv_err"]
    tot_rec = st_d["rec_pos"] + st_d["rec_neg"] + st_d["rec_err"]
    tot_cp = st_d["cp_kill"] + st_d["cp_in"] + st_d["cp_err"]
    tot_bp = st_d["bp_kill"] + st_d["bp_in"] + st_d["bp_err"]
    tot_att = tot_cp + tot_bp
    tot_kill = st_d["cp_kill"] + st_d["bp_kill"]
    tot_att_err = st_d["cp_err"] + st_d["bp_err"]
    tot_blk = st_d["blk_pts"] + st_d["blk_touch"] + st_d["blk_fault"]

    # Calcoli percentuali
    ace_pct = (st_d["srv_ace"] / tot_srv * 100) if tot_srv > 0 else 0
    err_srv_pct = (st_d["srv_err"] / tot_srv * 100) if tot_srv > 0 else 0
    rec_pos_pct = (st_d["rec_pos"] / tot_rec * 100) if tot_rec > 0 else 0
    rec_err_pct = (st_d["rec_err"] / tot_rec * 100) if tot_rec > 0 else 0
    cp_kill_pct = (st_d["cp_kill"] / tot_cp * 100) if tot_cp > 0 else 0
    bp_kill_pct = (st_d["bp_kill"] / tot_bp * 100) if tot_bp > 0 else 0
    tot_kill_pct = (tot_kill / tot_att * 100) if tot_att > 0 else 0
    tot_eff_pct = ((tot_kill - tot_att_err) / tot_att * 100) if tot_att > 0 else 0

    st.subheader("🎯 Semaforo Benchmark Serie B1 2026-27")
    kpi_cols = st.columns(5)

    def render_kpi(col, title, val, target_str, is_ok, subtitle=""):
        badge = "▲ IN TARGET" if is_ok else "▼ SOTTO SOGLIA"
        color = "#10B981" if is_ok else "#EF4444"
        col.markdown(f"""
        <div style="background-color: #0F172A; border-left: 5px solid {color}; padding: 12px; border-radius: 6px;">
            <div style="font-size: 0.85rem; color: #94A3B8;">{title}</div>
            <div style="font-size: 1.6rem; font-weight: bold; color: white;">{val:.0f}%</div>
            <div style="font-size: 0.75rem; color: {color}; font-weight: bold;">{badge} ({target_str})</div>
            <div style="font-size: 0.70rem; color: #64748B;">{subtitle}</div>
        </div>
        """, unsafe_allow_html=True)

    render_kpi(kpi_cols[0], "Attacco CP (Kill)", cp_kill_pct, "≥35%", cp_kill_pct >= BENCHMARK_B1["att_cp"]["kill_min"], f"{st_d['cp_kill']}/{tot_cp} colpi")
    render_kpi(kpi_cols[1], "Attacco BP (Kill)", bp_kill_pct, "≥30%", bp_kill_pct >= BENCHMARK_B1["att_bp"]["kill_min"], f"{st_d['bp_kill']}/{tot_bp} colpi")
    render_kpi(kpi_cols[2], "Attacco Totale", tot_kill_pct, "≥32%", tot_kill_pct >= BENCHMARK_B1["att_tot"]["kill_min"], f"Eff: {tot_eff_pct:.0f}%")
    render_kpi(kpi_cols[3], "Ricezione Pos (#+)", rec_pos_pct, "≥50%", rec_pos_pct >= BENCHMARK_B1["reception"]["pos_min"], f"Err: {rec_err_pct:.0f}%")
    render_kpi(kpi_cols[4], "Errori Battuta", err_srv_pct, "≤10%", err_srv_pct <= BENCHMARK_B1["serve"]["err_max"], f"Ace: {ace_pct:.0f}% ({st_d['srv_ace']})")

    st.markdown("---")

    # Quadro Distribuzione Avversaria per Tutte le Rotazioni
    st.subheader("🗺️ Mappa Distribuzione Palleggiatore Avversario (Basi & Spinte)")
    d_cols = st.columns(3)
    
    for idx, p in enumerate([1, 6, 5, 4, 3, 2]):
        c_target = d_cols[idx % 3]
        rot_d = st.session_state["match_data"]["rotations"][p]
        tot_rot_att = rot_d["total_att"]
        
        with c_target:
            st.markdown(f"**FASE P{p} ({tot_rot_att} palloni):**")
            if tot_rot_att > 0 and rot_d["bases"]:
                top_choice = max(rot_d["bases"], key=rot_d["bases"].get)
                top_pct = (rot_d["bases"][top_choice] / tot_rot_att) * 100
                st.info(f"🔥 **Scelta dominante:** {top_choice} ({top_pct:.0f}%)")
                for b_name, b_val in sorted(rot_d["bases"].items(), key=lambda x: x[1], reverse=True)[:3]:
                    pct = (b_val / tot_rot_att) * 100
                    st.progress(min(1.0, pct / 100.0), text=f"{b_name}: {pct:.0f}% ({b_val}p)")
            else:
                st.caption("Nessuna azione ancora registrata in questa fase.")
