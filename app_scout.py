import io
import math
import re
from collections import defaultdict
import streamlit as st
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.pdfgen import canvas

def parse_dvw(file_text, target_set=None):
    lines = file_text.splitlines()
    teams = {"home": "Busnago", "opp": "Avversario"}
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
            "serves": defaultdict(int),
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

        if skill == "R":
            reception_stats[player]["tot"] += 1
            if eval_char in reception_stats[player]:
                reception_stats[player][eval_char] += 1
       if skill == "R":
         reception_stats[player]["tot"] += 1
         if eval_char in reception_stats[player]:
             reception_stats[player][eval_char] += 1
                
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
        elif skill == "S":
            if start_z and end_z:
                rotations[p_rot]["serves"][f"#{player} Z{start_z}»Z{end_z}"] += 1

    return {
        "teams": teams,
        "players": opp_players,
        "rotations": rotations,
        "reception": reception_stats,
        "attack": attack_stats
    }

ATTACK_POS = {
    "4": (0.18, 0.90), "3": (0.50, 0.90), "2": (0.82, 0.90),
    "8": (0.50, 0.60), "6": (0.50, 0.60),
}

DEFENSE_POS = {
    "1": (0.80, 0.15), "6": (0.50, 0.15), "5": (0.20, 0.15),
    "9": (0.80, 0.45), "8": (0.50, 0.45), "7": (0.20, 0.45),
    "2": (0.80, 0.70), "3": (0.50, 0.70), "4": (0.20, 0.70),
}

def draw_arrow(c, x1, y1, x2, y2, color, line_w=1.2):
    c.setStrokeColor(color)
    c.setFillColor(color)
    c.setLineWidth(line_w)
    c.line(x1, y1, x2, y2)
    
    ang = math.atan2(y2 - y1, x2 - x1)
    alen = 5
    awid = math.pi / 6
    
    p = c.beginPath()
    p.moveTo(x2, y2)
    p.lineTo(x2 - alen * math.cos(ang - awid), y2 - alen * math.sin(ang - awid))
    p.lineTo(x2 - alen * math.cos(ang + awid), y2 - alen * math.sin(ang + awid))
    p.close()
    c.drawPath(p, fill=1, stroke=0)

def draw_pitch(c, x, y, w, h, rot_data):
    c.setFillColor(colors.HexColor("#FDF2E9"))
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.rect(x, y, w, h, fill=1, stroke=1)
    
    c.setStrokeColor(colors.HexColor("#A93226"))
    c.setLineWidth(2.5)
    c.line(x, y + h, x + w, y + h)
    
    c.setStrokeColor(colors.HexColor("#BDC3C7"))
    c.setLineWidth(0.8)
    c.line(x, y + h * 0.67, x + w, y + h * 0.67)

    tot = max(1, rot_data["total_att"])
    p4 = rot_data["att_dist"].get("4", 0)
    p3 = rot_data["att_dist"].get("3", 0)
    p2 = rot_data["att_dist"].get("2", 0)
    
    c.setFillColor(colors.HexColor("#2C3E50"))
    c.rect(x + 2, y + h - 13, 30, 11, fill=1, stroke=0)
    c.rect(x + w/2 - 15, y + h - 13, 30, 11, fill=1, stroke=0)
    c.rect(x + w - 32, y + h - 13, 30, 11, fill=1, stroke=0)
    
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawString(x + 4, y + h - 10, f"4:{p4*100//tot}%")
    c.drawString(x + w/2 - 13, y + h - 10, f"3:{p3*100//tot}%")
    c.drawString(x + w - 30, y + h - 10, f"2:{p2*100//tot}%")

    for att in rot_data["attacks"]:
        _, sz, ez, ev = att
        if sz in ATTACK_POS and ez in DEFENSE_POS:
            x1 = x + ATTACK_POS[sz][0] * w
            y1 = y + ATTACK_POS[sz][1] * h
            x2 = x + DEFENSE_POS[ez][0] * w
            y2 = y + DEFENSE_POS[ez][1] * h
            
            if ev == "#":
                col = colors.HexColor("#27AE60")
                lw = 1.5
            elif ev in ["=", "/"]:
                col = colors.HexColor("#E74C3C")
                lw = 1.5
            else:
                col = colors.HexColor("#2980B9")
                lw = 0.9
