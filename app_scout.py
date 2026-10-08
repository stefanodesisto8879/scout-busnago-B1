import io
import re
import math
from collections import defaultdict
import streamlit as st
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.pdfgen import canvas

# Coordinate standard (Rete in alto y=1.0, Fondo campo in basso y=0.0)
ATTACK_ORIGIN = {
    "4": (0.18, 0.88),
    "3": (0.50, 0.88),
    "2": (0.82, 0.88),
    "8": (0.50, 0.55),
    "6": (0.50, 0.55),
}

DEFENSE_TARGET = {
    "1": (0.80, 0.15), "6": (0.50, 0.15), "5": (0.20, 0.15),
    "9": (0.80, 0.45), "8": (0.50, 0.45), "7": (0.20, 0.45),
    "2": (0.80, 0.70), "3": (0.50, 0.70), "4": (0.20, 0.70),
}

def parse_dvw(file_text, target_set=None):
    lines = file_text.splitlines()
    teams = {"home": "Casa", "opp": "Ospiti"}
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

        # Ricezione
        if skill == "R":
            reception_stats[player]["tot"] += 1
            if eval_char in reception_stats[player]:
                reception_stats[player][eval_char] += 1
                
        # Attacco
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

        # Battuta
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

def draw_arrow_head(c, x1, y1, x2, y2, color, width=1.5):
    c.setStrokeColor(color)
    c.setFillColor(color)
    c.setLineWidth(width)
    c.line(x1, y1, x2, y2)
    
    angle = math.atan2(y2 - y1, x2 - x1)
    arrow_len = 6
    arrow_w = math.pi / 6
    
    px1 = x2 - arrow_len * math.cos(angle - arrow_w)
    py1 = y2 - arrow_len * math.sin(angle - arrow_w)
    px2 = x2 - arrow_len * math.cos(angle + arrow_w)
    py2 = y2 - arrow_len * math.sin(angle + arrow_w)
    
    p = c.beginPath()
    p.moveTo(x2, y2)
    p.lineTo(px1, py1)
    p.lineTo(px2, py2)
    p.close()
    c.drawPath(p, fill=1, stroke=0)

def draw_tactical_pitch(c, x, y, w, h, rot_data):
    c.setFillColor(colors.HexColor("#FCEADE"))
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.rect(x, y, w, h, fill=1, stroke=1)
    
    c.setStrokeColor(colors.HexColor("#922B21"))
    c.setLineWidth(3)
    c.line(x, y + h, x + w, y + h)
    
    c.setStrokeColor(colors.HexColor("#A6ACAF"))
    c.setLineWidth(1)
    c.line(x, y + h * 0.68, x + w, y + h * 0.68)
    
    c.setStrokeColor(colors.HexColor("#D5D8DC"))
    c.setLineWidth(0.6)
    c.setDash(2, 2)
    c.line(x + w * 0.33, y, x + w * 0.33, y + h * 0.68)
    c.line(x + w * 0.66, y, x + w * 0.66,
