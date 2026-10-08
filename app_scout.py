import io
import math
import re
from collections import defaultdict
import streamlit as st
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.pdfgen import canvas

# ==========================================================
# COORDINATE CAMPO (Rete in alto y=1.0, Fondo campo in basso y=0.0)
# ==========================================================
ATTACK_POS = {
    "4": (0.16, 0.94),   # Posto 4
    "3": (0.50, 0.94),   # Posto 3
    "2": (0.84, 0.94),   # Posto 2 / Fast
    "8": (0.50, 0.72),   # Pipe
    "6": (0.50, 0.72)
}

DEFENSE_POS = {
    "4": (0.20, 0.65), "3": (0.50, 0.65), "2": (0.80, 0.65),
    "7": (0.20, 0.40), "8": (0.50, 0.40), "9": (0.80, 0.40),
    "5": (0.20, 0.12), "6": (0.50, 0.12), "1": (0.80, 0.12),
}

# Coordinate per battuta (da zona di fondo campo verso campo di ricezione)
SERVE_ORIGIN = {
    "1": (0.80, 0.98), "6": (0.50, 0.98), "5": (0.20, 0.98),
    "": (0.50, 0.98)
}

SERVE_TARGET = {
    "4": (0.22, 0.76), "3": (0.50, 0.76), "2": (0.78, 0.76),
    "7": (0.22, 0.48), "8": (0.50, 0.48), "9": (0.78, 0.48),
    "5": (0.22, 0.20), "6": (0.50, 0.20), "1": (0.78, 0.20),
}

# ==========================================================
# PARSER CLICK&SCOUT (.dvw)
# ==========================================================
def parse_dvw(file_text, target_set=None):
    lines = file_text.splitlines()
    teams = {"home": "Busnago", "opp": "Avversario"}
    opp_players = {}
    
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        if line == "[3TEAMS]":
            idx += 1
            if idx < len(lines):
                p_h = lines[idx].split(";")
                if len(p_h) >= 2:
                    teams["home"] = p_h[1]
            idx += 1
            if idx < len(lines):
                p_o = lines[idx].split(";")
                if len(p_o) >= 2:
                    teams["opp"] = p_o[1]
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
    
    reception_stats = defaultdict(lambda: {"#": 0, "+": 0, "!": 0, "-": 0, "/": 0, "=": 0, "tot": 0})
    attack_stats = defaultdict(lambda: {"#": 0, "+": 0, "-": 0, "/": 0, "=": 0, "tot": 0, "attacks": []})
    player_serves = defaultdict(lambda: {"tot": 0, "zones": defaultdict(int), "trajectories": []})
    
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
            if pinfo.get("role") == "5" or "P" in pinfo.get("name", "") or num == "01" or num == "1":
                setter_num = str(int(num))
                break
                
        if setter_num in opp_lineup:
            p_rot = opp_lineup.index(setter_num) + 1
        
        if len(code) < 4:
            continue
            
        player = code[1:3]
        skill = code[3]
        eval_char = code[5] if len(code) > 5 else ""
        
        traj_match = re.search(r"~(\d)(\d)", code)
        start_z = traj_match.group(1) if traj_match else ""
        end_z = traj_match.group(2) if traj_match else ""

        # Ricezione squadra avversaria
        if code.startswith("a") and skill == "R":
            reception_stats[player]["tot"] += 1
            if eval_char in reception_stats[player]:
                reception_stats[player][eval_char] += 1
                
        # Attacco avversario
        elif code.startswith("a") and skill == "A":
            attack_stats[player]["tot"] += 1
            if eval_char in attack_stats[player]:
                attack_stats[player][eval_char] += 1
                
            if start_z:
                att_record = (player, start_z, end_z, eval_char)
                rotations[p_rot]["total_att"] += 1
                rotations[p_rot]["att_dist"][start_z] += 1
                rotations[p_rot]["attacks"].append(att_record)
                attack_stats[player]["attacks"].append(att_record)
                
                p_role = opp_players.get(player, {}).get("role", "")
                if start_z == "3" or p_role == "4" or "C" in opp_players.get(player, {}).get("name", ""):
                    if end_z in ["2", "1"]:
                        rotations[p_rot]["bases"]["K7"] += 1
                    elif end_z in ["4", "5"]:
                        rotations[p_rot]["bases"]["K1"] += 1
                    else:
                        rotations[p_rot]["bases"]["KC"] += 1

        # Battuta avversaria
        elif code.startswith("a") and skill == "S":
            player_serves[player]["tot"] += 1
            if end_z:
                player_serves[player]["zones"][end_z] += 1
                srv_record = (player, start_z, end_z, eval_char)
                player_serves[player]["trajectories"].append(srv_record)
                rotations[p_rot]["serves_data"].append(srv_record)

    return {
        "teams": teams,
        "players": opp_players,
        "rotations": rotations,
        "reception": reception_stats,
        "attack": attack_stats,
        "serves": player_serves
    }

# ==========================================================
# MOTORE GRAFICO VETTORIALE (FRECCE & PUNTINE)
# ==========================================================
def draw_trajectory(c, x1, y1, x2, y2, color, line_w=1.4):
    c.setFillColor(color)
    c.circle(x1, y1, 2.2, fill=1, stroke=0)
    
    c.setStrokeColor(color)
    c.setLineWidth(line_w)
    c.line(x1, y1, x2, y2)
    
    ang = math.atan2(y2 - y1, x2 - x1)
    alen = 5.5
    awid = math.pi / 5.5
    
    p = c.beginPath()
    p.moveTo(x2, y2)
    p.lineTo(x2 - alen * math.cos(ang - awid), y2 - alen * math.sin(ang - awid))
    p.lineTo(x2 - alen * math.cos(ang + awid), y2 - alen * math.sin(ang + awid))
    p.close()
    c.drawPath(p, fill=1, stroke=0)

def draw_attack_pitch(c, x, y, w, h, attacks_list, p_dist=None, total_att=None):
    # Sfondo campo attacco
    c.setFillColor(colors.HexColor("#FEF9E7"))
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.8)
    c.rect(x, y, w, h, fill=1, stroke=1)
    
    # Rete in alto
    c.setStrokeColor(colors.HexColor("#922B21"))
    c.setLineWidth(2.8)
    c.line(x, y + h, x + w, y + h)
    
    # 3 Metri in alto
    c.setStrokeColor(colors.HexColor("#7F8C8D"))
    c.setLineWidth(0.9)
    c.line(x, y + h * 0.70, x + w, y + h * 0.70)
    
    # Box percentuali a rete (se presenti)
    if p_dist and total_att and total_att > 0:
        p4 = p_dist.get("4", 0)
        p3 = p_dist.get("3", 0)
        p2 = p_dist.get("2", 0)
        
        c.setFillColor(colors.HexColor("#2C3E50"))
        c.rect(x + 1, y + h - 11, 28, 9, fill=1, stroke=0)
        c.rect(x + w/2 - 14, y + h - 11, 28, 9, fill=1, stroke=0)
        c.rect(x + w - 29, y + h - 11, 28, 9, fill=1, stroke=0)
        
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 6)
        c.drawString(x + 3, y + h - 9, f"4:{p4*100//total_att}%")
        c.drawString(x + w/2 - 12, y + h - 9, f"3:{p3*100//total_att}%")
        c.drawString(x + w - 27, y + h - 9, f"2:{p2*100//total_att}%")

    # Frecce attacco
    for att in attacks_list:
        _, sz, ez, ev = att
        if sz in ATTACK_POS and ez in DEFENSE_POS:
            x1 = x + ATTACK_POS[sz][0] * w
            y1 = y + ATTACK_POS[sz][1] * h
            x2 = x + DEFENSE_POS[ez][0] * w
            y2 = y + DEFENSE_POS[ez][1] * h
            
            if ev == "#":
                col = colors.HexColor("#229954")  # Punto
                lw = 1.6
            elif ev in ["=", "/"]:
                col = colors.HexColor("#C0392B")  # Errore / Murato
                lw = 1.6
            else:
                col = colors.HexColor("#2980B9")  # Gioco / Difeso
                lw = 1.0
            draw_trajectory(c, x1, y1, x2, y2, col, line_w=lw)

def draw_serve_box_with_player(c, x, y, w, h, serves_list, players_dict):
    c.setFillColor(colors.HexColor("#F2F4F4"))
    c.setStrokeColor(colors.HexColor("#7F8C8D"))
    c.setLineWidth(0.8)
    c.rect(x, y, w, h, fill=1, stroke=1)
    
    # Rete in alto
    c.setStrokeColor(colors.HexColor("#922B21"))
    c.setLineWidth(2.0)
    c.line(x, y + h, x + w, y + h)

    # 3 Metri in alto
    c.setStrokeColor(colors.HexColor("#BDC3C7"))
    c.setLineWidth(0.7)
    c.line(x, y + h * 0.70, x + w, y + h * 0.70)

    # Identificazione battitore principale della fase
    server_counts = defaultdict(int)
    for p, _, _, _ in serves_list:
        server_counts[p] += 1
        
    main_server = max(server_counts, key=server_counts.get) if server_counts else None
    
    c.setFillColor(colors.HexColor("#1A252F"))
    c.setFont("Helvetica-Bold", 6.5)
    if main_server:
        s_name = players_dict.get(main_server, {}).get("name", "")[:10]
        c.drawString(x + 2, y + h + 2, f"BATTITORE: #{main_server} {s_name}")
    else:
        c.drawString(x + 2, y + h + 2, "ARRIVO BATTUTE:")

    # Conteggio zone di arrivo
    counts = defaultdict(int)
    for _, _, ez, _ in serves_list:
        if ez:
            counts[ez] += 1

    max_c = max(counts.values()) if counts else 0

    for zn, cnt in counts.items():
        if zn in SERVE_TARGET and cnt > 0:
            zx = x + SERVE_TARGET[zn][0] * w
            zy = y + SERVE_TARGET[zn][1] * h
            
            if cnt == max_c and max_c > 1:
                c.setFillColor(colors.HexColor("#8E44AD"))  # Zona preferita bersagliata
                rad = 7.5
            else:
                c.setFillColor(colors.HexColor("#34495E"))
                rad = 6.0
                
            c.circle(zx, zy, rad, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 7.5)
            c.drawCentredString(zx, zy - 2.6, str(cnt))

# ==========================================================
# GENERATORE PDF (PAGINA 1: SQUADRA | PAGINA 2: FOCUS ATTACCANTI)
# ==========================================================
def generate_pdf(data, set_label="Gara"):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4))
    width, height = landscape(A4)
    
    # ----------------------------------------------------
    # PAGINA 1: ANALISI DI SQUADRA PER FASE P1-P6
    # ----------------------------------------------------
    c.setFillColor(colors.HexColor("#1A252F"))
    c.rect(0, height - 34, width, 34, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20, height - 20, f"STUDIO TATTICO LIVE: {data['teams']['opp']} vs {data['teams']['home']}")
    c.setFont("Helvetica", 8)
    c.drawString(20, height - 30, f"Analisi: {set_label}  |  Distribuzione Palleggiatore, Traiettorie Reali & Battitori per Fase")

    # Legenda Frecce
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
    cw, ch = 104, 134

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
        
        # 1. Campo Attacchi di Squadra
        cx, cy = bx + 5, by + 8
        draw_attack_pitch(c, cx, cy, cw, ch, rot["attacks"], p_dist=rot["att_dist"], total_att=rot["total_att"])
        
        # 2. Box Battitore e Arrivo Battute
        sx, sy = bx + cw + 10, by + 8
        sw, sh = bw - cw - 15, 68
        draw_serve_box_with_player(c, sx, sy, sw, sh, rot["serves_data"], data["players"])
        
        # 3. Basi Centrale
        dx = bx + cw + 10
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(dx, by + bh - 28, "BASI C1/C2:")
        c.setFont("Helvetica", 7)
        c.drawString(dx, by + bh - 39, f"• K1: {rot['bases'].get('K1', 0)}")
        c.drawString(dx, by + bh - 49, f"• KC: {rot['bases'].get('KC', 0)}")
        c.drawString(dx, by + bh - 59, f"• K7: {rot['bases'].get('K7', 0)}")

    # Pannello Destro Target
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
    c.drawString(px + 8, py + ph - 13, "INDICAZIONI & TARGET GIOCATORI")
    
    # Ricezione
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(px + 8, py + ph - 30, "RICEZIONE AVVERSARIA:")
    
    rec_sorted = []
    for num, st_r in data["reception"].items():
        if st_r["tot"] > 0:
            pos_pct = (st_r["#"] + st_r["+"]) / st_r["tot"] * 100
            prf_pct = st_r["#"] / st_r["tot"] * 100
            rec_sorted.append((num, st_r["tot"], pos_pct, prf_pct, st_r["="]))
    rec_sorted.sort(key=lambda x: x[2])
    
    c.setFont("Helvetica", 6.5)
    c.drawString(px + 8, py + ph - 42, "#   Nome       Tot  Pos%  Prf%  Err")
    c.line(px + 8, py + ph - 45, px + pw - 8, py + ph - 45)
    
    ry = py + ph - 56
    for i, r in enumerate(rec_sorted[:5]):
        pname = data["players"].get(r[0], {}).get("name", "")[:9]
        if i == 0:
            c.setFillColor(colors.HexColor("#C0392B"))
            prefix = "🎯 "
        elif i == len(rec_sorted) - 1:
            c.setFillColor(colors.HexColor("#1E8449"))
            prefix = "🛡️ "
        else:
            c.setFillColor(colors.black)
            prefix = ""
        c.drawString(px + 8, ry, f"{prefix}#{r[0]} {pname:<9} {r[1]:<3} {r[2]:.0f}%   {r[3]:.0f}%   {r[4]}")
        ry -= 11

    # Attacco
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(px + 8, ry - 10, "ATTACCO AVVERSARIO:")
    
    att_sorted = []
    for num, st_a in data["attack"].items():
        if st_a["tot"] > 0:
            eff = ((st_a["#"] - st_a["="] - st_a["/"]) / st_a["tot"]) * 100
            pt_pct = st_a["#"] / st_a["tot"] * 100
            att_sorted.append((num, st_a["tot"], st_a["#"], eff, pt_pct))
    att_sorted.sort(key=lambda x: x[1], reverse=True)
    max_eff_player = max(att_sorted, key=lambda x: x[3])[0] if att_sorted else None
    
    c.setFont("Helvetica", 6.5)
    c.drawString(px + 8, ry - 22, "#   Nome       Tot  Pt   Eff%  Pt%")
    c.line(px + 8, ry - 25, px + pw - 8, ry - 25)
    
    ay = ry - 36
    for i, a in enumerate(att_sorted[:6]):
        pname = data["players"].get(a[0], {}).get("name", "")[:9]
        if i == 0:
            c.setFillColor(colors.HexColor("#D35400"))
            prefix = "🔥 "
        elif a[0] == max_eff_player and a[1] >= 3:
            c.setFillColor(colors.HexColor("#922B21"))
            prefix = "⚡ "
        else:
            c.setFillColor(colors.black)
            prefix = ""
        c.drawString(px + 8, ay, f"{prefix}#{a[0]} {pname:<9} {a[1]:<3} {a[2]:<3} {a[3]:.0f}%  {a[4]:.0f}%")
        ay -= 11

    # Decisioni Tattiche
    c.setFillColor(colors.HexColor("#EAEDED"))
    c.rect(px + 6, py + 10, pw - 12, ay - py + 5, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#1A252F"))
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(px + 10, ay - 6, "DECISIONI TATTICHE:")
    c.setFont("Helvetica", 6.8)
    c.setFillColor(colors.black)
    if rec_sorted:
        c.drawString(px + 10, ay - 18, f"• Battuta su: #{rec_sorted[0][0]} ({rec_sorted[0][2]:.0f}% Pos)")
        c.drawString(px + 10, ay - 28, f"• Evita battuta su: #{rec_sorted[-1][0]} ({rec_sorted[-1][2]:.0f}%)")
    if att_sorted:
        c.drawString(px + 10, ay - 39, f"• Muro/Difesa Focus: #{att_sorted[0][0]} ({att_sorted[0][1]} attacchi)")
        if max_eff_player:
            c.drawString(px + 10, ay - 49, f"• Più Pericoloso: #{max_eff_player} (Alta Eff%)")

    c.showPage()

    # ----------------------------------------------------
    # PAGINA 2: FOCUS PREFERENZE SINGOLI ATTACCANTI (6 GIOCATORI)
    # ----------------------------------------------------
    c.setFillColor(colors.HexColor("#1A252F"))
    c.rect(0, height - 34, width, 34, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20, height - 20, f"FOCUS PREFERENZE ATTACCO INDIVIDUALI: {data['teams']['opp']}")
    c.setFont("Helvetica", 8)
    c.drawString(20, height - 30, f"Mappa direzioni e traiettorie per singolo attaccante  |  {set_label}")

    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(colors.HexColor("#229954"))
    c.drawString(width - 240, height - 20, "●→ Punto (#)")
    c.setFillColor(colors.HexColor("#C0392B"))
    c.drawString(width - 175, height - 20, "●→ Errore/Murato (=, /)")
    c.setFillColor(colors.HexColor("#2980B9"))
    c.drawString(width - 85, height - 20, "●→ In Gioco (+, -)")

    # Coordinate griglia per 6 singoli attaccanti (3 sopra, 3 sotto)
    f_coords = [
        (20, height - 262), (285, height - 262), (550, height - 262),
        (20, height - 500), (285, height - 500), (550, height - 500)
    ]
    fb_w, fb_h = 250, 228
    fc_w, fc_h = 135, 140

    top_attackers = att_sorted[:6]

    for idx, att_info in enumerate(top_attackers):
        p_num = att_info[0]
        p_tot, p_pts, p_eff, p_pct = att_info[1], att_info[2], att_info[3], att_info[4]
        p_name = data["players"].get(p_num, {}).get("name", f"Giocatore #{p_num}")
        p_role = data["players"].get(p_num, {}).get("role", "")
        
        fx, fy = f_coords[idx]
        
        # Bordo box
        c.setStrokeColor(colors.HexColor("#BDC3C7"))
        c.setLineWidth(0.8)
        c.rect(fx, fy, fb_w, fb_h)
        
        # Titolo giocatore
        c.setFillColor(colors.HexColor("#2C3E50"))
        c.rect(fx, fy + fb_h - 18, fb_w, 18, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(fx + 6, fy + fb_h - 13, f"#{p_num} {p_name.upper()} ({p_tot} Palloni)")
        
        # Campetto individuale con le sue traiettorie
        p_attacks = data["attack"][p_num]["attacks"]
        draw_attack_pitch(c, fx + 8, fy + 12, fc_w, fc_h, p_attacks)
        
        # Statistiche e preferenze a lato del campetto
        rx = fx + fc_w + 16
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(rx, fy + fb_h - 30, "STATISTICHE:")
        c.setFont("Helvetica", 7)
        c.drawString(rx, fy + fb_h - 42, f"• Punti Vincenti: {p_pts} ({p_pct:.0f}%)")
        c.drawString(rx, fy + fb_h - 54, f"• Efficienza Netta: {p_eff:.0f}%")
        
        # Analisi zone di partenza
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
            c.drawString(rx, fy + fb_h - 84, f"• Attacca da: Posto {top_start}")
        if z_end_cnt:
            top_dest = max(z_end_cnt, key=z_end_cnt.get)
            c.drawString(rx, fy + fb_h - 96, f"• Chiude in: Zona {top_dest}")
            
        # Analisi tipologia colpo
        c.setFont("Helvetica-Bold", 7)
        c.setFillColor(colors.HexColor("#C0392B"))
        diag_cnt = z_end_cnt.get("5", 0) + z_end_cnt.get("6", 0)
        par_cnt = z_end_cnt.get("1", 0) + z_end_cnt.get("9", 0)
        if diag_cnt > par_cnt:
            trend = "Preferisce Diagonale"
        elif par_cnt > diag_cnt:
            trend = "Preferisce Parallela"
        else:
            trend = "Distribuzione Mista"
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
    st.write("Generazione del Dossier a 2 Pagine: Analisi di Squadra per Rotazione + Focus Preferenze Singoli Attaccanti.")

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
            label="📄 Scarica Dossier Tattico Completo (2 Pagine PDF)",
            data=pdf_buffer,
            file_name=f"Dossier_Tattico_{scout_data['teams']['opp']}_{set_choice.replace(' ', '_')}.pdf",
            mime="application/pdf"
        )

if __name__ == "__main__":
    main()
