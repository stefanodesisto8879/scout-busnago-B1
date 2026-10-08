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
            if eval
