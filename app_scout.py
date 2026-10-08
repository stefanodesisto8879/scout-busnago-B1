import io
import math
import re
from collections import defaultdict
import streamlit as st
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.pdfgen import canvas

# ==========================================================
# COORDINATE CAMPO CON PROSPETTIVA DALLA NOSTRA PANCHINA:
# Z4 AVVERSARIO A DESTRA | Z2 AVVERSARIO A SINISTRA
# ==========================================================
# Origine attacco (Metà superiore): Rete a y=0.50, Fondo a y=1.00
ATTACK_ORIGIN_FULL = {
    # 1° Linea a filo rete
    "2": (0.17, 0.53),  # Z2 Avversario (a sinistra per noi)
    "3": (0.50, 0.53),  # Z3 Avversario (centro)
    "4": (0.83, 0.53),  # Z4 Avversario (a destra per noi)
    # 2° Linea / Pipe
    "8": (0.50, 0.77),  # Pipe (Z8 avversaria)
    "6": (0.50, 0.77),
    "1": (0.17, 0.77),  # Z1 avversaria (per noi a sinistra)
    "5": (0.83, 0.77),  # Z5 avversaria (per noi a destra)
}

# Arrivo palla nel nostro campo difensivo (Metà inferiore): Rete a y=0.50, Fondo a y=0.00
DEFENSE_TARGET_FULL = {
    # Prima linea difesa (vicino alla rete)
    "2": (0.17, 0.44), "3": (0.50, 0.44), "4": (0.83, 0.44),
    # Fascia centrale (tra 3m e fondo campo)
    "7": (0.17, 0.28), "8": (0.50, 0.28), "9": (0.83, 0.28),
    # Fondo campo difesa
    "5": (0.17, 0.11), "6": (0.50, 0.11), "1": (0.83, 0.11),
}

# Arrivo battute nel nostro campo ricezione
SERVE_TARGET = {
    "2": (0.17, 0.70), "3": (0.50, 0.70), "4": (0.83, 0.70),
    "7": (0.17, 0.45), "8": (0.50, 0.45), "9": (0.83, 0.45),
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
                if eval_char == "=": home_errors["serve"] += 1
                if eval_char in home_srv[player]: home_srv[player][eval_char] += 1

            elif skill == "R":
                home_rec[player]["tot"] += 1
                if eval_char in home_rec[player]: home_rec[player][eval_char] += 1

            elif skill == "A":
                home_att[player]["tot"] += 1
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
            if skill == "R":
                opp_rec[player]["tot"] += 1
                if eval_char in opp_rec[player]: opp_rec[player][eval_char] += 1
                    
            elif skill == "A":
                opp_att[player]["tot"] += 1
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
                        if end_z in ["2", "1", "9"]:
                            rotations[p_rot]["bases"]["K7"] += 1
                        elif end_z in ["4", "5", "7"]:
                            rotations[p_rot]["bases"]["K1"] += 1
                        else:
                            rotations[p_rot]["bases"]["KC"] += 1

            elif skill == "S":
                if end_z:
                    rotations[p_rot]["serves_data"].append((player, start_z, end_z, eval_char))

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
        "phase_stats": phase_stats
    }

# ==========================================================
# DISEGNO TRAIETTORIE
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
# CAMPO CON 9 SOTTO-ZONE CLICK&SCOUT TRATTEGGIATE
# ==========================================================
def draw_full_pitch(c, x, y, w, h, attacks_list, p_dist=None, total_att=None):
    # Sfondo campo
    c.setFillColor(colors.HexColor("#FEF9E7"))
    c.setStrokeColor(colors.black)
    c.setLineWidth(1.0)
    c.rect(x, y, w, h, fill=1, stroke=1)
    
    net_y = y + h * 0.50
    half_h = h * 0.50
    w_third = w / 3.0
    h_third = half_h / 3.0

    # RETE CENTRALE SPESSA
    c.setStrokeColor(colors.HexColor("#922B21"))
    c.setLineWidth(2.8)
    c.line(x, net_y, x + w, net_y)

    # LINEE TRATTEGGIATE DELLE 9 SOTTOZONE CLICK&SCOUT
    c.setStrokeColor(colors.HexColor("#D5D8DC"))
    c.setLineWidth(0.6)
    c.setDash(2, 2)

    # 1. Corridoi verticali (dividono in 3 corsie: sinistra, centro, destra)
    c.line(x + w_third, y, x + w_third, y + h)
    c.line(x + 2 * w_third, y, x + 2 * w_third, y + h)

    # 2. Linee orizzontali campo difesa (sotto)
    c.line(x, net_y - h_third, x + w, net_y - h_third)       # Separa prima linea (3m) da intermedia
    c.line(x, net_y - 2 * h_third, x + w, net_y - 2 * h_third) # Separa intermedia da fondo campo

    # 3. Linee orizzontali campo attacco (sopra)
    c.line(x, net_y + h_third, x + w, net_y + h_third)       # Separa prima linea (3m) da intermedia
    c.line(x, net_y + 2 * h_third, x + w, net_y + 2 * h_third) # Separa intermedia da fondo campo
    
    # Resetta tratteggio
    c.setDash()

    # LINEE DEI 3 METRI UFFICIALI (Leggermente più marcate)
    c.setStrokeColor(colors.HexColor("#A6ACAF"))
    c.setLineWidth(0.8)
    c.line(x, net_y + h_third, x + w, net_y + h_third)
    c.line(x, net_y - h_third, x + w, net_y - h_third)

    # NUMERI SOTTOZONE IN FILIGRANA LEGGERA (Discreti in grigio)
    c.setFont("Helvetica-Bold", 6)
    c.setFillColor(colors.HexColor("#BDC3C7"))

    # Zone Difesa Nostra (Metà inferiore)
    # Sotto rete: Z2 (sx), Z3 (centro), Z4 (dx)
    c.drawCentredString(x + w_third * 0.5, net_y - h_third * 0.5 - 2, "2")
    c.drawCentredString(x + w_third * 1.5, net_y - h_third * 0.5 - 2, "3")
    c.drawCentredString(x + w_third * 2.5, net_y - h_third * 0.5 - 2, "4")
    # Intermedia: Z7 (sx), Z8 (centro), Z9 (dx)
    c.drawCentredString(x + w_third * 0.5, net_y - h_third * 1.5 - 2, "7")
    c.drawCentredString(x + w_third * 1.5, net_y - h_third * 1.5 - 2, "8")
    c.drawCentredString(x + w_third * 2.5, net_y - h_third * 1.5 - 2, "9")
    # Fondo campo: Z5 (sx), Z6 (centro), Z1 (dx)
    c.drawCentredString(x + w_third * 0.5, net_y - h_third * 2.5 - 2, "5")
    c.drawCentredString(x + w_third * 1.5, net_y - h_third * 2.5 - 2, "6")
    c.drawCentredString(x + w_third * 2.5, net_y - h_third * 2.5 - 2, "1")

    # Zone Attacco Avversario (Metà superiore)
    # A rete: Z2 (sx), Z3 (centro), Z4 (dx)
    c.drawCentredString(x + w_third * 0.5, net_y + h_third * 0.5 - 2, "2")
    c.drawCentredString(x + w_third * 1.5, net_y + h_third * 0.5 - 2, "3")
    c.drawCentredString(x + w_third * 2.5, net_y + h_third * 0.5 - 2, "4")
    # Pipe: Z8
    c.drawCentredString(x + w_third * 1.5, net_y + h_third * 1.5 - 2, "8")

    # Box percentuali palleggiatore a rete
    if p_dist and total_att and total_att > 0:
        p4 = p_dist.get("4", 0)
        p3 = p_dist.get("3", 0)
        p2 = p_dist.get("2", 0)
        
        c.setFillColor(colors.HexColor("#2C3E50"))
        c.rect(x + 1, net_y + 9, 28, 9, fill=1, stroke=0)
        c.rect(x + w/2 - 14, net_y + 9, 28, 9, fill=1, stroke=0)
        c.rect(x + w - 29, net_y + 9, 28, 9, fill=1, stroke=0)
        
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 6)
        c.drawString(x + 3, net_y + 11, f"2:{p2*100//total_att}%")
        c.drawString(x + w/2 - 12, net_y + 11, f"3:{p3*100//total_att}%")
        c.drawString(x + w - 27, net_y + 11, f"4:{p4*100//total_att}%")

    # Traiettorie attacchi reali
    for att in attacks_list:
        _, sz, ez, ev = att
        if sz in ATTACK_ORIGIN_FULL and ez in DEFENSE_TARGET_FULL:
            x1 = x + ATTACK_ORIGIN_FULL[sz][0] * w
            y1 = y + ATTACK_ORIGIN_FULL[sz][1] * h
            x2 = x + DEFENSE_TARGET_FULL[ez][0] * w
            y2 = y + DEFENSE_TARGET_FULL[ez][1] * h
            
            if ev == "#":
                col = colors.HexColor("#229954")
                lw = 1.6
            elif ev in ["=", "/"]:
                col = colors.HexColor("#C0392B")
                lw = 1.6
            else:
                col = colors.HexColor("#2980B9")
                lw = 1.0
            draw_trajectory(c, x1, y1, x2, y2, col, line_w=lw)

# ==========================================================
# BOX BATTITORE CON LE 9 SOTTOZONE TRATTEGGIATE
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
    c.setFillColor(colors.HexColor("#F2F4F4"))
    c.setStrokeColor(colors.HexColor("#7F8C8D"))
    c.setLineWidth(0.8)
    c.rect(x, y, w, court_h, fill=1, stroke=1)
    
    # Rete
    c.setStrokeColor(colors.HexColor("#922B21"))
    c.setLineWidth(2.0)
    c.line(x, y + court_h, x + w, y + court_h)

    # Griglia 3x3 sottozone tratteggiata
    c.setStrokeColor(colors.HexColor("#BDC3C7"))
    c.setLineWidth(0.5)
    c.setDash(1.5, 1.5)
    w_th = w / 3.0
    h_th = court_h / 3.0
    c.line(x + w_th, y, x + w_th, y + court_h)
    c.line(x + 2 * w_th, y, x + 2 * w_th, y + court_h)
    c.line(x, y + h_th, x + w, y + h_th)
    c.line(x, y + 2 * h_th, x + w, y + 2 * h_th)
    c.setDash()

    # Numeri in filigrana
    c.setFont("Helvetica", 5)
    c.setFillColor(colors.HexColor("#BDC3C7"))
    c.drawCentredString(x + w_th * 0.5, y + h_th * 2.5 - 1.5, "2")
    c.drawCentredString(x + w_th * 1.5, y + h_th * 2.5 - 1.5, "3")
    c.drawCentredString(x + w_th * 2.5, y + h_th * 2.5 - 1.5, "4")
    c.drawCentredString(x + w_th * 0.5, y + h_th * 1.5 - 1.5, "7")
    c.drawCentredString(x + w_th * 1.5, y + h_th * 1.5 - 1.5, "8")
    c.drawCentredString(x + w_th * 2.5, y + h_th * 1.5 - 1.5, "9")
    c.drawCentredString(x + w_th * 0.5, y + h_th * 0.5 - 1.5, "5")
    c.drawCentredString(x + w_th * 1.5, y + h_th * 0.5 - 1.5, "6")
    c.drawCentredString(x + w_th * 2.5, y + h_th * 0.5 - 1.5, "1")

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
# GENERATORE PDF (PAGINA 1: SQUADRE | PAGINA 2: INDIVIDUALI)
# ==========================================================
def generate_pdf(data, set_label="Gara"):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4))
    width, height = landscape(A4)
    
    # ----------------------------------------------------
    # PAGINA 1: SQUADRA PER ROTAZIONE (P1-P6)
    # ----------------------------------------------------
    c.setFillColor(colors.HexColor("#1A252F"))
    c.rect(0, height - 34, width, 34, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20, height - 20, f"STUDIO TATTICO LIVE: {data['teams']['opp']} vs {data['teams']['home']}")
    c.setFont("Helvetica", 8)
    c.drawString(20, height - 30, f"Analisi: {set_label}  |  Griglia Sottozone Click&Scout 1-9  |  CP vs BP  |  Errori Diretti")

    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(colors.HexColor("#229954"))
    c.drawString(width - 240, height - 20, "●→ Punto (#)")
    c.setFillColor(colors.HexColor("#C0392B"))
    c.drawString(width - 175, height - 20, "●→ Errore/Murato (=, /)")
    c.setFillColor(colors.HexColor("#2980B9"))
    c.drawString(width - 85, height - 20, "●→ In Gioco (+, -)")

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
    # PANNELLO DESTRO: METRICHE SQUADRA E TARGET
    # ----------------------------------------------------
    px = 626
    py = height - 500
    pw = width - px - 15
    ph = 466
    
    c.setStrokeColor(colors.HexColor("#2C3E50"))
    c.rect(px, py, pw, ph)
    c.setFillColor(colors.HexColor("#2C3E50"))
    c.rect(px, py + ph - 18, pw, 18, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(px + 8, py + ph - 13, "METRICHE CHIAVE & RENDIMENTO")

    curr_y = py + ph - 28

    # 1. ERRORI DIRETTI NOSTRI
    err_att = data["home_errors"]["attack"]
    err_srv = data["home_errors"]["serve"]
    err_tot = err_att + err_srv
    
    c.setFillColor(colors.HexColor("#922B21"))
    c.setFont("Helvetica-Bold", 8)
    c.drawString(px + 8, curr_y, f"ERRORI DIRETTI BUSNAGO: {err_tot} TOT")
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.black)
    c.drawString(px + 8, curr_y - 11, f"• In Battuta: {err_srv} err  |  In Attacco: {err_att} err (out/murati)")
    c.line(px + 8, curr_y - 15, px + pw - 8, curr_y - 15)
    
    curr_y -= 26

    # 2. CONFRONTO CP vs BP
    c.setFillColor(colors.HexColor("#1A252F"))
    c.setFont("Helvetica-Bold", 7.8)
    c.drawString(px + 8, curr_y, "CONFRONTO ATTACCO (CP vs BP):")
    
    ps = data["phase_stats"]
    h_cp_pct = (ps["home"]["cp_kill"] / ps["home"]["cp_tot"] * 100) if ps["home"]["cp_tot"] > 0 else 0
    o_cp_pct = (ps["opp"]["cp_kill"] / ps["opp"]["cp_tot"] * 100) if ps["opp"]["cp_tot"] > 0 else 0
    h_bp_pct = (ps["home"]["bp_kill"] / ps["home"]["bp_tot"] * 100) if ps["home"]["bp_tot"] > 0 else 0
    o_bp_pct = (ps["opp"]["bp_kill"] / ps["opp"]["bp_tot"] * 100) if ps["opp"]["bp_tot"] > 0 else 0

    c.setFont("Helvetica", 7)
    c.drawString(px + 8, curr_y - 12, f"• Cambio Palla:  Busnago {h_cp_pct:.0f}%  vs  Avv {o_cp_pct:.0f}%")
    c.drawString(px + 8, curr_y - 23, f"• Break Point:   Busnago {h_bp_pct:.0f}%  vs  Avv {o_bp_pct:.0f}%")
    c.line(px + 8, curr_y - 28, px + pw - 8, curr_y - 28)
    
    curr_y -= 40

    # 3. STATO NOSTRA SQUADRA
    c.setFillColor(colors.HexColor("#2C3E50"))
    c.setFont("Helvetica-Bold", 7.8)
    c.drawString(px + 8, curr_y, "FOCUS NOSTRA SQUADRA (BUSNAGO):")
    
    h_rec_list = []
    for num, st_r in data["home_reception"].items():
        if st_r["tot"] > 0:
            pos = (st_r["#"] + st_r["+"]) / st_r["tot"] * 100
            h_rec_list.append((num, st_r["tot"], pos, st_r["="]))
    h_rec_list.sort(key=lambda x: (x[2], -x[3]))
    worst_rec = h_rec_list[0] if h_rec_list else None
    
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

    c.setFont("Helvetica", 7)
    c.setFillColor(colors.black)
    
    if worst_rec:
        p_name = data["home_players"].get(worst_rec[0], {}).get("name", "")[:9]
        c.drawString(px + 8, curr_y - 12, f"• Ric. più in affanno: #{worst_rec[0]} {p_name} ({worst_rec[2]:.0f}% Pos, {worst_rec[3]} err)")
    else:
        c.drawString(px + 8, curr_y - 12, "• Ric. più in affanno: Nessun errore")

    if top_vol_h:
        p_name = data["home_players"].get(top_vol_h[0], {}).get("name", "")[:9]
        c.drawString(px + 8, curr_y - 23, f"• Attaccante più servito: #{top_vol_h[0]} {p_name} ({top_vol_h[1]} pal)")
    if top_eff_h:
        p_name = data["home_players"].get(top_eff_h[0], {}).get("name", "")[:9]
        c.drawString(px + 8, curr_y - 34, f"• Attaccante più efficace: #{top_eff_h[0]} {p_name} ({top_eff_h[3]:.0f}% Eff)")

    if worst_perf_player and (worst_perf_player[1]["pts"] - worst_perf_player[1]["err"]) < 0:
        wp_num = worst_perf_player[0]
        wp_name = data["home_players"].get(wp_num, {}).get("name", "")[:9]
        saldo = worst_perf_player[1]["pts"] - worst_perf_player[1]["err"]
        c.setFillColor(colors.HexColor("#C0392B"))
        c.drawString(px + 8, curr_y - 45, f"⚠️ Giocatore momento no: #{wp_num} {wp_name} (Saldo: {saldo})")
    else:
        c.drawString(px + 8, curr_y - 45, "• Rendimento squadra: Equilibrato")

    c.line(px + 8, curr_y - 50, px + pw - 8, curr_y - 50)
    curr_y -= 62

    # 4. TARGET AVVERSARI
    c.setFillColor(colors.HexColor("#1A252F"))
    c.setFont("Helvetica-Bold", 7.8)
    c.drawString(px + 8, curr_y, "TARGET TATTICI SUGLI AVVERSARI:")
    
    opp_rec_list = []
    for num, st_r in data["opp_reception"].items():
        if st_r["tot"] > 0:
            pos = (st_r["#"] + st_r["+"]) / st_r["tot"] * 100
            opp_rec_list.append((num, st_r["tot"], pos, st_r["="]))
    opp_rec_list.sort(key=lambda x: x[2])
    
    opp_att_list = []
    for num, st_a in data["opp_attack"].items():
        if st_a["tot"] > 0:
            eff = ((st_a["#"] - st_a["="] - st_a["/"]) / st_a["tot"]) * 100
            opp_att_list.append((num, st_a["tot"], st_a["#"], eff))
    opp_att_list.sort(key=lambda x: x[1], reverse=True)

    c.setFont("Helvetica", 7)
    c.setFillColor(colors.black)
    if opp_rec_list:
        p_name = data["opp_players"].get(opp_rec_list[0][0], {}).get("name", "")[:9]
        c.drawString(px + 8, curr_y - 12, f"🎯 Batti su: #{opp_rec_list[0][0]} {p_name} ({opp_rec_list[0][2]:.0f}% Pos)")
        p_best = data["opp_players"].get(opp_rec_list[-1][0], {}).get("name", "")[:9]
        c.drawString(px + 8, curr_y - 23, f"🛡️ Evita: #{opp_rec_list[-1][0]} {p_best} ({opp_rec_list[-1][2]:.0f}% Pos)")
        
    if opp_att_list:
        p_name = data["opp_players"].get(opp_att_list[0][0], {}).get("name", "")[:9]
        c.drawString(px + 8, curr_y - 34, f"🔥 Loro palla chiave: #{opp_att_list[0][0]} ({opp_att_list[0][1]} att)")
        top_eff_opp = max(opp_att_list, key=lambda x: x[3])
        c.drawString(px + 8, curr_y - 45, f"⚡ Più pericoloso: #{top_eff_opp[0]} ({top_eff_opp[3]:.0f}% Eff)")

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
    c.drawString(20, height - 30, f"Campo 18x9m con Sottozone 1-9  |  Posto 4 a Destra, Posto 2 a Sinistra  |  {set_label}")

    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(colors.HexColor("#229954"))
    c.drawString(width - 240, height - 20, "●→ Punto (#)")
    c.setFillColor(colors.HexColor("#C0392B"))
    c.drawString(width - 175, height - 20, "●→ Errore/Murato (=, /)")
    c.setFillColor(colors.HexColor("#2980B9"))
    c.drawString(width - 85, height - 20, "●→ In Gioco (+, -)")

    f_coords = [
        (20, height - 262), (285, height - 262), (550, height - 262),
        (20, height - 500), (285, height - 500), (550, height - 500)
    ]
    fb_w, fb_h = 250, 228
    fc_w, fc_h = 95, 190

    top_attackers = opp_att_list[:6]

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
            if top_start == "4": label_s = "Posto 4 (Destra)"
            elif top_start == "2": label_s = "Posto 2 (Sinistra)"
            elif top_start == "3": label_s = "Posto 3 (Centro)"
            else: label_s = f"Pipe/Z{top_start} (2° Linea)"
            c.drawString(rx, fy + fb_h - 84, f"• Parte da: {label_s}")
            
        if z_end_cnt:
            top_dest = max(z_end_cnt, key=z_end_cnt.get)
            c.drawString(rx, fy + fb_h - 96, f"• Chiude in: Zona {top_dest}")
            
        c.setFont("Helvetica-Bold", 7)
        c.setFillColor(colors.HexColor("#C0392B"))
        
        if z_start_cnt.get("4", 0) >= z_start_cnt.get("2", 0):
            par = z_end_cnt.get("1", 0) + z_end_cnt.get("9", 0)
            diag = z_end_cnt.get("5", 0) + z_end_cnt.get("7", 0)
        else:
            par = z_end_cnt.get("5", 0) + z_end_cnt.get("7", 0)
            diag = z_end_cnt.get("1", 0) + z_end_cnt.get("9", 0)
            
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
    st.write("Dossier Completo con Sottozone Click&Scout 1-9 tratteggiate, CP vs BP, Errori e Focus Individuali.")

    dvw_file = st.file_uploader("Trascina qui il file .dvw di Click&Scout:", type=["dvw"])
    
    if dvw_file:
        text = dvw_file.getvalue().decode("utf-8", errors="ignore")
        
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
            st.error("Formato file scout non valido o privo di dati.")
            return
            
        st.success(f"Dati elaborati: **{scout_data['teams']['opp']}** vs **{scout_data['teams']['home']}**")
        
        pdf_buffer = generate_pdf(scout_data, set_label=set_choice)
        
        st.download_button(
            label="📄 Scarica Dossier Tattico Completo (PDF)",
            data=pdf_buffer,
            file_name=f"Dossier_Tattico_{scout_data['teams']['opp']}_{set_choice.replace(' ', '_')}.pdf",
            mime="application/pdf"
        )

if __name__ == "__main__":
    main()
