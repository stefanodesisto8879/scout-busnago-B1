import io
import math
import re
from collections import defaultdict
import streamlit as st
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.pdfgen import canvas

# ==========================================================
# COORDINATE CAMPO RIGOROSE (DENOMINAZIONE ESATTA SOTTOZONE)
# ==========================================================
ATTACK_ORIGIN_FULL = {
    "2": (0.17, 0.53),
    "3": (0.50, 0.53),
    "4": (0.83, 0.53),
    "9": (0.17, 0.70),
    "8": (0.50, 0.70),
    "7": (0.83, 0.70),
    "1": (0.17, 0.88),
    "6": (0.50, 0.88),
    "5": (0.83, 0.88),
}

DEFENSE_TARGET_FULL = {
    "4": (0.17, 0.44),
    "3": (0.50, 0.44),
    "2": (0.83, 0.44),
    "9": (0.17, 0.28),
    "8": (0.50, 0.28),
    "7": (0.83, 0.28),
    "5": (0.17, 0.11),
    "6": (0.50, 0.11),
    "1": (0.83, 0.11),
}

SERVE_TARGET = {
    "4": (0.17, 0.70), "3": (0.50, 0.70), "2": (0.83, 0.70),
    "9": (0.17, 0.45), "8": (0.50, 0.45), "7": (0.83, 0.45),
    "5": (0.17, 0.18), "6": (0.50, 0.18), "1": (0.83, 0.18),
}

# ==========================================================
# PARSER CLICK&SCOUT (.dvw)
# ==========================================================
def parse_dvw(file_text, target_set=None):
    lines = file_text.splitlines()
    teams = {"home": "Busnago", "opp": "Avversario"}
    home_players = {}
    opp_players = {}
    
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        if line == "[3TEAMS]":
            idx += 1
            if idx < len(lines):
                p_h = lines[idx].split(";")
                if len(p_h) >= 2: teams["home"] = p_h[1]
            idx += 1
            if idx < len(lines):
                p_o = lines[idx].split(";")
                if len(p_o) >= 2: teams["opp"] = p_o[1]
        elif line == "[3PLAYERS-H]":
            idx += 1
            while idx < len(lines) and not lines[idx].startswith("[3"):
                row = lines[idx].split(";")
                if len(row) > 9:
                    num = row[1].zfill(2)
                    name = row[9] if row[9] else f"#{row[1]}"
                    role = row[12] if len(row) > 12 else ""
                    home_players[num] = {"name": name, "role": role}
                idx += 1
            continue
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
            "serves_data": [],
            "att_dist": defaultdict(int),
            "bases": defaultdict(int),
            "total_att": 0
        }
        for p in range(1, 7)
    }
    
    opp_rec = defaultdict(lambda: {"#": 0, "+": 0, "!": 0, "-": 0, "/": 0, "=": 0, "tot": 0})
    opp_att = defaultdict(lambda: {"#": 0, "+": 0, "-": 0, "/": 0, "=": 0, "tot": 0, "attacks": []})
    
    home_rec = defaultdict(lambda: {"#": 0, "+": 0, "!": 0, "-": 0, "/": 0, "=": 0, "tot": 0})
    home_att = defaultdict(lambda: {"#": 0, "+": 0, "-": 0, "/": 0, "=": 0, "tot": 0, "attacks": []})
    home_srv = defaultdict(lambda: {"#": 0, "+": 0, "-": 0, "/": 0, "=": 0, "tot": 0})
    
    skill_points = {
        "home": {"attack": 0, "serve": 0, "block": 0},
        "opp": {"attack": 0, "serve": 0, "block": 0}
    }

    home_errors = {"attack": 0, "serve": 0}
    phase_stats = {
        "home": {"cp_tot": 0, "cp_kill": 0, "bp_tot": 0, "bp_kill": 0},
        "opp": {"cp_tot": 0, "cp_kill": 0, "bp_tot": 0, "bp_kill": 0}
    }
    
    current_set = 1
    last_serve_team = None

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
            if pinfo.get("role") == "5" or "P" in pinfo.get("name", "") or num == "01" or num == "1":
                setter_num = str(int(num))
                break
                
        if setter_num in opp_lineup:
            p_rot = opp_lineup.index(setter_num) + 1
        
        if len(code) < 4:
            continue
            
        team_char = code[0]
        player = code[1:3]
        skill = code[3]
        eval_char = code[5] if len(code) > 5 else ""
        
        traj_match = re.search(r"~(\d)(\d)", code)
        start_z = traj_match.group(1) if traj_match else ""
        end_z = traj_match.group(2) if traj_match else ""

        if skill == "S":
            last_serve_team = team_char

        # ---------------- NOSTRA SQUADRA (*) ----------------
        if team_char == "*":
            if skill == "S":
                home_srv[player]["tot"] += 1
                if eval_char == "#": skill_points["home"]["serve"] += 1
                if eval_char == "=": home_errors["serve"] += 1
                if eval_char in home_srv[player]: home_srv[player][eval_char] += 1

            elif skill == "B":
                if eval_char == "#": skill_points["home"]["block"] += 1

            elif skill == "R":
                home_rec[player]["tot"] += 1
                if eval_char in home_rec[player]: home_rec[player][eval_char] += 1

            elif skill == "A":
                home_att[player]["tot"] += 1
                if eval_char == "#": skill_points["home"]["attack"] += 1
                if eval_char in ["=", "/"]: home_errors["attack"] += 1
                if eval_char in home_att[player]: home_att[player][eval_char] += 1
                
                is_kill = (eval_char == "#")
                if last_serve_team == "a":
                    phase_stats["home"]["cp_tot"] += 1
                    if is_kill: phase_stats["home"]["cp_kill"] += 1
                else:
                    phase_stats["home"]["bp_tot"] += 1
                    if is_kill: phase_stats["home"]["bp_kill"] += 1

        # ---------------- AVVERSARI (a) ----------------
        elif team_char == "a":
            if skill == "S":
                if eval_char == "#": skill_points["opp"]["serve"] += 1
                if end_z:
                    rotations[p_rot]["serves_data"].append((player, start_z, end_z, eval_char))

            elif skill == "B":
                if eval_char == "#": skill_points["opp"]["block"] += 1

            elif skill == "R":
                opp_rec[player]["tot"] += 1
                if eval_char in opp_rec[player]: opp_rec[player][eval_char] += 1
                    
            elif skill == "A":
                opp_att[player]["tot"] += 1
                if eval_char == "#": skill_points["opp"]["attack"] += 1
                if eval_char in opp_att[player]: opp_att[player][eval_char] += 1
                    
                is_kill = (eval_char == "#")
                if last_serve_team == "*":
                    phase_stats["opp"]["cp_tot"] += 1
                    if is_kill: phase_stats["opp"]["cp_kill"] += 1
                else:
                    phase_stats["opp"]["bp_tot"] += 1
                    if is_kill: phase_stats["opp"]["bp_kill"] += 1

                if start_z:
                    att_rec = (player, start_z, end_z, eval_char)
                    rotations[p_rot]["total_att"] += 1
                    rotations[p_rot]["att_dist"][start_z] += 1
                    rotations[p_rot]["attacks"].append(att_rec)
                    opp_att[player]["attacks"].append(att_rec)
                    
                    p_role = opp_players.get(player, {}).get("role", "")
                    if start_z == "3" or p_role == "4" or "C" in opp_players.get(player, {}).get("name", ""):
                        if end_z in ["2", "1", "7"]:
                            rotations[p_rot]["bases"]["K7"] += 1
                        elif end_z in ["4", "5", "9"]:
                            rotations[p_rot]["bases"]["K1"] += 1
                        else:
                            rotations[p_rot]["bases"]["KC"] += 1

    return {
        "teams": teams,
        "home_players": home_players,
        "opp_players": opp_players,
        "rotations": rotations,
        "opp_reception": opp_rec,
        "opp_attack": opp_att,
        "home_reception": home_rec,
        "home_attack": home_att,
        "home_errors": home_errors,
        "phase_stats": phase_stats,
        "skill_points": skill_points
    }

# ==========================================================
# MOTORE GRAFICO VETTORIALE (FRECCE & PUNTINE)
# ==========================================================
def draw_trajectory(c, x1, y1, x2, y2, color, line_w=1.4):
    c.setFillColor(color)
    c.circle(x1, y1, 2.5, fill=1, stroke=0)
    
    c.setStrokeColor(color)
    c.setLineWidth(line_w)
    c.line(x1, y1, x2, y2)
    
    ang = math.atan2(y2 - y1, x2 - x1)
    alen = 6.0
    awid = math.pi / 5.5
    
    p = c.beginPath()
    p.moveTo(x2, y2)
    p.lineTo(x2 - alen * math.cos(ang - awid), y2 - alen * math.sin(ang - awid))
    p.lineTo(x2 - alen * math.cos(ang + awid), y2 - alen * math.sin(ang + awid))
    p.close()
    c.drawPath(p, fill=1, stroke=0)

# ==========================================================
# CAMPO BIANCO CON SOTTOZONE CLICK&SCOUT
# ==========================================================
def draw_full_pitch(c, x, y, w, h, attacks_list, p_dist=None, total_att=None):
    c.setFillColor(colors.HexColor("#FFFFFF"))
    c.setStrokeColor(colors.black)
    c.setLineWidth(1.2)
    c.rect(x, y, w, h, fill=1, stroke=1)
    
    net_y = y + h * 0.50
    half_h = h * 0.50
    w_third = w / 3.0
    h_third = half_h / 3.0

    c.setStrokeColor(colors.black)
    c.setLineWidth(2.8)
    c.line(x, net_y, x + w, net_y)

    c.setStrokeColor(colors.black)
    c.setLineWidth(1.0)
    c.line(x, net_y + h_third, x + w, net_y + h_third)
    c.line(x, net_y - h_third, x + w, net_y - h_third)

    c.setStrokeColor(colors.HexColor("#F5B7B1"))
    c.setLineWidth(0.8)
    c.setDash(3, 3)

    c.line(x + w_third, y, x + w_third, y + h)
    c.line(x + 2 * w_third, y, x + 2 * w_third, y + h)
    c.line(x, net_y + 2 * h_third, x + w, net_y + 2 * h_third)
    c.line(x, net_y - 2 * h_third, x + w, net_y - 2 * h_third)
    c.setDash()

    c.setFont("Helvetica", 6)
    c.setFillColor(colors.black)
    c.drawString(x + 3, net_y + 2 * h_third + h_third - 7, "1")
    c.drawString(x + w_third + 3, net_y + 2 * h_third + h_third - 7, "6")
    c.drawString(x + 2 * w_third + 3, net_y + 2 * h_third + h_third - 7, "5")

    c.drawString(x + 3, net_y + h_third + h_third - 7, "9")
    c.drawString(x + w_third + 3, net_y + h_third + h_third - 7, "8")
    c.drawString(x + 2 * w_third + 3, net_y + h_third + h_third - 7, "7")

    c.drawString(x + 3, net_y + h_third - 7, "2")
    c.drawString(x + w_third + 3, net_y + h_third - 7, "3")
    c.drawString(x + 2 * w_third + 3, net_y + h_third - 7, "4")

    c.setFont("Helvetica-Bold", 7.5)
    c.drawCentredString(x + w_third * 0.5, net_y - h_third * 0.5 - 3, "4")
    c.drawCentredString(x + w_third * 1.5, net_y - h_third * 0.5 - 3, "3")
    c.drawCentredString(x + w_third * 2.5, net_y - h_third * 0.5 - 3, "2")

    c.drawCentredString(x + w_third * 0.5, net_y - h_third * 1.5 - 3, "9")
    c.drawCentredString(x + w_third * 1.5, net_y - h_third * 1.5 - 3, "8")
    c.drawCentredString(x + w_third * 2.5, net_y - h_third * 1.5 - 3, "7")

    c.drawCentredString(x + w_third * 0.5, net_y - h_third * 2.5 - 3, "5")
    c.drawCentredString(x + w_third * 1.5, net_y - h_third * 2.5 - 3, "6")
    c.drawCentredString(x + w_third * 2.5, net_y - h_third * 2.5 - 3, "1")

    if p_dist and total_att and total_att > 0:
        p4 = p_dist.get("4", 0)
        p3 = p_dist.get("3", 0)
        p2 = p_dist.get("2", 0)
        
        c.setFillColor(colors.HexColor("#2C3E50"))
        c.rect(x + 1, net_y + 11, 28, 9, fill=1, stroke=0)
        c.rect(x + w/2 - 14, net_y + 11, 28, 9, fill=1, stroke=0)
        c.rect(x + w - 29, net_y + 11, 28, 9, fill=1, stroke=0)
        
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 6)
        c.drawString(x + 3, net_y + 13, f"2:{p2*100//total_att}%")
        c.drawString(x + w/2 - 12, net_y + 13, f"3:{p3*100//total_att}%")
        c.drawString(x + w - 27, net_y + 13, f"4:{p4*100//total_att}%")

    for att in attacks_list:
        _, sz, ez, ev = att
        if sz in ATTACK_ORIGIN_FULL and ez in DEFENSE_TARGET_FULL:
            x1 = x + ATTACK_ORIGIN_FULL[sz][0] * w
            y1 = y + ATTACK_ORIGIN_FULL[sz][1] * h
            x2 = x + DEFENSE_TARGET_FULL[ez][0] * w
            y2 = y + DEFENSE_TARGET_FULL[ez][1] * h
            
            if ev == "#":
                col = colors.HexColor("#27AE60")
                lw = 1.6
            elif ev in ["=", "/"]:
                col = colors.HexColor("#E74C3C")
                lw = 1.6
            else:
                col = colors.HexColor("#F39C12")
                lw = 1.1
            draw_trajectory(c, x1, y1, x2, y2, col, line_w=lw)

# ==========================================================
# BOX BATTITORE BIANCO
# ==========================================================
def draw_serve_box_with_player(c, x, y, w, h, serves_list, players_dict):
    server_counts = defaultdict(int)
    for p, _, _, _ in serves_list:
        server_counts[p] += 1
        
    main_server = max(server_counts, key=server_counts.get) if server_counts else None
    
    header_h = 22
    c.setFillColor(colors.HexColor("#34495E"))
    c.rect(x, y + h - header_h, w, header_h, fill=1, stroke=0)
    
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawString(x + 4, y + h - 8, "BATTITORE:")
    
    if main_server:
        s_name = players_dict.get(main_server, {}).get("name", "")[:12]
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(x + 4, y + h - 18, f"#{main_server} {s_name}")
    else:
        c.setFont("Helvetica", 6.5)
        c.drawString(x + 4, y + h - 18, "Nessun dato")

    court_h = h - header_h
    c.setFillColor(colors.HexColor("#FFFFFF"))
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.8)
    c.rect(x, y, w, court_h, fill=1, stroke=1)
    
    c.setStrokeColor(colors.black)
    c.setLineWidth(2.0)
    c.line(x, y + court_h, x + w, y + court_h)

    c.setStrokeColor(colors.HexColor("#F5B7B1"))
    c.setLineWidth(0.6)
    c.setDash(2, 2)
    w_th = w / 3.0
    h_th = court_h / 3.0
    c.line(x + w_th, y, x + w_th, y + court_h)
    c.line(x + 2 * w_th, y, x + 2 * w_th, y + court_h)
    c.line(x, y + h_th, x + w, y + h_th)
    c.line(x, y + 2 * h_th, x + w, y + 2 * h_th)
    c.setDash()

    c.setFont("Helvetica", 5.5)
    c.setFillColor(colors.HexColor("#BDC3C7"))
    c.drawCentredString(x + w_th * 0.5, y + h_th * 2.5 - 2, "4")
    c.drawCentredString(x + w_th * 1.5, y + h_th * 2.5 - 2, "3")
    c.drawCentredString(x + w_th * 2.5, y + h_th * 2.5 - 2, "2")
    c.drawCentredString(x + w_th * 0.5, y + h_th * 1.5 - 2, "9")
    c.drawCentredString(x + w_th * 1.5, y + h_th * 1.5 - 2, "8")
    c.drawCentredString(x + w_th * 2.5, y + h_th * 1.5 - 2, "7")
    c.drawCentredString(x + w_th * 0.5, y + h_th * 0.5 - 2, "5")
    c.drawCentredString(x + w_th * 1.5, y + h_th * 0.5 - 2, "6")
    c.drawCentredString(x + w_th * 2.5, y + h_th * 0.5 - 2, "1")

    counts = defaultdict(int)
    for _, _, ez, _ in serves_list:
        if ez: counts[ez] += 1

    max_c = max(counts.values()) if counts else 0

    for zn, cnt in counts.items():
        if zn in SERVE_TARGET and cnt > 0:
            zx = x + SERVE_TARGET[zn][0] * w
            zy = y + SERVE_TARGET[zn][1] * court_h
            
            if cnt == max_c and max_c > 1:
                c.setFillColor(colors.HexColor("#8E44AD"))
                rad = 7.5
            else:
                c.setFillColor(colors.HexColor("#2C3E50"))
                rad = 6.0
                
            c.circle(zx, zy, rad, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 7.5)
            c.drawCentredString(zx, zy - 2.6, str(cnt))

# ==========================================================
# GENERATORE PDF (PAGINA 1 CON BOX METRICHE OTTIMIZZATO)
# ==========================================================
def generate_pdf(data, set_label="Gara"):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4))
    width, height = landscape(A4)
    
    # ----------------------------------------------------
    # HEADER PAGINA 1
    # ----------------------------------------------------
    c.setFillColor(colors.HexColor("#1A252F"))
    c.rect(0, height - 34, width, 34, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20, height - 20, f"STUDIO TATTICO LIVE: {data['teams']['opp']} vs {data['teams']['home']}")
    c.setFont("Helvetica", 8)
    c.drawString(20, height - 30, f"Analisi: {set_label}  |  Campo con Sottozone 1-9  |  Analisi Live e Decisioni Tattiche")

    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(colors.HexColor("#27AE60"))
    c.drawString(width - 240, height - 20, "• Punto (#)")
    c.setFillColor(colors.HexColor("#E74C3C"))
    c.drawString(width - 180, height - 20, "• Errore/Murato (=, /)")
    c.setFillColor(colors.HexColor("#F39C12"))
    c.drawString(width - 90, height - 20, "• In Gioco (+, -)")

    positions = [1, 6, 5, 4, 3, 2]
    coords = [
        (20, height - 262), (222, height - 262), (424, height - 262),
        (20, height - 500), (222, height - 500), (424, height - 500)
    ]
    
    bw, bh = 196, 228
    cw, ch = 98, 196

    for idx, p in enumerate(positions):
        bx, by = coords[idx]
        rot = data["rotations"][p]
        
        c.setStrokeColor(colors.HexColor("#BDC3C7"))
        c.setLineWidth(0.8)
        c.rect(bx, by, bw, bh)
        
        c.setFillColor(colors.HexColor("#2C3E50"))
        c.rect(bx, by + bh - 16, bw, 16, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(bx + 6, by + bh - 12, f"FASE P{p} (P in Z{p}) - {rot['total_att']} Attacchi")
        
        cx, cy = bx + 5, by + 8
        draw_full_pitch(c, cx, cy, cw, ch, rot["attacks"], p_dist=rot["att_dist"], total_att=rot["total_att"])
        
        sx, sy = bx + cw + 10, by + 8
        sw, sh = bw - cw - 15, 80
        draw_serve_box_with_player(c, sx, sy, sw, sh, rot["serves_data"], data["opp_players"])
        
        dx = bx + cw + 10
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(dx, by + bh - 26, "BASI C1/C2:")
        c.setFont("Helvetica", 7)
        c.drawString(dx, by + bh - 38, f"• K1: {rot['bases'].get('K1', 0)}")
        c.drawString(dx, by + bh - 48, f"• KC: {rot['bases'].get('KC', 0)}")
        c.drawString(dx, by + bh - 58, f"• K7: {rot['bases'].get('K7', 0)}")

    # ----------------------------------------------------
    # PANNELLO DESTRO METRICHE (DESIGN RINNOVATO SENZA EMOJI ROTTI)
    # ----------------------------------------------------
    px = 626
    py = height - 500
    pw = width - px - 15
    ph = 466
    
    c.setFillColor(colors.HexColor("#F8F9FA"))
    c.rect(px, py, pw, ph, fill=1, stroke=0)
    c.setStrokeColor(colors.HexColor("#CFD8DC"))
    c.setLineWidth(1)
    c.rect(px, py, pw, ph, fill=0, stroke=1)

    # Intestazione pannello
    c.setFillColor(colors.HexColor("#263238"))
    c.rect(px, py + ph - 22, pw, 22, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(px + 10, py + ph - 15, "CONFRONTO SQUADRE & TARGET TATTICI")

    c_y = py + ph - 26

    # ====================================================
    # 1. CONFRONTO PUNTI DIRETTI (SENZA SOVRAPPOSIZIONI)
    # ====================================================
    card_pts_h = 68
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.HexColor("#CFD8DC"))
    c.rect(px + 6, c_y - card_pts_h, pw - 12, card_pts_h, fill=1, stroke=1)

    # Titolo a sinistra
    c.setFillColor(colors.HexColor("#263238"))
    c.setFont("Helvetica-Bold", 7.2)
    c.drawString(px + 10, c_y - 12, "PUNTI DIRETTI")

    # Legenda ben distanziata a destra
    c.setFillColor(colors.HexColor("#1B4F72"))
    c.circle(px + pw - 90, c_y - 10, 3, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 6.8)
    c.drawString(px + pw - 84, c_y - 12, "Busnago")

    c.setFillColor(colors.HexColor("#D35400"))
    c.circle(px + pw - 42, c_y - 10, 3, fill=1, stroke=0)
    c.drawString(px + pw - 36, c_y - 12, "Avv")

    sp = data["skill_points"]
    h_att_pts, o_att_pts = sp["home"]["attack"], sp["opp"]["attack"]
    h_ace_pts, o_ace_pts = sp["home"]["serve"], sp["opp"]["serve"]
    h_blk_pts, o_blk_pts = sp["home"]["block"], sp["opp"]["block"]

    def draw_skill_row(y_pos, label, val_h, val_o):
        c.setFont("Helvetica-Bold", 6.8)
        c.setFillColor(colors.HexColor("#455A64"))
        c.drawString(px + 10, y_pos + 1, label)
        
        c.setFillColor(colors.HexColor("#1B4F72"))
        c.drawString(px + 52, y_pos + 1, f"{val_h:>2}")
        c.setFillColor(colors.HexColor("#90A4AE"))
        c.drawString(px + 64, y_pos + 1, "vs")
        c.setFillColor(colors.HexColor("#D35400"))
        c.drawString(px + 76, y_pos + 1, f"{val_o:<2}")

        max_v = max(1, val_h + val_o)
        b_x = px + 92
        b_w = pw - 106
        w_h = (val_h / max_v) * b_w
        w_o = (val_o / max_v) * b_w
        
        c.setFillColor(colors.HexColor("#2980B9"))
        c.rect(b_x, y_pos, max(2, w_h), 5.5, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#E67E22"))
        c.rect(b_x + max(2, w_h) + 1.5, y_pos, max(2, w_o), 5.5, fill=1, stroke=0)

    draw_skill_row(c_y - 25, "Attacco", h_att_pts, o_att_pts)
    draw_skill_row(c_y - 38, "Ace", h_ace_pts, o_ace_pts)
    draw_skill_row(c_y - 51, "Muro", h_blk_pts, o_blk_pts)

    tot_h_pts = h_att_pts + h_ace_pts + h_blk_pts
    tot_o_pts = o_att_pts + o_ace_pts + o_blk_pts
    c.setFont("Helvetica-Bold", 6.8)
    c.setFillColor(colors.HexColor("#1B4F72") if tot_h_pts >= tot_o_pts else colors.HexColor("#D35400"))
    c.drawString(px + 10, c_y - 63, f"Totale Vincenti: Busnago {tot_h_pts}  -  Avversario {tot_o_pts}")

    c_y = c_y - card_pts_h - 4

    # ====================================================
    # 2. ERRORI DIRETTI & RENDIMENTO FASI (COMPATTO & PULITO)
    # ====================================================
    card_err_h = 42
    c.setFillColor(colors.HexColor("#FDEDEC"))
    c.setStrokeColor(colors.HexColor("#F5B7B1"))
    c.rect(px + 6, c_y - card_err_h, pw - 12, card_err_h, fill=1, stroke=1)
    
    err_att = data["home_errors"]["attack"]
    err_srv = data["home_errors"]["serve"]
    err_tot = err_att + err_srv
    
    c.setFillColor(colors.HexColor("#C0392B"))
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(px + 10, c_y - 11, "ERRORI DIRETTI BUSNAGO")
    
    # Badge circolare numero errori
    badge_x = px + pw - 22
    badge_y = c_y - 13
    c.circle(badge_x, badge_y, 9, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(badge_x, badge_y - 2.8, str(err_tot))

    ps = data["phase_stats"]
    h_cp = (ps["home"]["cp_kill"] / ps["home"]["cp_tot"] * 100) if ps["home"]["cp_tot"] > 0 else 0
    o_cp = (ps["opp"]["cp_kill"] / ps["opp"]["cp_tot"] * 100) if ps["opp"]["cp_tot"] > 0 else 0
    h_bp = (ps["home"]["bp_kill"] / ps["home"]["bp_tot"] * 100) if ps["home"]["bp_tot"] > 0 else 0
    o_bp = (ps["opp"]["bp_kill"] / ps["opp"]["bp_tot"] * 100) if ps["opp"]["bp_tot"] > 0 else 0

    c.setFillColor(colors.HexColor("#78281F"))
    c.setFont("Helvetica", 6.8)
    c.drawString(px + 10, c_y - 23, f"• Battuta: {err_srv} err  |  Attacco: {err_att} out o murati")
    c.drawString(px + 10, c_y - 34, f"• CP: Bus {h_cp:.0f}% vs Avv {o_cp:.0f}%  |  BP: Bus {h_bp:.0f}% vs Avv {o_bp:.0f}%")

    c_y = c_y - card_err_h - 4

    # ====================================================
    # 3. FOCUS BUSNAGO (BADGE COLORATI, ZERO EMOJI ROTTE)
    # ====================================================
    card_busnago_h = 114
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.HexColor("#1B4F72"))
    c.rect(px + 6, c_y - card_busnago_h, pw - 12, card_busnago_h, fill=1, stroke=1)

    c.setFillColor(colors.HexColor("#1B4F72"))
    c.rect(px + 6, c_y - 15, pw - 12, 15, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(px + 10, c_y - 11, "FOCUS BUSNAGO (NOSTRA SQUADRA)")

    c.setFont("Helvetica-Bold", 6.8)
    c.setFillColor(colors.HexColor("#2C3E50"))
    c.drawString(px + 10, c_y - 24, "RICEZIONE INDIVIDUALE (min. 5 ric):")

    c.setFont("Helvetica-Bold", 6.2)
    c.setFillColor(colors.HexColor("#7F8C8D"))
    c.drawString(px + 10, c_y - 33, "#  Nome         Tot    #+ %     Err %")
    c.setStrokeColor(colors.HexColor("#BDC3C7"))
    c.line(px + 10, c_y - 35, px + pw - 12, c_y - 35)

    rec_qual_list = []
    for num, st_r in data["home_reception"].items():
        if st_r["tot"] >= 5:
            pos_pct = ((st_r["#"] + st_r["+"]) / st_r["tot"]) * 100
            err_pct = (st_r["="] / st_r["tot"]) * 100
            rec_qual_list.append((num, st_r["tot"], pos_pct, err_pct))
    rec_qual_list.sort(key=lambda x: x[2])

    sub_y = c_y - 44
    if rec_qual_list:
        for r in rec_qual_list[:3]:
            pname = data["home_players"].get(r[0], {}).get("name", "")[:9]
            c.setFont("Helvetica", 6.5)
            c.setFillColor(colors.HexColor("#C0392B") if r[3] >= 15 else colors.HexColor("#2C3E50"))
            c.drawString(px + 10, sub_y, f"#{r[0]} {pname:<10} {r[1]:<4} {r[2]:.0f}%     {r[3]:.0f}%")
            sub_y -= 9.5
    else:
        c.setFont("Helvetica-Oblique", 6.5)
        c.setFillColor(colors.HexColor("#7F8C8D"))
        c.drawString(px + 10, sub_y, "Nessun giocatore con >= 5 ricezioni")
        sub_y -= 9.5

    c.setStrokeColor(colors.HexColor("#ECEFF1"))
    c.line(px + 10, sub_y + 2, px + pw - 12, sub_y + 2)
    sub_y -= 6

    h_att_list = []
    for num, st_a in data["home_attack"].items():
        if st_a["tot"] > 0:
            eff = ((st_a["#"] - st_a["="] - st_a["/"]) / st_a["tot"]) * 100
            h_att_list.append((num, st_a["tot"], st_a["#"], eff))
    h_att_list.sort(key=lambda x: x[1], reverse=True)
    top_vol_h = h_att_list[0] if h_att_list else None
    
    h_att_by_eff = sorted(h_att_list, key=lambda x: x[3], reverse=True)
    top_eff_h = h_att_by_eff[0] if h_att_by_eff else None

    player_impact = defaultdict(lambda: {"pts": 0, "err": 0})
    for num, st_a in data["home_attack"].items():
        player_impact[num]["pts"] += st_a["#"]
        player_impact[num]["err"] += (st_a["="] + st_a["/"])
    for num, st_r in data["home_reception"].items():
        player_impact[num]["err"] += st_r["="]
    
    worst_perf_player = None
    if player_impact:
        sorted_impact = sorted(player_impact.items(), key=lambda x: (x[1]["pts"] - x[1]["err"]))
        worst_perf_player = sorted_impact[0]

    # Pillole / Bullet grafici nativi
    def draw_bullet(by, color):
        c.setFillColor(color)
        c.circle(px + 13, by + 2.5, 2.3, fill=1, stroke=0)

    c.setFont("Helvetica", 6.8)
    if top_vol_h:
        draw_bullet(sub_y, colors.HexColor("#D35400"))
        p_name = data["home_players"].get(top_vol_h[0], {}).get("name", "")[:9]
        c.setFillColor(colors.black)
        c.drawString(px + 19, sub_y, f"Più servito: #{top_vol_h[0]} {p_name} ({top_vol_h[1]} pal)")
        sub_y -= 9.5
    
    if top_eff_h:
        draw_bullet(sub_y, colors.HexColor("#27AE60"))
        p_name = data["home_players"].get(top_eff_h[0], {}).get("name", "")[:9]
        c.setFillColor(colors.black)
        c.drawString(px + 19, sub_y, f"Più efficace: #{top_eff_h[0]} {p_name} ({top_eff_h[3]:.0f}% Eff)")
        sub_y -= 9.5

    if worst_perf_player and (worst_perf_player[1]["pts"] - worst_perf_player[1]["err"]) < 0:
        draw_bullet(sub_y, colors.HexColor("#C0392B"))
        wp_num = worst_perf_player[0]
        wp_name = data["home_players"].get(wp_num, {}).get("name", "")[:9]
        saldo = worst_perf_player[1]["pts"] - worst_perf_player[1]["err"]
        c.setFillColor(colors.HexColor("#C0392B"))
        c.setFont("Helvetica-Bold", 6.8)
        c.drawString(px + 19, sub_y, f"Momento NO: #{wp_num} {wp_name} (Saldo: {saldo})")
    else:
        draw_bullet(sub_y, colors.HexColor("#7F8C8D"))
        c.setFillColor(colors.HexColor("#546E7A"))
        c.drawString(px + 19, sub_y, "Rendimento squadra: Equilibrato")

    c_y = c_y - card_busnago_h - 4

    # ====================================================
    # 4. FOCUS AVVERSARI (TARGET TATTICI AD ALTO CONTRASTO)
    # ====================================================
    card_opp_h = 104
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.HexColor("#D35400"))
    c.rect(px + 6, c_y - card_opp_h, pw - 12, card_opp_h, fill=1, stroke=1)

    c.setFillColor(colors.HexColor("#D35400"))
    c.rect(px + 6, c_y - 15, pw - 12, 15, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(px + 10, c_y - 11, "TARGET AVVERSARI (DECISIONI TATTICHE)")

    opp_rec_qual = []
    for num, st_r in data["opp_reception"].items():
        if st_r["tot"] >= 5:
            eff_pos = ((st_r["#"] + st_r["+"]) / st_r["tot"]) * 100
            debolezza_pct = ((st_r["="] + st_r["/"] + st_r["-"]) / st_r["tot"]) * 100
            opp_rec_qual.append((num, st_r["tot"], eff_pos, debolezza_pct))

    best_opp_rec = max(opp_rec_qual, key=lambda x: x[2]) if opp_rec_qual else None
    worst_opp_rec = max(opp_rec_qual, key=lambda x: x[3]) if opp_rec_qual else None

    opp_att_list = []
    for num, st_a in data["opp_attack"].items():
        if st_a["tot"] > 0:
            eff = ((st_a["#"] - st_a["="] - st_a["/"]) / st_a["tot"]) * 100
            opp_att_list.append((num, st_a["tot"], st_a["#"], eff))

    opp_att_by_vol = sorted(opp_att_list, key=lambda x: x[1], reverse=True)
    top_vol_opp = opp_att_by_vol[0] if opp_att_by_vol else None

    # Esclusione palleggiatore
    non_setters_att = []
    for item in opp_att_list:
        p_num = item[0]
        p_info = data["opp_players"].get(p_num, {})
        p_role = str(p_info.get("role", "")).strip()
        p_name = p_info.get("name", "").upper()
        is_setter = (p_role == "5") or ("P" in p_name) or ("PAL" in p_name) or ("PALLEGGIATORE" in p_name)
        if not is_setter:
            non_setters_att.append(item)

    non_setters_by_vol = sorted(non_setters_att, key=lambda x: x[1])
    min_vol_opp = non_setters_by_vol[0] if non_setters_by_vol else None

    opp_att_qual = [a for a in opp_att_list if a[1] >= 3]
    top_eff_opp = max(opp_att_qual, key=lambda x: x[3]) if opp_att_qual else (opp_att_list[0] if opp_att_list else None)

    sub_opp_y = c_y - 25
    c.setFont("Helvetica-Bold", 6.8)
    c.setFillColor(colors.HexColor("#263238"))
    c.drawString(px + 10, sub_opp_y, "RICEZIONE AVVERSARIA (min. 5 ric):")

    sub_opp_y -= 10
    if worst_opp_rec:
        p_name = data["opp_players"].get(worst_opp_rec[0], {}).get("name", "")[:9]
        # Badge Bersaglio
        c.setFillColor(colors.HexColor("#FDEDEC"))
        c.rect(px + 10, sub_opp_y - 2, pw - 20, 9.5, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#C0392B"))
        c.circle(px + 15, sub_opp_y + 2.5, 2.5, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 6.6)
        c.drawString(px + 21, sub_opp_y, f"BERSAGLIO SERVIZIO: #{worst_opp_rec[0]} {p_name} ({worst_opp_rec[3]:.0f}% neg/err)")
    else:
        c.setFont("Helvetica", 6.6)
        c.setFillColor(colors.HexColor("#546E7A"))
        c.drawString(px + 10, sub_opp_y, "• Bersaglio servizio: Dati ric. insufficienti (<5)")

    sub_opp_y -= 10
    if best_opp_rec:
        p_name = data["opp_players"].get(best_opp_rec[0], {}).get("name", "")[:9]
        c.setFillColor(colors.HexColor("#E8F8F5"))
        c.rect(px + 10, sub_opp_y - 2, pw - 20, 9.5, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#196F3D"))
        c.circle(px + 15, sub_opp_y + 2.5, 2.5, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 6.6)
        c.drawString(px + 21, sub_opp_y, f"EVITA BATTUTA: #{best_opp_rec[0]} {p_name} ({best_opp_rec[2]:.0f}% #+)")
    else:
        c.setFont("Helvetica", 6.6)
        c.setFillColor(colors.HexColor("#546E7A"))
        c.drawString(px + 10, sub_opp_y, "• Evita battuta: Dati ric. insufficienti (<5)")

    sub_opp_y -= 11
    c.setStrokeColor(colors.HexColor("#ECEFF1"))
    c.line(px + 10, sub_opp_y + 2, px + pw - 12, sub_opp_y + 2)

    sub_opp_y -= 7
    c.setFont("Helvetica-Bold", 6.8)
    c.setFillColor(colors.HexColor("#263238"))
    c.drawString(px + 10, sub_opp_y, "ATTACCO AVVERSARIO:")

    sub_opp_y -= 10
    c.setFont("Helvetica", 6.8)
    if top_eff_opp:
        c.setFillColor(colors.HexColor("#27AE60"))
        c.circle(px + 13, sub_opp_y + 2.5, 2.3, fill=1, stroke=0)
        p_name = data["opp_players"].get(top_eff_opp[0], {}).get("name", "")[:9]
        c.setFillColor(colors.black)
        c.drawString(px + 19, sub_opp_y, f"Più efficace: #{top_eff_opp[0]} {p_name} ({top_eff_opp[3]:.0f}% Eff)")
    
    sub_opp_y -= 10
    if top_vol_opp:
        c.setFillColor(colors.HexColor("#D35400"))
        c.circle(px + 13, sub_opp_y + 2.5, 2.3, fill=1, stroke=0)
        p_name = data["opp_players"].get(top_vol_opp[0], {}).get("name", "")[:9]
        c.setFillColor(colors.black)
        c.drawString(px + 19, sub_opp_y, f"Più servito: #{top_vol_opp[0]} {p_name} ({top_vol_opp[1]} pal)")
        
    sub_opp_y -= 10
    if min_vol_opp and min_vol_opp[0] != (top_vol_opp[0] if top_vol_opp else None):
        c.setFillColor(colors.HexColor("#2980B9"))
        c.circle(px + 13, sub_opp_y + 2.5, 2.3, fill=1, stroke=0)
        p_name = data["opp_players"].get(min_vol_opp[0], {}).get("name", "")[:9]
        c.setFillColor(colors.black)
        c.drawString(px + 19, sub_opp_y, f"Meno servito (no P): #{min_vol_opp[0]} {p_name} ({min_vol_opp[1]} pal)")

    c.showPage()

    # ----------------------------------------------------
    # PAGINA 2: FOCUS PREFERENZE SINGOLI ATTACCANTI
    # ----------------------------------------------------
    c.setFillColor(colors.HexColor("#1A252F"))
    c.rect(0, height - 34, width, 34, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20, height - 20, f"FOCUS PREFERENZE ATTACCO INDIVIDUALI: {data['teams']['opp']}")
    c.setFont("Helvetica", 8)
    c.drawString(20, height - 30, f"Campi a Sfondo Bianco  |  Traiettorie: Verde Punto, Rosso Errore, Giallo in Gioco  |  {set_label}")

    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(colors.HexColor("#27AE60"))
    c.drawString(width - 240, height - 20, "• Punto (#)")
    c.setFillColor(colors.HexColor("#E74C3C"))
    c.drawString(width - 180, height - 20, "• Errore/Murato (=, /)")
    c.setFillColor(colors.HexColor("#F39C12"))
    c.drawString(width - 90, height - 20, "• In Gioco (+, -)")

    f_coords = [
        (20, height - 262), (285, height - 262), (550, height - 262),
        (20, height - 500), (285, height - 500), (550, height - 500)
    ]
    fb_w, fb_h = 250, 228
    fc_w, fc_h = 95, 190

    top_attackers = opp_att_by_vol[:6]

    for idx, att_info in enumerate(top_attackers):
        p_num = att_info[0]
        p_tot, p_pts, p_eff = att_info[1], att_info[2], att_info[3]
        p_pct = (p_pts / p_tot * 100) if p_tot > 0 else 0
        p_name = data["opp_players"].get(p_num, {}).get("name", f"Giocatore #{p_num}")
        
        fx, fy = f_coords[idx]
        
        c.setStrokeColor(colors.HexColor("#BDC3C7"))
        c.setLineWidth(0.8)
        c.rect(fx, fy, fb_w, fb_h)
        
        c.setFillColor(colors.HexColor("#2C3E50"))
        c.rect(fx, fy + fb_h - 18, fb_w, 18, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(fx + 6, fy + fb_h - 13, f"#{p_num} {p_name.upper()} ({p_tot} Palloni)")
        
        p_attacks = data["opp_attack"][p_num]["attacks"]
        draw_full_pitch(c, fx + 8, fy + 10, fc_w, fc_h, p_attacks)
        
        rx = fx + fc_w + 16
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(rx, fy + fb_h - 30, "STATISTICHE:")
        c.setFont("Helvetica", 7)
        c.drawString(rx, fy + fb_h - 42, f"• Vincenti: {p_pts} ({p_pct:.0f}%)")
        c.drawString(rx, fy + fb_h - 54, f"• Efficienza: {p_eff:.0f}%")
        
        z_start_cnt = defaultdict(int)
        z_end_cnt = defaultdict(int)
        for _, sz, ez, _ in p_attacks:
            if sz: z_start_cnt[sz] += 1
            if ez: z_end_cnt[ez] += 1
            
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(rx, fy + fb_h - 72, "PREFERENZE:")
        c.setFont("Helvetica", 7)
        if z_start_cnt:
            top_start = max(z_start_cnt, key=z_start_cnt.get)
            if top_start in ["2", "3", "4"]:
                label_s = f"Posto {top_start}"
            else:
                label_s = f"Zona {top_start} (2° Linea)"
            c.drawString(rx, fy + fb_h - 84, f"• Parte da: {label_s}")
            
        if z_end_cnt:
            top_dest = max(z_end_cnt, key=z_end_cnt.get)
            c.drawString(rx, fy + fb_h - 96, f"• Chiude in: Zona {top_dest}")
            
        c.setFont("Helvetica-Bold", 7)
        c.setFillColor(colors.HexColor("#C0392B"))
        
        if z_start_cnt.get("4", 0) >= z_start_cnt.get("2", 0):
            par = z_end_cnt.get("1", 0) + z_end_cnt.get("7", 0)
            diag = z_end_cnt.get("5", 0) + z_end_cnt.get("9", 0)
        else:
            par = z_end_cnt.get("5", 0) + z_end_cnt.get("9", 0)
            diag = z_end_cnt.get("1", 0) + z_end_cnt.get("7", 0)
            
        if diag > par: trend = "Preferisce Diagonale"
        elif par > diag: trend = "Preferisce Parallela"
        else: trend = "Distribuzione Mista"
        c.drawString(rx, fy + fb_h - 114, f"• {trend}")

    c.showPage()
    c.save()
    buf.seek(0)
    return buf

# ==========================================================
# INTERFACCIA STREAMLIT
# ==========================================================
def main():
    st.set_page_config(page_title="Volley Scout Dashboard", layout="wide")
    st.title("🏐 Scheda Tattica Grafica Live Click&Scout")
    st.write("Dossier Completo: Pre-Gara Memorizzato + Analisi Live con Target Ricezione e Attacco.")

    if "saved_pre_pdf_bytes" not in st.session_state:
        st.session_state["saved_pre_pdf_bytes"] = None
    if "saved_pre_pdf_name" not in st.session_state:
        st.session_state["saved_pre_pdf_name"] = ""

    col_pre, col_scout = st.columns(2)

    with col_pre:
        st.subheader("1. Studio Pre-Gara (Carica 1 volta sola)")
        if st.session_state["saved_pre_pdf_bytes"] is not None:
            st.success(f"✅ Pre-gara memorizzato in sessione: **{st.session_state['saved_pre_pdf_name']}**")
            if st.button("🗑️ Rimuovi / Cambia Pre-Gara"):
                st.session_state["saved_pre_pdf_bytes"] = None
                st.session_state["saved_pre_pdf_name"] = ""
                st.rerun()
        else:
            uploaded_pre = st.file_uploader(
                "Carica qui il PDF del tuo studio pre-gara:",
                type=["pdf"]
            )
            if uploaded_pre:
                st.session_state["saved_pre_pdf_bytes"] = uploaded_pre.getvalue()
                st.session_state["saved_pre_pdf_name"] = uploaded_pre.name
                st.success(f"✅ Memorizzato per tutti i set: **{uploaded_pre.name}**")
                st.rerun()

    with col_scout:
        st.subheader("2. Dati Scout (Aggiorna fine set)")
        metodo = st.radio(
            "Modalità inserimento scout:",
            ["📁 Carica File Scout", "📋 Incolla Testo Scout"],
            horizontal=True
        )

        text = None
        if metodo == "📁 Carica File Scout":
            uploaded_file = st.file_uploader(
                "Seleziona il file scout aggiornato (estensione .dvw o .txt):",
                type=None
            )
            if uploaded_file:
                text = uploaded_file.getvalue().decode("utf-8", errors="ignore")
        else:
            raw_text = st.text_area(
                "Incolla qui il contenuto aggiornato di Click&Scout:",
                height=160,
                placeholder="Incolla le righe di Click&Scout..."
            )
            if raw_text.strip():
                text = raw_text

    if text:
        col_set, _ = st.columns([3, 3])
        with col_set:
            set_choice = st.selectbox(
                "Seleziona il Set da analizzare:",
                ["Gara Completa", "Set 1", "Set 2", "Set 3", "Set 4", "Set 5"]
            )
            
        t_set = None
        if set_choice != "Gara Completa":
            match_s = re.search(r"\d+", set_choice)
            if match_s:
                t_set = int(match_s.group(0))

        scout_data = parse_dvw(text, target_set=t_set)
        
        if not scout_data:
            st.error("Formato scout non valido o privo di dati.")
            return
            
        st.success(f"Dati elaborati: **{scout_data['teams']['opp']}** vs **{scout_data['teams']['home']}**")
        
        live_pdf_buf = generate_pdf(scout_data, set_label=set_choice)

        if st.session_state["saved_pre_pdf_bytes"] is not None:
            merger = PdfWriter()
            r_pre = PdfReader(io.BytesIO(st.session_state["saved_pre_pdf_bytes"]))
            for page in r_pre.pages:
                merger.add_page(page)
            r_live = PdfReader(live_pdf_buf)
            for page in r_live.pages:
                merger.add_page(page)
            out_buf = io.BytesIO()
            merger.write(out_buf)
            out_buf.seek(0)
            final_data = out_buf
            btn_label = f"📄 Scarica Dossier Completo (Pre-Gara + Analisi {set_choice})"
            file_name_out = f"Dossier_Completo_{scout_data['teams']['opp']}_{set_choice.replace(' ', '_')}.pdf"
        else:
            final_data = live_pdf_buf
            btn_label = f"📄 Scarica Scheda Tattica Grafica ({set_choice})"
            file_name_out = f"Scheda_Live_{scout_data['teams']['opp']}_{set_choice.replace(' ', '_')}.pdf"

        st.download_button(
            label=btn_label,
            data=final_data,
            file_name=file_name_out,
            mime="application/pdf"
        )

if __name__ == "__main__":
    main()
