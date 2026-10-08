import io
import re
from collections import defaultdict
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
import streamlit as st


# ==========================================
# PARSER PER FILE CLICK&SCOUT (.dvw)
# ==========================================
def parse_dvw(file_text, target_set=None):
    lines = file_text.splitlines()

    # Informazioni squadre e giocatori
    teams = {"home": "Home", "opp": "Opponent"}
    opp_players = {}

    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        if line == "[3TEAMS]":
            idx += 1
            if idx < len(lines):
                parts = lines[idx].split(";")
                if len(parts) >= 2:
                    teams["home"] = parts[1]
            idx += 1
            if idx < len(lines):
                parts = lines[idx].split(";")
                if len(parts) >= 2:
                    teams["opp"] = parts[1]
        elif line == "[3PLAYERS-V]":  # Squadra avversaria (ospite)
            idx += 1
            while idx < len(lines) and not lines[idx].startswith("[3"):
                row = lines[idx].split(";")
                if len(row) > 9:
                    num = row[1].zfill(2)
                    name = row[9] if row[9] else f"#{row[1]}"
                    role = row[12] if len(row) > 12 else ""
                    opp_players[num] = {"name": name, "role": role}
                idx += 1
            continue
        elif line == "[3SCOUT]":
            idx += 1
            break
        idx += 1

    # Inizializzazione strutture per le 6 rotazioni (P1..P6)
    rotations = {
        p: {
            "att_dist": defaultdict(int),
            "att_dir": defaultdict(int),
            "serv_dir": defaultdict(int),
            "bases": defaultdict(int),
            "total_att": 0,
        }
        for p in range(1, 7)
    }

    # Statistiche individuali avversarie
    reception_stats = defaultdict(
        lambda: {"#": 0, "+": 0, "!": 0, "-": 0, "/": 0, "=": 0, "tot": 0}
    )
    attack_stats = defaultdict(
        lambda: {"#": 0, "+": 0, "-": 0, "/": 0, "=": 0, "tot": 0}
    )

    current_set = 1

    for row in lines[idx:]:
        parts = row.split(";")
        if not parts or not parts[0]:
            continue

        code = parts[0]

        # Cambio set
        if "**" in code and "set" in code:
            m = re.search(r"\*\*(\d)set", code)
            if m:
                current_set = int(m.group(1)) + 1
            continue

        if target_set is not None and current_set != target_set:
            continue

        # Formazione avversaria nelle colonne da 19 a 24
        opp_lineup = parts[19:25] if len(parts) >= 25 else []

        # Identificazione rotazione Palleggiatore avversario (Default maglia 1 o prima trovata)
        p_rot = 1
        setter_num = "1"
        for num, pinfo in opp_players.items():
            if (
                pinfo.get("role") == "5"
                or "P" in pinfo.get("name", "")
                or num == "01"
            ):
                setter_num = str(int(num))
                break

        if setter_num in opp_lineup:
            p_rot = opp_lineup.index(setter_num) + 1  # 1..6

        # Analisi codici squadra avversaria ('a')
        if not code.startswith("a") or len(code) < 4:
            continue

        player = code[1:3]
        skill = code[3]
        eval_char = code[5] if len(code) > 5 else ""

        # Coordinate o traiettorie (~da_zona, a_zona)
        traj_match = re.search(r"~(\d)(\d)", code)
        start_z = traj_match.group(1) if traj_match else ""
        end_z = traj_match.group(2) if traj_match else ""

        # 1. RICEZIONE
        if skill == "R":
            reception_stats[player]["tot"] += 1
            if eval_char in reception_stats[player]:
                reception_stats[player][eval_char] += 1

        # 2. ATTACCO
        elif skill == "A":
            attack_stats[player]["tot"] += 1
            if eval_char in attack_stats[player]:
                attack_stats[player][eval_char] += 1

            if start_z:
                rotations[p_rot]["total_att"] += 1
                rotations[p_rot]["att_dist"][start_z] += 1
                if end_z:
                    rotations[p_rot]["att_dir"][
                        f"{start_z}->{end_z}_{eval_char}"
                    ] += 1

                # Combinazione centrale (zona 3 o codici primo tempo)
                p_role = opp_players.get(player, {}).get("role", "")
                if (
                    start_z == "3"
                    or p_role == "4"
                    or "C" in opp_players.get(player, {}).get("name", "")
                ):
                    if end_z in ["2", "1"]:
                        rotations[p_rot]["bases"]["K7/Fast"] += 1
                    elif end_z in ["4", "5"]:
                        rotations[p_rot]["bases"]["K1 Avanti"] += 1
                    else:
                        rotations[p_rot]["bases"]["KC Centro"] += 1

        # 3. BATTUTA
        elif skill == "S":
            if start_z and end_z:
                rotations[p_rot]["serv_dir"][
                    f"{player}: Z{start_z}->Z{end_z}"
                ] += 1

    return {
        "teams": teams,
        "players": opp_players,
        "rotations": rotations,
        "reception": reception_stats,
        "attack": attack_stats,
    }


# ==========================================
# GENERAZIONE PDF TATTICO (A4 Orizzontale)
# ==========================================
def generate_tactical_pdf(data, set_label="Gara Completa"):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)

    # Intestazione
    c.setFont("Helvetica-Bold", 14)
    c.drawString(
        30,
        height - 35,
        f"STUDIO GARA LIVE: {data['teams']['opp']} vs {data['teams']['home']}",
    )
    c.setFont("Helvetica", 10)
    c.drawString(
        30,
        height - 50,
        f"Filtro: {set_label}  |  Elaborazione Tattica Click&Scout per 6 Posizioni Palleggiatore",
    )

    # Griglia 2 righe x 3 colonne per i 6 campi
    # Riga Superiore: P1, P6, P5
    # Riga Inferiore: P4, P3, P2
    positions_order = [1, 6, 5, 4, 3, 2]
    grid_coords = [
        (30, height - 265),
        (230, height - 265),
        (430, height - 265),
        (30, height - 475),
        (230, height - 475),
        (430, height - 475),
    ]

    field_w, field_h = 185, 195

    for idx, p in enumerate(positions_order):
        x, y = grid_coords[idx]
        rot_data = data["rotations"][p]

        # Riquadro campo
        c.setStrokeColor(colors.black)
        c.setLineWidth(1)
        c.rect(x, y, field_w, field_h)

        # Barra titolo fase P
        c.setFillColor(colors.HexColor("#2C3E50"))
        c.rect(x, y + field_h - 22, field_w, 22, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(
            x + 8,
            y + field_h - 16,
            f"FASE P{p} (P in Zona {p}) - Attacchi: {rot_data['total_att']}",
        )

        # Linea di metà campo / rete
        c.setStrokeColor(colors.gray)
        c.setLineWidth(0.8)
        net_y = y + field_h - 55
        c.line(x, net_y, x + field_w, net_y)

        # Dettaglio Distribuzione 4 - 3 - 2 - Pipe
        tot_att = max(1, rot_data["total_att"])
        p4_att = rot_data["att_dist"].get("4", 0)
        p3_att = rot_data["att_dist"].get("3", 0)
        p2_att = rot_data["att_dist"].get("2", 0)
        pipe_att = rot_data["att_dist"].get("8", 0) + rot_data["att_dist"].get(
            "6", 0
        )

        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x + 8, net_y + 18, "DISTRIBUZIONE ALZATE:")
        c.setFont("Helvetica", 8)
        c.drawString(
            x + 8,
            net_y + 6,
            f"Z4: {p4_att} ({p4_att*100//tot_att}%) | Z3: {p3_att} ({p3_att*100//tot_att}%) | Z2: {p2_att} ({p2_att*100//tot_att}%)",
        )

        # Basi del Centrale
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x + 8, y + 95, "BASI CENTRALE:")
        c.setFont("Helvetica", 7.5)
        k1 = rot_data["bases"].get("K1 Avanti", 0)
        kc = rot_data["bases"].get("KC Centro", 0)
        k7 = rot_data["bases"].get("K7/Fast", 0)
        c.drawString(x + 8, y + 83, f"• K1 (Avanti): {k1}")
        c.drawString(x + 8, y + 72, f"• KC (Centro): {kc}")
        c.drawString(x + 8, y + 61, f"• K7 (Dietro/Fast): {k7}")

        # Principali Direzioni di Attacco
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x + 8, y + 46, "DIREZIONI PREVALENTI:")
        c.setFont("Helvetica", 7)
        top_dirs = sorted(
            rot_data["att_dir"].items(), key=lambda item: item[1], reverse=True
        )[:3]
        if top_dirs:
            y_offset = y + 34
            for d_name, cnt in top_dirs:
                c.drawString(x + 12, y_offset, f"• {d_name.split('_')[0]}: {cnt}")
                y_offset -= 10
        else:
            c.drawString(x + 12, y + 34, "Nessun attacco registrato")

    # Pannello Laterale Destro: Riepilogo Tattico
    side_x = 635
    side_y = height - 475
    side_w = width - side_x - 25
    side_h = 440

    c.setStrokeColor(colors.HexColor("#2C3E50"))
    c.rect(side_x, side_y, side_w, side_h)
    c.setFillColor(colors.HexColor("#2C3E50"))
    c.rect(side_x, side_y + side_h - 22, side_w, 22, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(side_x + 8, side_y + side_h - 16, "SINTESI CHIAVE AVVERSARIA")

    # Calcolo Ricevitori
    rec_ranking = []
    for num, stats in data["reception"].items():
        if stats["tot"] > 0:
            pos_pct = (stats["#"] + stats["+"]) / stats["tot"] * 100
            rec_ranking.append((num, stats["tot"], pos_pct, stats["="]))

    rec_ranking.sort(key=lambda x: (x[2], -x[3]))

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(side_x + 8, side_y + side_h - 40, "RICEZIONE AVVERSARIA:")
    c.setFont("Helvetica", 8)
    if rec_ranking:
        worst = rec_ranking[0]
        best = rec_ranking[-1]
        c.drawString(
            side_x + 8,
            side_y + side_h - 55,
            f"TARGET (Peggior): #{worst[0]}",
        )
        c.drawString(
            side_x + 12,
            side_y + side_h - 67,
            f"{worst[2]:.0f}% Pos ({worst[1]} ric, {worst[3]} err)",
        )

        c.drawString(
            side_x + 8,
            side_y + side_h - 85,
            f"EVITARE (Miglior): #{best[0]}",
        )
        c.drawString(
            side_x + 12,
            side_y + side_h - 97,
            f"{best[2]:.0f}% Pos ({best[1]} ric, {best[3]} err)",
        )
    else:
        c.drawString(side_x + 8, side_y + side_h - 55, "Dati ricezione assenti")

    # Calcolo Attaccanti
    att_ranking = []
    for num, stats in data["attack"].items():
        if stats["tot"] > 0:
            eff_pct = (
                (stats["#"] - stats["="] - stats["/"]) / stats["tot"]
            ) * 100
            att_ranking.append((num, stats["tot"], stats["#"], eff_pct))

    att_ranking_served = sorted(att_ranking, key=lambda x: x[1], reverse=True)
    att_ranking_eff = sorted(att_ranking, key=lambda x: x[3], reverse=True)

    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(side_x + 8, side_y + side_h - 125, "ATTACCANTI CHIAVE:")
    c.setFont("Helvetica", 8)
    if att_ranking:
        most_served = att_ranking_served[0]
        c.drawString(
            side_x + 8,
            side_y + side_h - 140,
            f"PIÙ SERVITO: #{most_served[0]}",
        )
        c.drawString(
            side_x + 12,
            side_y + side_h - 152,
            f"{most_served[1]} attacchi ({most_served[2]} pti)",
        )

        strongest = att_ranking_eff[0]
        c.drawString(
            side_x + 8,
            side_y + side_h - 170,
            f"PIÙ EFFICACE: #{strongest[0]}",
        )
        c.drawString(
            side_x + 12,
            side_y + side_h - 182,
            f"{strongest[3]:.0f}% Efficienza ({strongest[2]} pti)",
        )

    # Note a piè di pagina
    c.setFont("Helvetica-Oblique", 7.5)
    c.drawString(side_x + 8, side_y + 15, "Elaborato da Click&Scout (.dvw)")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


# ==========================================
# INTERFACCIA WEB STREAMLIT
# ==========================================
def main():
    st.set_page_config(
        page_title="Volley Scout Dashboard - Busnago", layout="wide"
    )

    st.title("🏐 Elaboratore Tattico Click&Scout")
    st.write(
        "Carica il file `.dvw` generato a fine set per ottenere la sintesi a 6 campi tattici e il PDF pronto da stampare."
    )

    uploaded_file = st.file_uploader(
        "Trascina qui il file .dvw di Click&Scout", type=["dvw"]
    )

    if uploaded_file:
        file_text = uploaded_file.getvalue().decode("utf-8", errors="ignore")

        # Filtro Set
        col_set, _ = st.columns([2, 4])
        with col_set:
            selected_set_str = st.selectbox(
                "Seleziona il Set da analizzare:",
                [
                    "Gara Completa",
                    "Set 1",
                    "Set 2",
                    "Set 3",
                    "Set 4",
                    "Set 5",
                ],
            )

        target_set = (
            None
            if selected_set_str == "Gara Completa"
            else int(selected_set_str.split(" ")[1])
        )

        data = parse_dvw(file_text, target_set=target_set)

        if not data:
            st.error(
                "Impossibile analizzare il file. Assicurati che contenga la sezione [3SCOUT]."
            )
            return

        st.success(
            f"Dati caricati con successo: **{data['teams']['opp']}** vs **{data['teams']['home']}**"
        )

        # Generazione PDF
        pdf_buffer = generate_tactical_pdf(data, set_label=selected_set_str)

        st.download_button(
            label="📄 Scarica Scheda Tattica in PDF",
            data=pdf_buffer,
            file_name=f"Tattica_{data['teams']['opp']}_{selected_set_str.replace(' ', '_')}.pdf",
            mime="application/pdf",
        )

        # Riepilogo rapido a schermo
        st.subheader("📊 Sintesi Rapida Ricezione & Attacco")
        c1, c2, c3, c4 = st.columns(4)

        rec_list = [
            (
                num,
                st_r["tot"],
                (st_r["#"] + st_r["+"]) / max(1, st_r["tot"]) * 100,
                st_r["="],
            )
            for num, st_r in data["reception"].items()
            if st_r["tot"] > 0
        ]
        rec_list.sort(key=lambda x: x[2])

        att_list = [
            (
                num,
                st_a["tot"],
                st_a["#"],
                (st_a["#"] - st_a["="] - st_a["/"]) / max(1, st_a["tot"]) * 100,
            )
            for num, st_a in data["attack"].items()
            if st_a["tot"] > 0
        ]
        att_by_vol = sorted(att_list, key=lambda x: x[1], reverse=True)
        att_by_eff = sorted(att_list, key=lambda x: x[3], reverse=True)

        with c1:
            if rec_list:
                st.metric(
                    "Peggior Ricevitore",
                    f"#{rec_list[0][0]}",
                    f"{rec_list[0][2]:.0f}% Pos ({rec_list[0][3]} err)",
                )
        with c2:
            if rec_list:
                st.metric(
                    "Miglior Ricevitore",
                    f"#{rec_list[-1][0]}",
                    f"{rec_list[-1][2]:.0f}% Pos",
                )
        with c3:
            if att_by_vol:
                st.metric(
                    "Attaccante Più Servito",
                    f"#{att_by_vol[0][0]}",
                    f"{att_by_vol[0][1]} attacchi",
                )
        with c4:
            if att_by_eff:
                st.metric(
                    "Attaccante Più Forte/Efficace",
                    f"#{att_by_eff[0][0]}",
                    f"{att_by_eff[0][3]:.0f}% Efficienza",
                )


if __name__ == "__main__":
    main()
