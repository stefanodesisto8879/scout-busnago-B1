import io
import re
from collections import defaultdict
import streamlit as st
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

# ==========================================================
# COORDINATE STANDARD ZONE PALLAVOLO
# ==========================================================
ZONE_COORDS = {
    "4": (0.20, 0.82), "3": (0.50, 0.82), "2": (0.80, 0.82),
    "7": (0.20, 0.55), "8": (0.50, 0.55), "9": (0.80, 0.55),
    "5": (0.20, 0.20), "6": (0.50, 0.20), "1": (0.80, 0.20),
}

OPP_ZONE_COORDS = {
    "4": (0.80, 0.70), "3": (0.50, 0.70), "2": (0.20, 0.70),
    "7": (0.80, 0.50), "8": (0.50, 0.50), "9": (0.20, 0.50),
    "5": (0.80, 0.25), "6": (0.50, 0.25), "1": (0.20, 0.25),
}

# ==========================================================
# PARSER CLICK&SCOUT (.dvw)
# ==========================================================
def parse_dvw(file_text, target_set=None):
    lines = file_text.splitlines()
    teams = {"home": "Home", "opp": "Opponent"}
    opp_players = {}
    
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        if line == "[3TEAMS]":
            idx += 1
            if idx < len(lines) and len(lines[idx].split(";")) >= 2:
                teams["home"] = lines[idx].split(";")[1]
            idx += 1
            if idx < len(lines) and len(lines[idx].split(";")) >= 2:
                teams["opp"] = lines[idx].split(";")[1]
        elif line == "[3PLAYERS-V]":
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

    rotations = {
        p: {
            "attacks": [],
            "serves": [],
            "att_dist": defaultdict(int),
            "bases": defaultdict(int),
            "total_att": 0
        }
        for p in range(1, 7)
    }
    
    reception_stats = defaultdict(lambda: {"#": 0, "+": 0, "!": 0, "-": 0, "/": 0, "=": 0, "tot": 0})
    attack_stats = defaultdict(lambda: {"#": 0, "+": 0, "-": 0, "/": 0, "=": 0, "tot": 0})
    
    current_set = 1

    for row in lines[idx:]:
        parts = row.split(";")
        if not parts or not parts[0]:
            continue
            
        code = parts[0]
        
        if "**" in code and "set" in code:
            m = re.search(r"\*\*(\d)set", code)
            if m:
                current_set = int(m.group(1)) + 1
            continue
            
        if target_set is not None and current_set != target_set:
            continue

        opp_lineup = parts[19:25] if len(parts) >= 25 else []
        
        p_rot = 1
        setter_num = "1"
        for num, pinfo in opp_players.items():
            if pinfo.get("role") == "5" or "P" in pinfo.get("name", "") or num == "01":
                setter_num = str(int(num))
                break
                
        if setter_num in opp_lineup:
            p_rot = opp_lineup.index(setter_num) + 1
        
        if not code.startswith("a") or len(code) < 4:
            continue
            
        player = code[1:3]
        skill = code[3]
        eval_char = code[5] if len(code) > 5 else ""
        
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
                rotations[p_rot]["attacks"].append((player, start_z, end_z, eval_char))
                
                p_role = opp_players.get(player, {}).get("role", "")
                if start_z == "3" or p_role == "4" or "C" in opp_players.get(player, {}).get("name", ""):
                    if end_z in ["2", "1"]:
                        rotations[p_rot]["bases"]["K7"] += 1
                    elif end_z in ["4", "5"]:
                        rotations[p_rot]["bases"]["K1"] += 1
                    else:
                        rotations[p_rot]["bases"]["KC"] += 1

        # 3. BATTUTA
        elif skill == "S":
            if start_z and end_z:
                rotations[p_rot]["serves"].append((player, start_z, end_z, eval_char))

    return {
        "teams": teams,
        "players": opp_players,
        "rotations": rotations,
        "reception": reception_stats,
        "attack": attack_stats
    }


# ==========================================================
# DISEGNO CAMPO E TRAIETTORIE
# ==========================================================
def draw_court(c, x, y, w, h):
    c.setFillColor(colors.HexColor("#FDF2E9"))
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.rect(x, y, w, h, fill=1, stroke=1)
    
    # Rete
    c.setStrokeColor(colors.HexColor("#C0392B"))
    c.setLineWidth(2)
    c.line(x, y + h, x + w, y + h)
    
    # Linea 3 Metri
    c.setStrokeColor(colors.HexColor("#BDC3C7"))
    c.setLineWidth(1)
    c.line(x, y + h * 0.66, x + w, y + h * 0.66)
    
    # Divisione zone tratteggiata
    c.setStrokeColor(colors.HexColor("#E5E7E9"))
    c.setLineWidth(0.5)
    c.setDash(2, 2)
    c.line(x + w * 0.33, y, x + w * 0.33, y + h)
    c.line(x + w * 0.66, y, x + w * 0.66, y + h)
    c.line(x, y + h * 0.33, x + w, y + h * 0.33)
    c.setDash()


def draw_arrow(c, x1, y1, x2, y2, color, is_serve=False):
    c.setStrokeColor(color)
    c.setFillColor(color)
    c.setLineWidth(1.2 if not is_serve else 0.9)
    if is_serve:
        c.setDash(2, 2)
    else:
        c.setDash()
    c.line(x1, y1, x2, y2)
    c.setDash()
    c.circle(x2, y2, 1.8, fill=1, stroke=1)


# ==========================================================
# GENERAZIONE SCHEDA LIVE GRAFICA
# ==========================================================
def generate_tactical_pdf(data, set_label="Gara Completa"):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)
    
    # Intestazione
    c.setFillColor(colors.HexColor("#1A252F"))
    c.rect(0, height - 42, width, 42, fill=1, stroke=0)
    
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(25, height - 25, f"VERIFICA LIVE: {data['teams']['opp']} vs {data['teams']['home']}")
    c.setFont("Helvetica", 9)
    c.drawString(25, height - 37, f"Analisi Set: {set_label}  |  Distribuzione Palleggiatore, Traiettorie & Basi Centrale")

    # Legenda colori frecce
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor("#27AE60"))
    c.drawString(width - 250, height - 25, "■ Punto (#)")
    c.setFillColor(colors.HexColor("#E74C3C"))
    c.drawString(width - 190, height - 25, "■ Errore/Murato (=, /)")
    c.setFillColor(colors.HexColor("#2980B9"))
    c.drawString(width - 95, height - 25, "■ In Gioco (+, -)")

    positions = [1, 6, 5, 4, 3, 2]
    grid_coords = [
        (25, height - 265),
        (225, height - 265),
        (425, height - 265),
        (25, height - 495),
        (225, height - 495),
        (425, height - 495)
    ]
    
    box_w, box_h = 190, 220
    court_w, court_h = 100, 125

    for idx, p in enumerate(positions):
        bx, by = grid_coords[idx]
        rot = data["rotations"][p]
        
        c.setStrokeColor(colors.HexColor("#BDC3C7"))
        c.setLineWidth(0.8)
        c.rect(bx, by, box_w, box_h)
        
        c.setFillColor(colors.HexColor("#34495E"))
        c.rect(bx, by + box_h - 18, box_w, 18, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(bx + 6, by + box_h - 13, f"FASE P{p} (Palleggiatore in Zona {p})")
        
        cx, cy = bx + 6, by + 12
        draw_court(c, cx, cy, court_w, court_h)
        
        # Traiettorie Attacco
        for att in rot["attacks"]:
            plyr, sz, ez, ev = att
            if sz in ZONE_COORDS and ez in OPP_ZONE_COORDS:
                x1 = cx + ZONE_COORDS[sz][0] * court_w
                y1 = cy + (1.0 - ZONE_COORDS[sz][1]) * court_h
                x2 = cx + OPP_ZONE_COORDS[ez][0] * court_w
                y2 = cy + court_h
                
                arr_col = colors.HexColor("#27AE60") if ev == "#" else (
                    colors.HexColor("#E74C3C") if ev in ["=", "/"] else colors.HexColor("#2980B9")
                )
                draw_arrow(c, x1, y1, x2, y2, arr_col)

        # Dati a destra nel riquadro
        dx = bx + court_w + 12
        tot_att = max(1, rot["total_att"])
        p4 = rot["att_dist"].get("4", 0)
        p3 = rot["att_dist"].get("3", 0)
        p2 = rot["att_dist"].get("2", 0)
        
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(dx, by + box_h - 32, "DISTRIBUZIONE:")
        c.setFont("Helvetica", 7.5)
        c.drawString(dx, by + box_h - 44, f"P4: {p4} ({p4*100//tot_att}%)")
        c.drawString(dx, by + box_h - 55, f"P3: {p3} ({p3*100//tot_att}%)")
        c.drawString(dx, by + box_h - 66, f"P2: {p2} ({p2*100//tot_att}%)")
        
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(dx, by + box_h - 85, "BASI C1/C2:")
        c.setFont("Helvetica", 7)
        c.drawString(dx, by + box_h - 96, f"K1 (Avanti): {rot['bases'].get('K1', 0)}")
        c.drawString(dx, by + box_h - 106, f"KC (Centro): {rot['bases'].get('KC', 0)}")
        c.drawString(dx, by + box_h - 116, f"K7 (Fast): {rot['bases'].get('K7', 0)}")
        
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(dx, by + box_h - 135, "BATTUTE:")
        c.setFont("Helvetica", 7)
        serv_cnt = len(rot["serves"])
        c.drawString(dx, by + box_h - 146, f"Tot: {serv_cnt}")
        if rot["serves"]:
            s_ply, s_sz, s_ez, _ = rot["serves"][-1]
            c.drawString(dx, by + box_h - 156, f"Ult: #{s_ply} Z{s_sz}»Z{s_ez}")

    # Pannello Destro Giocatori
    sx = 625
    sy = height - 495
    sw = width - sx - 20
    sh = 450
    
    c.setStrokeColor(colors.HexColor("#2C3E50"))
    c.setLineWidth(1)
    c.rect(sx, sy, sw, sh)
    
    c.setFillColor(colors.HexColor("#2C3E50"))
    c.rect(sx, sy + sh - 20, sw, 20, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(sx + 8, sy + sh - 14, "ANALISI GIOCATORI AVVERSARI")
    
    # RICEZIONE
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(sx + 8, sy + sh - 35, "RICEZIONE (Target):")
    
    rec_sorted = []
    for num, st_r in data["reception"].items():
        if st_r["tot"] > 0:
            pos_pct = (st_r["#"] + st_r["+"]) / st_r["tot"] * 100
            prf_pct = st_r["#"] / st_r["tot"] * 100
            rec_sorted.append((num, st_r["tot"], pos_pct, prf_pct, st_r["="]))
    rec_sorted.sort(key=lambda x: x[2])
    
    c.setFont("Helvetica", 7)
    c.drawString(sx + 8, sy + sh - 48, "#   Nome/Ruolo    Tot   Pos%   Prf%   Err")
    c.line(sx + 8, sy + sh - 51, sx + sw - 8, sy + sh - 51)
    
    ry = sy + sh - 62
    for r in rec_sorted[:5]:
        pname = data["players"].get(r[0], {}).get("name", "")[:10]
        c.drawString(sx + 8, ry, f"#{r[0]}  {pname:<11} {r[1]:<4} {r[2]:.0f}%   {r[3]:.0f}%    {r[4]}")
        ry -= 11

    # ATTACCO
    c.setFont("Helvetica-Bold", 8)
    c.drawString(sx + 8, ry - 10, "ATTACCO (Volume/Efficienza):")
    
    att_sorted = []
    for num, st_a in data["attack"].items():
        if st_a["tot"] > 0:
            eff = ((st_a["#"] - st_a["="] - st_a["/"]) / st_a["tot"]) * 100
            pt_pct = st_a["#"] / st_a["tot"] * 100
            att_sorted.append((num, st_a["tot"], st_a["#"], eff, pt_pct))
    att_sorted.sort(key=lambda x: x[1], reverse=True)
    
    c.setFont("Helvetica", 7)
    c.drawString(sx + 8, ry - 23, "#   Nome/Ruolo    Tot   Pt    Eff%   Pt%")
    c.line(sx + 8, ry - 26, sx + sw - 8, ry - 26)
    
    ay = ry - 37
    for a in att_sorted[:6]:
        pname = data["players"].get(a[0], {}).get("name", "")[:10]
        c.drawString(sx + 8, ay, f"#{a[0]}  {pname:<11} {a[1]:<4} {a[2]:<4} {a[3]:.0f}%   {a[4]:.0f}%")
        ay -= 11

    # INDICAZIONI CHIAVE
    c.setFont("Helvetica-Bold", 8)
    c.drawString(sx + 8, ay - 12, "INDICAZIONI CHIAVE:")
    c.setFont("Helvetica", 7)
    if rec_sorted:
        c.drawString(sx + 8, ay - 24, f"• Target Battuta: #{rec_sorted[0][0]} ({rec_sorted[0][2]:.0f}% Pos)")
    if att_sorted:
        c.drawString(sx + 8, ay - 35, f"• Attaccante Focus: #{att_sorted[0][0]} ({att_sorted[0][1]} palloni)")
        strongest = max(att_sorted, key=lambda x: x[3])
        c.drawString(sx + 8, ay - 46, f"• Più Efficace: #{strongest[0]} ({strongest[3]:.0f}% Eff)")

    c.setFont("Helvetica-Oblique", 7)
    c.drawString(sx + 8, sy + 8, "Elaborazione automatica live Click&Scout")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


# ==========================================================
# INTERFACCIA STREAMLIT CON UNIONE DOSSIER PRE-GARA
# ==========================================================
def main():
    st.set_page_config(page_title="Volley Scout Dashboard", layout="wide")
    
    st.title("🏐 Elaboratore Tattico Click&Scout")
    st.write("Genera il Dossier Strategico completo: il tuo piano pre-gara affiancato alla verifica reale live dei 6 campi.")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("1. Piano Pre-Gara (Facoltativo)")
        prematch_pdf = st.file_uploader("Carica il PDF compilato prima della gara:", type=["pdf"])
    with col2:
        st.subheader("2. File Scout Live")
        uploaded_dvw = st.file_uploader("Trascina qui il file .dvw di Click&Scout:", type=["dvw"])
    
    if uploaded_dvw:
        file_text = uploaded_dvw.getvalue().decode("utf-8", errors="ignore")
        
        col_set, _ = st.columns([2, 4])
        with col_set:
            selected_set_str = st.selectbox(
                "Seleziona il Set da analizzare:",
                ["Gara Completa", "Set 1", "Set 2", "Set 3", "Set 4", "Set 5"]
            )
            
        target_set = None if selected_set_str == "Gara Completa" else int(selected_set_str.split(" ")[1])
        data = parse_dvw(file_text, target_set=target_set)
        
        if not data:
            st.error("File non valido o privo di dati scout.")
            return
            
        st.success(f"Dati scout elaborati: **{data['teams']['opp']}** vs **{data['teams']['home']}**")
        
        # Genera il PDF live con i 6 campi grafici
        live_pdf_buffer = generate_tactical_pdf(data, set_label=selected_set_str)
        
        # Unione se presente il piano pre-gara
        if prematch_pdf:
            merger = PdfWriter()
            
            # Aggiunge tutte le pagine del modello preparato prima
            reader_pre = PdfReader(prematch_pdf)
            for page in reader_pre.pages:
                merger.add_page(page)
                
            # Aggiunge la pagina di verifica reale live
            reader_live = PdfReader(live_pdf_buffer)
            for page in reader_live.pages:
                merger.add_page(page)
                
            final_buffer = io.BytesIO()
            merger.write(final_buffer)
            final_buffer.seek(0)
            
            download_data = final_buffer
            download_label = "📄 Scarica Dossier Completo (Piano Pre-Gara + Dati Live)"
            file_name_out = f"Dossier_Strategico_{data['teams']['opp']}_{selected_set_str.replace(' ', '_')}.pdf"
        else:
            download_data = live_pdf_buffer
            download_label = "📄 Scarica Scheda Tattica Grafica Live (PDF)"
            file_name_out = f"Verifica_Live_{data['teams']['opp']}_{selected_set_str.replace(' ', '_')}.pdf"

        st.download_button(
            label=download_label,
            data=download_data,
            file_name=file_name_out,
            mime="application/pdf"
        )

if __name__ == "__main__":
    main()
