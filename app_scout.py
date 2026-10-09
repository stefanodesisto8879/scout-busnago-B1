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
# BENCHMARK MODELLO DI PRESTAZIONE BUSNAGO B1 2026-27
# ==========================================================
BENCHMARK_B1 = {
    "serve": {"ace_min": 6.0, "err_max": 10.0},
    "reception": {"pos_min": 50.0, "slash_max": 35.0, "err_max": 7.0},
    "att_cp": {"kill_min": 35.0, "err_max": 15.0},
    "att_bp": {"kill_min": 30.0, "err_max": 15.0},
    "att_tot": {"kill_min": 32.0, "err_max": 16.0},
}

# ==========================================================
# COORDINATE CAMPO RIGOROSE (SOTTOZONE CLICK&SCOUT)
# ==========================================================
ATTACK_ORIGIN_FULL = {
    "2": (0.17, 0.53), "3": (0.50, 0.53), "4": (0.83, 0.53),
    "9": (0.17, 0.70), "8": (0.50, 0.70), "7": (0.83, 0.70),
    "1": (0.17, 0.88), "6": (0.50, 0.88), "5": (0.83, 0.88),
}

DEFENSE_TARGET_FULL = {
    "4": (0.17, 0.44), "3": (0.50, 0.44), "2": (0.83, 0.44),
    "9": (0.17, 0.28), "8": (0.50, 0.28), "7": (0.83, 0.28),
    "5": (0.17, 0.11), "6": (0.50, 0.11), "1": (0.83, 0.11),
}

SERVE_TARGET = {
    "4": (0.17, 0.70), "3": (0.50, 0.70), "2": (0.83, 0.70),
    "9": (0.17, 0.45), "8": (0.50, 0.45), "7": (0.83, 0.45),
    "5": (0.17, 0.18), "6": (0.50, 0.18), "1": (0.83, 0.18),
}

# ==========================================================
# PARSER CLICK&SCOUT (.dvw)
# ==========================================================
def parse_dvw(file_text, target_set=None, force_opp_name=None):
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

    is_swapped = False
    if force_opp_name and force_opp_name.lower() in teams["home"].lower():
        teams["home"], teams["opp"] = teams["opp"], teams["home"]
        home_players, opp_players = opp_players, home_players
        is_swapped = True

    rotations = {
        p: {
            "attacks": [], "serves_data": [], "att_dist": defaultdict(int),
            "center_base_dist": defaultdict(lambda: defaultdict(int)),
            "center_base_tot": defaultdict(int), "total_att": 0
        }
        for p in range(1, 7)
    }
    
    opp_rec = defaultdict(lambda: {"#": 0, "+": 0, "!": 0, "-": 0, "/": 0, "=": 0, "tot": 0})
    opp_att = defaultdict(lambda: {"#": 0, "+": 0, "-": 0, "/": 0, "=": 0, "tot": 0, "attacks": []})
    home_rec = defaultdict(lambda: {"#": 0, "+": 0, "!": 0, "-": 0, "/": 0, "=": 0, "tot": 0})
    home_att = defaultdict(lambda: {"#": 0, "+": 0, "-": 0, "/": 0, "=": 0, "tot": 0, "attacks": []})
    home_srv = defaultdict(lambda: {"#": 0, "+": 0, "-": 0, "/": 0, "=": 0, "tot": 0})

    opp_servers_adv = defaultdict(lambda: {
        "types": defaultdict(int), "trajectories": defaultdict(int),
        "tot": 0, "ace": 0, "err": 0
    })
    setter_on_rec = {"pos": defaultdict(int), "neg": defaultdict(int), "tot_pos": 0, "tot_neg": 0}
    money_time = defaultdict(lambda: {"tot": 0, "pts": 0, "err": 0})
    phase_att = {"cp": defaultdict(int), "bp": defaultdict(int), "tot_cp": 0, "tot_bp": 0}
    shot_types = defaultdict(lambda: {"hard": 0, "tip": 0, "tot": 0})
    
    skill_points = {
        "home": {"attack": 0, "serve": 0, "block": 0},
        "opp": {"attack": 0, "serve": 0, "block": 0}
    }
    home_errors = {"attack": 0, "serve": 0}
    
    phase_stats = {
        "home": {"cp_tot": 0, "cp_kill": 0, "cp_err": 0, "bp_tot": 0, "bp_kill": 0, "bp_err": 0},
        "opp": {"cp_tot": 0, "cp_kill": 0, "cp_err": 0, "bp_tot": 0, "bp_kill": 0, "bp_err": 0}
    }
    
    current_set = 1
    last_serve_team = None
    last_opp_rec_eval = None

    for row in lines[idx:]:
        parts = row.split(";")
        if not parts or not parts[0]:
            continue
            
        code = parts[0]
        if "**" in code and "set" in code:
            m = re.search(r"\*\*(\d)set", code)
            if m: current_set = int(m.group(1)) + 1
            continue
            
        if target_set is not None and current_set != target_set:
            continue

        opp_lineup = parts[19:25] if len(parts) >= 25 else []
        p_rot = 1
        setter_num = "1"
        for num, pinfo in opp_players.items():
            if pinfo.get("role") == "5" or "P" in pinfo.get("name", "") or num in ["01", "1"]:
                setter_num = str(int(num))
                break
        if setter_num in opp_lineup:
            p_rot = opp_lineup.index(setter_num) + 1
        
        if len(code) < 4:
            continue
            
        raw_team_char = code[0]
        team_char = ("a" if raw_team_char == "*" else ("*" if raw_team_char == "a" else raw_team_char)) if is_swapped else raw_team_char

        player = code[1:3]
        skill = code[3]
        eval_char = code[5] if len(code) > 5 else ""
        hit_type = code[4] if len(code) > 4 else ""
        
        custom_call = parts[13].strip() if len(parts) > 13 and parts[13].strip() else ""
        attack_type = code[3:5] if len(code) >= 5 else ""

        traj_match = re.search(r"~(\d)(\d)", code)
        start_z = traj_match.group(1) if traj_match else ""
        end_z = traj_match.group(2) if traj_match else ""

        score_home = int(parts[14]) if len(parts) > 14 and parts[14].isdigit() else 0
        score_opp = int(parts[15]) if len(parts) > 15 and parts[15].isdigit() else 0
        is_money_time = (score_home >= 20 or score_opp >= 20)

        if skill == "S":
            last_serve_team = team_char
            last_opp_rec_eval = None

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
                is_err = eval_char in ["=", "/"]
                if is_err: home_errors["attack"] += 1
                if eval_char in home_att[player]: home_att[player][eval_char] += 1
                
                is_kill = (eval_char == "#")
                if last_serve_team == "a":
                    phase_stats["home"]["cp_tot"] += 1
                    if is_kill: phase_stats["home"]["cp_kill"] += 1
                    if is_err: phase_stats["home"]["cp_err"] += 1
                else:
                    phase_stats["home"]["bp_tot"] += 1
                    if is_kill: phase_stats["home"]["bp_kill"] += 1
                    if is_err: phase_stats["home"]["bp_err"] += 1

        # ---------------- AVVERSARI (a) ----------------
        elif team_char == "a":
            if skill == "S":
                srv_type = hit_type if hit_type in ["Q", "M", "T"] else "S"
                opp_servers_adv[player]["tot"] += 1
                opp_servers_adv[player]["types"][srv_type] += 1
                if eval_char == "#":
                    skill_points["opp"]["serve"] += 1
                    opp_servers_adv[player]["ace"] += 1
                if eval_char == "=": opp_servers_adv[player]["err"] += 1
                if start_z and end_z:
                    opp_servers_adv[player]["trajectories"][f"Z{start_z}->Z{end_z}"] += 1
                if end_z:
                    rotations[p_rot]["serves_data"].append((player, start_z, end_z, eval_char))

            elif skill == "B":
                if eval_char == "#": skill_points["opp"]["block"] += 1

            elif skill == "R":
                opp_rec[player]["tot"] += 1
                if eval_char in opp_rec[player]: opp_rec[player][eval_char] += 1
                last_opp_rec_eval = eval_char
                    
            elif skill == "A":
                opp_att[player]["tot"] += 1
                if eval_char == "#": skill_points["opp"]["attack"] += 1
                if eval_char in opp_att[player]: opp_att[player][eval_char] += 1
                is_kill = (eval_char == "#")
                is_err = eval_char in ["=", "/"]

                if last_serve_team == "*":
                    phase_stats["opp"]["cp_tot"] += 1
                    phase_att["tot_cp"] += 1
                    if start_z: phase_att["cp"][start_z] += 1
                    if is_kill: phase_stats["opp"]["cp_kill"] += 1
                    if is_err: phase_stats["opp"]["cp_err"] += 1
                else:
                    phase_stats["opp"]["bp_tot"] += 1
                    phase_att["tot_bp"] += 1
                    if start_z: phase_att["bp"][start_z] += 1
                    if is_kill: phase_stats["opp"]["bp_kill"] += 1
                    if is_err: phase_stats["opp"]["bp_err"] += 1

                if last_opp_rec_eval in ["#", "+"]:
                    setter_on_rec["tot_pos"] += 1
                    if start_z: setter_on_rec["pos"][start_z] += 1
                elif last_opp_rec_eval in ["-", "!", "/"]:
                    setter_on_rec["tot_neg"] += 1
                    if start_z: setter_on_rec["neg"][start_z] += 1

                if is_money_time:
                    money_time[player]["tot"] += 1
                    if is_kill: money_time[player]["pts"] += 1
                    if eval_char in ["=", "/"]: money_time[player]["err"] += 1

                shot_types[player]["tot"] += 1
                if hit_type in ["T", "P"]: shot_types[player]["tip"] += 1
                else: shot_types[player]["hard"] += 1

                if start_z:
                    att_rec = (player, start_z, end_z, eval_char)
                    rotations[p_rot]["total_att"] += 1
                    rotations[p_rot]["att_dist"][start_z] += 1
                    rotations[p_rot]["attacks"].append(att_rec)
                    opp_att[player]["attacks"].append(att_rec)
                    
                    p_info = opp_players.get(player, {})
                    is_center = (str(p_info.get("role", "")).strip() == "4") or ("C" in p_info.get("name", "").upper()) or (start_z == "3")

                    base_call = "K1"
                    if custom_call: base_call = custom_call
                    elif "X7" in attack_type or "K7" in attack_type or (is_center and end_z in ["2", "1", "7"]): base_call = "K7"
                    elif "X1" in attack_type or "K1" in attack_type or (is_center and end_z in ["4", "5", "9"]): base_call = "K1"
                    elif is_center: base_call = "KC"

                    set_dest = "Z4" if start_z == "4" else ("Z2" if start_z == "2" else ("Z3" if start_z == "3" else ("Pipe" if start_z in ["8", "6"] else f"Z{start_z}")))
                    rotations[p_rot]["center_base_tot"][base_call] += 1
                    rotations[p_rot]["center_base_dist"][base_call][set_dest] += 1

    return {
        "teams": teams, "home_players": home_players, "opp_players": opp_players,
        "rotations": rotations, "opp_reception": opp_rec, "opp_attack": opp_att,
        "home_reception": home_rec, "home_attack": home_att, "home_errors": home_errors,
        "home_srv": home_srv, "phase_stats": phase_stats, "skill_points": skill_points,
        "opp_servers_adv": opp_servers_adv, "setter_on_rec": setter_on_rec,
        "money_time": money_time, "phase_att": phase_att, "shot_types": shot_types
    }

# ==========================================================
# AGGREGATORE STATISTICO MULTI-GARA
# ==========================================================
def aggregate_scouts(scout_list, target_opp_name="Avversario"):
    if not scout_list: return None
    combined = scout_list[0]
    combined["teams"]["opp"] = target_opp_name
    combined["teams"]["home"] = "Studio Multi-Gara"

    for other in scout_list[1:]:
        for p_num, p_info in other["opp_players"].items():
            if p_num not in combined["opp_players"]: combined["opp_players"][p_num] = p_info

        for p in range(1, 7):
            c_rot, o_rot = combined["rotations"][p], other["rotations"][p]
            c_rot["attacks"].extend(o_rot["attacks"])
            c_rot["serves_data"].extend(o_rot["serves_data"])
            c_rot["total_att"] += o_rot["total_att"]
            for z, cnt in o_rot["att_dist"].items(): c_rot["att_dist"][z] += cnt
            for base, cnt in o_rot["center_base_tot"].items(): c_rot["center_base_tot"][base] += cnt
            for base, dest_dict in o_rot["center_base_dist"].items():
                for dest_z, cnt in dest_dict.items(): c_rot["center_base_dist"][base][dest_z] += cnt

        for p_num, r_stat in other["opp_reception"].items():
            for k, val in r_stat.items(): combined["opp_reception"][p_num][k] += val

        for p_num, a_stat in other["opp_attack"].items():
            for k in ["#", "+", "-", "/", "=", "tot"]: combined["opp_attack"][p_num][k] += a_stat[k]
            combined["opp_attack"][p_num]["attacks"].extend(a_stat["attacks"])

        for side in ["home", "opp"]:
            for sk in ["attack", "serve", "block"]: combined["skill_points"][side][sk] += other["skill_points"][side][sk]
            for ph in ["cp_tot", "cp_kill", "cp_err", "bp_tot", "bp_kill", "bp_err"]: combined["phase_stats"][side][ph] += other["phase_stats"][side][ph]

        for p_num, s_data in other["opp_servers_adv"].items():
            combined["opp_servers_adv"][p_num]["tot"] += s_data["tot"]
            combined["opp_servers_adv"][p_num]["ace"] += s_data["ace"]
            combined["opp_servers_adv"][p_num]["err"] += s_data["err"]
            for t_k, t_v in s_data["types"].items(): combined["opp_servers_adv"][p_num]["types"][t_k] += t_v
            for tr_k, tr_v in s_data["trajectories"].items(): combined["opp_servers_adv"][p_num]["trajectories"][tr_k] += tr_v

        combined["setter_on_rec"]["tot_pos"] += other["setter_on_rec"]["tot_pos"]
        combined["setter_on_rec"]["tot_neg"] += other["setter_on_rec"]["tot_neg"]
        for z, cnt in other["setter_on_rec"]["pos"].items(): combined["setter_on_rec"]["pos"][z] += cnt
        for z, cnt in other["setter_on_rec"]["neg"].items(): combined["setter_on_rec"]["neg"][z] += cnt

        for p_num, m_data in other["money_time"].items():
            combined["money_time"][p_num]["tot"] += m_data["tot"]
            combined["money_time"][p_num]["pts"] += m_data["pts"]
            combined["money_time"][p_num]["err"] += m_data["err"]

        combined["phase_att"]["tot_cp"] += other["phase_att"]["tot_cp"]
        combined["phase_att"]["tot_bp"] += other["phase_att"]["tot_bp"]
        for z, cnt in other["phase_att"]["cp"].items(): combined["phase_att"]["cp"][z] += cnt
        for z, cnt in other["phase_att"]["bp"].items(): combined["phase_att"]["bp"][z] += cnt

        for p_num, sh_data in other["shot_types"].items():
            combined["shot_types"][p_num]["tot"] += sh_data["tot"]
            combined["shot_types"][p_num]["hard"] += sh_data["hard"]
            combined["shot_types"][p_num]["tip"] += sh_data["tip"]

    return combined

# ==========================================================
# GRAFICA VETTORIALE TRAIETTORIE E CAMPI BIANCHI
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

    # Numeri sottozone piccoli nell'angolino in alto a sinistra
    c.setFont("Helvetica", 4.8)
    c.setFillColor(colors.HexColor("#7F8C8D"))
    c.drawString(x + 2.5, net_y + 3 * h_third - 6, "1")
    c.drawString(x + w_third + 2.5, net_y + 3 * h_third - 6, "6")
    c.drawString(x + 2 * w_third + 2.5, net_y + 3 * h_third - 6, "5")
    c.drawString(x + 2.5, net_y + 2 * h_third - 6, "9")
    c.drawString(x + w_third + 2.5, net_y + 2 * h_third - 6, "8")
    c.drawString(x + 2 * w_third + 2.5, net_y + 2 * h_third - 6, "7")
    c.drawString(x + 2.5, net_y + h_third - 6, "2")
    c.drawString(x + w_third + 2.5, net_y + h_third - 6, "3")
    c.drawString(x + 2 * w_third + 2.5, net_y + h_third - 6, "4")

    c.drawString(x + 2.5, net_y - 6, "4")
    c.drawString(x + w_third + 2.5, net_y - 6, "3")
    c.drawString(x + 2 * w_third + 2.5, net_y - 6, "2")
    c.drawString(x + 2.5, net_y - h_third - 6, "9")
    c.drawString(x + w_third + 2.5, net_y - h_third - 6, "8")
    c.drawString(x + 2 * w_third + 2.5, net_y - h_third - 6, "7")
    c.drawString(x + 2.5, net_y - 2 * h_third - 6, "5")
    c.drawString(x + w_third + 2.5, net_y - 2 * h_third - 6, "6")
    c.drawString(x + 2 * w_third + 2.5, net_y - 2 * h_third - 6, "1")

    if p_dist and total_att and total_att > 0:
        p4, p3, p2 = p_dist.get("4", 0), p_dist.get("3", 0), p_dist.get("2", 0)
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
            col = colors.HexColor("#27AE60") if ev == "#" else (colors.HexColor("#E74C3C") if ev in ["=", "/"] else colors.HexColor("#F39C12"))
            lw = 1.6 if ev in ["#", "=", "/"] else 1.1
            draw_trajectory(c, x1, y1, x2, y2, col, line_w=lw)

def draw_serve_box_with_player(c, x, y, w, h, serves_list, players_dict):
    server_counts = defaultdict(int)
    for p, _, _, _ in serves_list: server_counts[p] += 1
    main_server = max(server_counts, key=server_counts.get) if server_counts else None
    
    header_h = 16
    c.setFillColor(colors.HexColor("#34495E"))
    c.rect(x, y + h - header_h, w, header_h, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 6.0)
    c.drawString(x + 3, y + h - 7, "BATTITORE:")
    if main_server:
        s_name = players_dict.get(main_server, {}).get("name", "")[:10]
        c.setFont("Helvetica-Bold", 6.8)
        c.drawString(x + 3, y + h - 14, f"#{main_server} {s_name}")
    else:
        c.setFont("Helvetica", 6.0)
        c.drawString(x + 3, y + h - 14, "N/D")

    court_h = h - header_h
    c.setFillColor(colors.HexColor("#FFFFFF"))
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.8)
    c.rect(x, y, w, court_h, fill=1, stroke=1)
    
    c.setStrokeColor(colors.black)
    c.setLineWidth(1.8)
    c.line(x, y + court_h, x + w, y + court_h)

    c.setStrokeColor(colors.HexColor("#F5B7B1"))
    c.setLineWidth(0.5)
    c.setDash(2, 2)
    w_th, h_th = w / 3.0, court_h / 3.0
    c.line(x + w_th, y, x + w_th, y + court_h)
    c.line(x + 2 * w_th, y, x + 2 * w_th, y + court_h)
    c.line(x, y + h_th, x + w, y + h_th)
    c.line(x, y + 2 * h_th, x + w, y + 2 * h_th)
    c.setDash()

    counts = defaultdict(int)
    for _, _, ez, _ in serves_list:
        if ez: counts[ez] += 1
    max_c = max(counts.values()) if counts else 0

    for zn, cnt in counts.items():
        if zn in SERVE_TARGET and cnt > 0:
            zx = x + SERVE_TARGET[zn][0] * w
            zy = y + SERVE_TARGET[zn][1] * court_h
            rad = 6.5 if (cnt == max_c and max_c > 1) else 5.0
            c.setFillColor(colors.HexColor("#8E44AD") if (cnt == max_c and max_c > 1) else colors.HexColor("#2C3E50"))
            c.circle(zx, zy, rad, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 6.5)
            c.drawCentredString(zx, zy - 2.2, str(cnt))

# ==========================================================
# GENERATORE PDF LIVE E PRE-GARA
# ==========================================================
def generate_pdf(data, set_label="Gara", is_pre_gara=False):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4))
    width, height = landscape(A4)
    
    # ----------------------------------------------------
    # PAGINA 1: ROTAZIONI DI SQUADRA & METRICHE LIVE
    # ----------------------------------------------------
    c.setFillColor(colors.HexColor("#1A252F"))
    c.rect(0, height - 34, width, 34, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20, height - 20, f"STUDIO TATTICO: {data['teams']['opp']} ({set_label})")
    c.setFont("Helvetica", 8)
    c.drawString(20, height - 30, "Campo con Sottozone 1-9  |  Relazione Base C -> Spinta Alzata  |  Focus Squadre")

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
        
        sx, sy = bx + cw + 8, by + 8
        sw, sh = bw - cw - 14, 62
        draw_serve_box_with_player(c, sx, sy, sw, sh, rot["serves_data"], data["opp_players"])
        
        dx, dw = bx + cw + 8, bw - cw - 14
        c.setFillColor(colors.HexColor("#1A252F"))
        c.setFont("Helvetica-Bold", 6.8)
        c.drawString(dx, by + bh - 26, "BASE C -> ALZATA:")
        
        sorted_bases = sorted(rot["center_base_tot"].items(), key=lambda x: x[1], reverse=True)
        cur_y = by + bh - 38
        
        if sorted_bases:
            for b_idx, (b_name, b_tot) in enumerate(sorted_bases[:2]):
                dest_map = rot["center_base_dist"][b_name]
                sorted_dests = sorted(dest_map.items(), key=lambda x: x[1], reverse=True)
                box_h = 24 if len(sorted_dests) > 1 else 17
                c.setFillColor(colors.HexColor("#FEF9E7") if b_idx == 0 else colors.HexColor("#F4F6F6"))
                c.setStrokeColor(colors.HexColor("#F39C12") if b_idx == 0 else colors.HexColor("#BDC3C7"))
                c.roundRect(dx, cur_y - box_h, dw, box_h, 2, fill=1, stroke=1)
                
                c.setFont("Helvetica-Bold", 6.5)
                c.setFillColor(colors.HexColor("#B7950B") if b_idx == 0 else colors.HexColor("#2C3E50"))
                c.drawString(dx + 3, cur_y - 8, f"Base {b_name} ({b_tot}p):")
                
                d_y = cur_y - 15
                for d_zone, d_cnt in sorted_dests[:2]:
                    pct_d = (d_cnt / b_tot) * 100
                    c.setFont("Helvetica-Bold", 6.0)
                    c.setFillColor(colors.HexColor("#C0392B") if pct_d >= 50 else colors.HexColor("#2C3E50"))
                    c.drawString(dx + 5, d_y, f"-> {d_zone}: {pct_d:.0f}%")
                    bar_w = 22.0 * (pct_d / 100.0)
                    c.setFillColor(colors.HexColor("#E67E22") if pct_d >= 50 else colors.HexColor("#3498DB"))
                    c.rect(dx + dw - 25, d_y + 0.5, max(1.5, bar_w), 2.2, fill=1, stroke=0)
                    d_y -= 7.5
                cur_y -= (box_h + 3)
        else:
            c.setFont("Helvetica-Oblique", 6.2)
            c.setFillColor(colors.HexColor("#7F8C8D"))
            c.drawString(dx + 2, cur_y - 10, "Nessun attacco")
            cur_y -= 25

        if rot["att_dist"] and rot["total_att"] > 0:
            top_z = max(rot["att_dist"], key=rot["att_dist"].get)
            top_pct = (rot["att_dist"][top_z] / rot["total_att"]) * 100
            badge_h, badge_y = 12, by + sh + 5
            c.setFillColor(colors.HexColor("#C0392B") if top_pct >= 50 else colors.HexColor("#2C3E50"))
            c.roundRect(dx, badge_y, dw, badge_h, 2.5, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 6.6)
            c.drawCentredString(dx + dw / 2.0, badge_y + 3.5, f"SPINTA MAX: Z{top_z} ({top_pct:.0f}%)")

    # Pannello Destro
    px = 626
    py = height - 500
    pw = width - px - 15
    ph = 466
    c.setFillColor(colors.HexColor("#F8F9FA"))
    c.rect(px, py, pw, ph, fill=1, stroke=0)
    c.setStrokeColor(colors.HexColor("#CFD8DC"))
    c.rect(px, py, pw, ph, fill=0, stroke=1)
    c.setFillColor(colors.HexColor("#263238"))
    c.rect(px, py + ph - 22, pw, 22, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(px + 10, py + ph - 15, "CONFRONTO SQUADRE & METRICHE")

    c_y = py + ph - 26

    # 1. Punti Diretti
    card_pts_h = 66
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.HexColor("#CFD8DC"))
    c.rect(px + 6, c_y - card_pts_h, pw - 12, card_pts_h, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#263238"))
    c.setFont("Helvetica-Bold", 7.2)
    c.drawString(px + 10, c_y - 12, "PUNTI DIRETTI")
    c.setFillColor(colors.HexColor("#1B4F72"))
    c.circle(px + pw - 90, c_y - 10, 3, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 6.8)
    c.drawString(px + pw - 84, c_y - 12, "Busnago")
    c.setFillColor(colors.HexColor("#D35400"))
    c.circle(px + pw - 42, c_y - 10, 3, fill=1, stroke=0)
    c.drawString(px + pw - 36, c_y - 12, "Avv")

    sp = data["skill_points"]
    b_start_x = px + 90
    b_max_total_w = (px + pw - 12) - b_start_x - 4

    def draw_skill_row(y_pos, label, val_h, val_o):
        c.setFont("Helvetica-Bold", 6.8)
        c.setFillColor(colors.HexColor("#455A64"))
        c.drawString(px + 10, y_pos + 1, label)
        c.setFillColor(colors.HexColor("#1B4F72"))
        c.drawString(px + 48, y_pos + 1, f"{val_h:>2}")
        c.setFillColor(colors.HexColor("#90A4AE"))
        c.drawString(px + 60, y_pos + 1, "vs")
        c.setFillColor(colors.HexColor("#D35400"))
        c.drawString(px + 72, y_pos + 1, f"{val_o:<2}")

        total_v = val_h + val_o
        w_h = (val_h / total_v) * b_max_total_w if total_v > 0 else b_max_total_w / 2.0
        w_o = b_max_total_w - w_h
        c.setFillColor(colors.HexColor("#2980B9"))
        c.rect(b_start_x, y_pos, max(1.5, w_h), 5.5, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#E67E22"))
        c.rect(b_start_x + w_h, y_pos, max(1.5, w_o), 5.5, fill=1, stroke=0)

    draw_skill_row(c_y - 25, "Attacco", sp["home"]["attack"], sp["opp"]["attack"])
    draw_skill_row(c_y - 37, "Ace", sp["home"]["serve"], sp["opp"]["serve"])
    draw_skill_row(c_y - 49, "Muro", sp["home"]["block"], sp["opp"]["block"])

    tot_h_pts = sp["home"]["attack"] + sp["home"]["serve"] + sp["home"]["block"]
    tot_o_pts = sp["opp"]["attack"] + sp["opp"]["serve"] + sp["opp"]["block"]
    c.setFont("Helvetica-Bold", 6.8)
    c.setFillColor(colors.HexColor("#1B4F72") if tot_h_pts >= tot_o_pts else colors.HexColor("#D35400"))
    c.drawString(px + 10, c_y - 61, f"Totale Vincenti: Busnago {tot_h_pts}  -  Avversario {tot_o_pts}")

    c_y = c_y - card_pts_h - 4

    # 2. Errori Diretti & Fasi CP/BP
    card_err_h = 58
    c.setFillColor(colors.HexColor("#FDEDEC"))
    c.setStrokeColor(colors.HexColor("#F5B7B1"))
    c.rect(px + 6, c_y - card_err_h, pw - 12, card_err_h, fill=1, stroke=1)
    err_att, err_srv = data["home_errors"]["attack"], data["home_errors"]["serve"]
    err_tot = err_att + err_srv
    
    c.setFillColor(colors.HexColor("#C0392B"))
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(px + 10, c_y - 11, "ERRORI DIRETTI BUSNAGO")
    badge_x, badge_y = px + pw - 20, c_y - 13
    c.circle(badge_x, badge_y, 8.5, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawCentredString(badge_x, badge_y - 2.5, str(err_tot))

    c.setFillColor(colors.HexColor("#78281F"))
    c.setFont("Helvetica", 6.8)
    c.drawString(px + 10, c_y - 22, f"• Battuta: {err_srv} err  |  Attacco: {err_att} out / murati subiti")
    c.setStrokeColor(colors.HexColor("#F5B7B1"))
    c.line(px + 10, c_y - 26, px + pw - 10, c_y - 26)

    ps = data["phase_stats"]
    h_cp = (ps["home"]["cp_kill"] / ps["home"]["cp_tot"] * 100) if ps["home"]["cp_tot"] > 0 else 0
    o_cp = (ps["opp"]["cp_kill"] / ps["opp"]["cp_tot"] * 100) if ps["opp"]["cp_tot"] > 0 else 0
    h_bp = (ps["home"]["bp_kill"] / ps["home"]["bp_tot"] * 100) if ps["home"]["bp_tot"] > 0 else 0
    o_bp = (ps["opp"]["bp_kill"] / ps["opp"]["bp_tot"] * 100) if ps["opp"]["bp_tot"] > 0 else 0

    c.setFont("Helvetica-Bold", 6.6)
    c.setFillColor(colors.HexColor("#1A252F"))
    c.drawString(px + 10, c_y - 36, "CAMBIO PALLA:")
    c.setFont("Helvetica", 6.6)
    c.drawString(px + 68, c_y - 36, f"Bus {h_cp:.0f}%  vs  Avv {o_cp:.0f}%")
    cp_bar_x = px + 140
    cp_bar_max = (px + pw - 14) - cp_bar_x
    if cp_bar_max > 0:
        c.setFillColor(colors.HexColor("#2980B9"))
        c.rect(cp_bar_x, c_y - 37, max(2, cp_bar_max * (h_cp / 100.0)), 4, fill=1, stroke=0)

    c.setFont("Helvetica-Bold", 6.6)
    c.setFillColor(colors.HexColor("#1A252F"))
    c.drawString(px + 10, c_y - 48, "BREAK POINT:")
    c.setFont("Helvetica", 6.6)
    c.drawString(px + 68, c_y - 48, f"Bus {h_bp:.0f}%  vs  Avv {o_bp:.0f}%")
    if cp_bar_max > 0:
        c.setFillColor(colors.HexColor("#27AE60"))
        c.rect(cp_bar_x, c_y - 49, max(2, cp_bar_max * (h_bp / 100.0)), 4, fill=1, stroke=0)

    c_y = c_y - card_err_h - 4

    # ====================================================
    # 3. FOCUS BUSNAGO (REINSERITE TUTTE LE STATISTICHE INDIVIDUALI)
    # ====================================================
    card_busnago_h = 132
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.HexColor("#1B4F72"))
    c.rect(px + 6, c_y - card_busnago_h, pw - 12, card_busnago_h, fill=1, stroke=1)
    
    c.setFillColor(colors.HexColor("#1B4F72"))
    c.rect(px + 6, c_y - 14, pw - 12, 14, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 7.2)
    c.drawString(px + 10, c_y - 10, "FOCUS BUSNAGO (STATISTICHE INDIVIDUALI)")

    # Sezione Ricezione Individuale
    c.setFont("Helvetica-Bold", 6.5)
    c.setFillColor(colors.HexColor("#2C3E50"))
    c.drawString(px + 10, c_y - 23, "RICEZIONE INDIVIDUALE (min. 3 ric):")
    c.setFont("Helvetica-Bold", 5.8)
    c.setFillColor(colors.HexColor("#7F8C8D"))
    c.drawString(px + 10, c_y - 31, "#  Nome         Tot    #+ %     Err %")
    c.setStrokeColor(colors.HexColor("#BDC3C7"))
    c.line(px + 10, c_y - 33, px + pw - 12, c_y - 33)

    rec_qual_list = []
    for num, st_r in data["home_reception"].items():
        if st_r["tot"] >= 3:
            pos_pct = ((st_r["#"] + st_r["+"]) / st_r["tot"]) * 100
            err_pct = (st_r["="] / st_r["tot"]) * 100
            rec_qual_list.append((num, st_r["tot"], pos_pct, err_pct))
    rec_qual_list.sort(key=lambda x: x[2], reverse=True)

    sub_y = c_y - 41
    if rec_qual_list:
        for r in rec_qual_list[:3]:
            pname = data["home_players"].get(r[0], {}).get("name", "")[:9]
            c.setFont("Helvetica", 6.2)
            c.setFillColor(colors.HexColor("#C0392B") if r[3] >= 15 else colors.HexColor("#2C3E50"))
            c.drawString(px + 10, sub_y, f"#{r[0]} {pname:<10} {r[1]:<4} {r[2]:.0f}%     {r[3]:.0f}%")
            sub_y -= 8.5
    else:
        c.setFont("Helvetica-Oblique", 6.0)
        c.setFillColor(colors.HexColor("#7F8C8D"))
        c.drawString(px + 10, sub_y, "Nessun giocatore con >= 3 ricezioni")
        sub_y -= 8.5

    # Sezione Attacco Individuale
    c.setStrokeColor(colors.HexColor("#ECEFF1"))
    c.line(px + 10, sub_y + 2, px + pw - 12, sub_y + 2)
    sub_y -= 5

    c.setFont("Helvetica-Bold", 6.5)
    c.setFillColor(colors.HexColor("#2C3E50"))
    c.drawString(px + 10, sub_y, "ATTACCO INDIVIDUALE:")
    sub_y -= 8.0
    c.setFont("Helvetica-Bold", 5.8)
    c.setFillColor(colors.HexColor("#7F8C8D"))
    c.drawString(px + 10, sub_y, "#  Nome         Tot    Kill     Eff %")
    c.setStrokeColor(colors.HexColor("#BDC3C7"))
    c.line(px + 10, sub_y - 2, px + pw - 12, sub_y - 2)

    h_att_list = []
    for num, st_a in data["home_attack"].items():
        if st_a["tot"] > 0:
            eff = ((st_a["#"] - st_a["="] - st_a["/"]) / st_a["tot"]) * 100
            h_att_list.append((num, st_a["tot"], st_a["#"], eff))
    h_att_list.sort(key=lambda x: x[1], reverse=True)

    sub_y -= 9.5
    if h_att_list:
        for a_item in h_att_list[:3]:
            pname = data["home_players"].get(a_item[0], {}).get("name", "")[:9]
            c.setFont("Helvetica", 6.2)
            c.setFillColor(colors.HexColor("#27AE60") if a_item[3] >= 35 else colors.HexColor("#2C3E50"))
            c.drawString(px + 10, sub_y, f"#{a_item[0]} {pname:<10} {a_item[1]:<4} {a_item[2]:<4}   {a_item[3]:.0f}%")
            sub_y -= 8.5
    else:
        c.setFont("Helvetica-Oblique", 6.0)
        c.setFillColor(colors.HexColor("#7F8C8D"))
        c.drawString(px + 10, sub_y, "Nessun attacco registrato")
        sub_y -= 8.5

    # Momento NO o Leader squadra
    player_impact = defaultdict(lambda: {"pts": 0, "err": 0})
    for num, st_a in data["home_attack"].items():
        player_impact[num]["pts"] += st_a["#"]
        player_impact[num]["err"] += (st_a["="] + st_a["/"])
    for num, st_r in data["home_reception"].items():
        player_impact[num]["err"] += st_r["="]
    
    worst_perf_player = None
    if player_impact:
        worst_perf_player = sorted(player_impact.items(), key=lambda x: (x[1]["pts"] - x[1]["err"]))[0]

    c.setStrokeColor(colors.HexColor("#ECEFF1"))
    c.line(px + 10, sub_y + 2, px + pw - 12, sub_y + 2)
    sub_y -= 5

    c.setFont("Helvetica-Bold", 6.2)
    if worst_perf_player and (worst_perf_player[1]["pts"] - worst_perf_player[1]["err"]) < 0:
        wp_num = worst_perf_player[0]
        wp_name = data["home_players"].get(wp_num, {}).get("name", "")[:9]
        saldo = worst_perf_player[1]["pts"] - worst_perf_player[1]["err"]
        c.setFillColor(colors.HexColor("#C0392B"))
        c.drawString(px + 10, sub_y, f"⚠️ Momento NO: #{wp_num} {wp_name} (Saldo Punti/Err: {saldo})")
    else:
        c.setFillColor(colors.HexColor("#27AE60"))
        c.drawString(px + 10, sub_y, "• Rendimento di squadra: Equilibrato")

    c_y = c_y - card_busnago_h - 4

    # ====================================================
    # 4. TARGET AVVERSARI
    # ====================================================
    card_opp_h = 76
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.HexColor("#D35400"))
    c.rect(px + 6, c_y - card_opp_h, pw - 12, card_opp_h, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#D35400"))
    c.rect(px + 6, c_y - 14, pw - 12, 14, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 7.2)
    c.drawString(px + 10, c_y - 10, "TARGET AVVERSARI (DECISIONI TATTICHE)")

    opp_rec_qual = []
    for num, st_r in data["opp_reception"].items():
        if st_r["tot"] >= 3:
            opp_rec_qual.append((num, st_r["tot"], ((st_r["#"] + st_r["+"]) / st_r["tot"]) * 100, ((st_r["="] + st_r["/"] + st_r["-"]) / st_r["tot"]) * 100))
    best_opp_rec = max(opp_rec_qual, key=lambda x: x[2]) if opp_rec_qual else None
    worst_opp_rec = max(opp_rec_qual, key=lambda x: x[3]) if opp_rec_qual else None

    sub_opp_y = c_y - 23
    c.setFont("Helvetica-Bold", 6.5)
    c.setFillColor(colors.HexColor("#263238"))
    c.drawString(px + 10, sub_opp_y, "RICEZIONE AVVERSARIA:")
    sub_opp_y -= 9.5

    if worst_opp_rec:
        p_name = data["opp_players"].get(worst_opp_rec[0], {}).get("name", "")[:9]
        c.setFillColor(colors.HexColor("#FDEDEC"))
        c.rect(px + 10, sub_opp_y - 2, pw - 20, 8.5, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#C0392B"))
        c.circle(px + 14, sub_opp_y + 2.5, 2.2, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 6.2)
        c.drawString(px + 19, sub_opp_y, f"BERSAGLIO SERVIZIO: #{worst_opp_rec[0]} {p_name} ({worst_opp_rec[3]:.0f}% neg/err)")
    else:
        c.setFont("Helvetica", 6.2)
        c.setFillColor(colors.HexColor("#546E7A"))
        c.drawString(px + 10, sub_opp_y, "• Dati ric. insufficienti (<3)")
    sub_opp_y -= 9.5

    if best_opp_rec:
        p_name = data["opp_players"].get(best_opp_rec[0], {}).get("name", "")[:9]
        c.setFillColor(colors.HexColor("#E8F8F5"))
        c.rect(px + 10, sub_opp_y - 2, pw - 20, 8.5, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#196F3D"))
        c.circle(px + 14, sub_opp_y + 2.5, 2.2, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 6.2)
        c.drawString(px + 19, sub_opp_y, f"EVITA BATTUTA: #{best_opp_rec[0]} {p_name} ({best_opp_rec[2]:.0f}% #+)")
    else:
        c.setFont("Helvetica", 6.2)
        c.setFillColor(colors.HexColor("#546E7A"))
        c.drawString(px + 10, sub_opp_y, "• Dati ric. insufficienti (<3)")

    sub_opp_y -= 10
    c.setStrokeColor(colors.HexColor("#ECEFF1"))
    c.line(px + 10, sub_opp_y + 2, px + pw - 12, sub_opp_y + 2)
    sub_opp_y -= 6

    opp_att_list = []
    for num, st_a in data["opp_attack"].items():
        if st_a["tot"] > 0:
            opp_att_list.append((num, st_a["tot"], st_a["#"], ((st_a["#"] - st_a["="] - st_a["/"]) / st_a["tot"]) * 100))
    opp_att_by_vol = sorted(opp_att_list, key=lambda x: x[1], reverse=True)
    top_vol_opp = opp_att_by_vol[0] if opp_att_by_vol else None

    non_setters = [a for a in opp_att_list if not ((str(data['opp_players'].get(a[0], {}).get('role', '')).strip() == '5') or ('P' in data['opp_players'].get(a[0], {}).get('name', '').upper()) or ('PAL' in data['opp_players'].get(a[0], {}).get('name', '').upper()))]
    min_vol_opp = sorted(non_setters, key=lambda x: x[1])[0] if non_setters else None

    c.setFont("Helvetica", 6.2)
    c.setFillColor(colors.black)
    if top_vol_opp:
        p_name = data["opp_players"].get(top_vol_opp[0], {}).get("name", "")[:9]
        c.drawString(px + 10, sub_opp_y, f"🔥 Più servito: #{top_vol_opp[0]} {p_name} ({top_vol_opp[1]} pal)")
        sub_opp_y -= 8.5
    if min_vol_opp and min_vol_opp[0] != (top_vol_opp[0] if top_vol_opp else None):
        p_name = data["opp_players"].get(min_vol_opp[0], {}).get("name", "")[:9]
        c.drawString(px + 10, sub_opp_y, f"❄️ Meno servito (no P): #{min_vol_opp[0]} {p_name} ({min_vol_opp[1]} pal)")

    c.showPage()

    # ----------------------------------------------------
    # PAGINA 2: FOCUS ATTACCANTI AVVERSARI (TRAIETTORIE)
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
            label_s = f"Posto {top_start}" if top_start in ["2", "3", "4"] else f"Zona {top_start} (2° Linea)"
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
            
        trend = "Preferisce Diagonale" if diag > par else ("Preferisce Parallela" if par > diag else "Distribuzione Mista")
        c.drawString(rx, fy + fb_h - 114, f"• {trend}")

    c.showPage()

    # ----------------------------------------------------
    # PAGINA 3: NUOVO DOSSIER PRE-GARA AVANZATO (TUTTI E 5 I PUNTI)
    # ----------------------------------------------------
    if is_pre_gara:
        c.setFillColor(colors.HexColor("#1A252F"))
        c.rect(0, height - 34, width, 34, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20, height - 20, f"ANALISI STRATEGICA PRE-GARA AVANZATA: {data['teams']['opp']}")
        c.setFont("Helvetica", 8)
        c.drawString(20, height - 30, "1. Mappa Battuta  |  2. Palleggiatore su Ricezione  |  3. Money Time (20-25)  |  4. CP vs BP  |  5. Tipologia Colpi")

        col1_w, col2_w, col3_w = 260, 260, 250
        box_y, box_h = height - 280, 240

        # 1. MAPPA BATTUTE
        c.setFillColor(colors.white)
        c.setStrokeColor(colors.HexColor("#BDC3C7"))
        c.rect(20, box_y, col1_w, box_h, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#2C3E50"))
        c.rect(20, box_y + box_h - 18, col1_w, 18, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(26, box_y + box_h - 13, "1. CARATTERISTICHE BATTITORI AVVERSARI")

        c.setFont("Helvetica-Bold", 6.4)
        c.setFillColor(colors.HexColor("#7F8C8D"))
        c.drawString(26, box_y + box_h - 30, "# Nome         Tot  Tipo   Ace%  Err%  Direttrice Top")
        c.setStrokeColor(colors.HexColor("#BDC3C7"))
        c.line(26, box_y + box_h - 32, 20 + col1_w - 6, box_y + box_h - 32)

        s_y = box_y + box_h - 43
        sorted_srv = sorted(data["opp_servers_adv"].items(), key=lambda x: x[1]["tot"], reverse=True)
        for p_num, s_info in sorted_srv[:7]:
            if s_info["tot"] >= 3:
                p_name = data["opp_players"].get(p_num, {}).get("name", "")[:8]
                top_type = max(s_info["types"], key=s_info["types"].get) if s_info["types"] else "S"
                type_label = "Spin" if top_type == "S" else ("Float" if top_type == "Q" else "Terra")
                ace_pct = (s_info["ace"] / s_info["tot"] * 100)
                err_pct = (s_info["err"] / s_info["tot"] * 100)
                top_traj = max(s_info["trajectories"], key=s_info["trajectories"].get) if s_info["trajectories"] else "-"
                
                c.setFont("Helvetica", 6.5)
                c.setFillColor(colors.HexColor("#C0392B") if ace_pct >= 15 else colors.black)
                c.drawString(26, s_y, f"#{p_num} {p_name:<8} {s_info['tot']:<3}  {type_label:<5} {ace_pct:>3.0f}%  {err_pct:>3.0f}%  {top_traj}")
                s_y -= 11

        # 2. PALLEGGIATORE: PALLA IN MANO (#/+) vs SCONTATA (-/!)
        c.setFillColor(colors.white)
        c.setStrokeColor(colors.HexColor("#BDC3C7"))
        c.rect(290, box_y, col2_w, box_h, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#2C3E50"))
        c.rect(290, box_y + box_h - 18, col2_w, 18, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(296, box_y + box_h - 13, "2. DISTRIBUZIONE SU QUALITÀ RICEZIONE")

        sr = data["setter_on_rec"]
        p_y = box_y + box_h - 32
        
        c.setFont("Helvetica-Bold", 7.2)
        c.setFillColor(colors.HexColor("#27AE60"))
        c.drawString(296, p_y, f"CON PALLA IN MANO (# / +) - {sr['tot_pos']} palloni:")
        p_y -= 12
        if sr["tot_pos"] > 0:
            for z in ["4", "3", "2", "8"]:
                cnt = sr["pos"].get(z, 0)
                pct = (cnt / sr["tot_pos"] * 100)
                label = "Posto 4" if z == "4" else ("Centro (3)" if z == "3" else ("Posto 2" if z == "2" else "Pipe"))
                c.setFont("Helvetica", 6.8)
                c.setFillColor(colors.black)
                c.drawString(300, p_y, f"• {label}: {pct:.0f}% ({cnt})")
                c.setFillColor(colors.HexColor("#27AE60"))
                c.rect(385, p_y + 1, max(2, 120 * (pct / 100)), 4, fill=1, stroke=0)
                p_y -= 11

        p_y -= 6
        c.setStrokeColor(colors.HexColor("#EAEDED"))
        c.line(296, p_y + 4, 290 + col2_w - 6, p_y + 4)

        c.setFont("Helvetica-Bold", 7.2)
        c.setFillColor(colors.HexColor("#C0392B"))
        c.drawString(296, p_y - 4, f"SU PALLA SCONTATA / STACCATA (- / !) - {sr['tot_neg']} pal:")
        p_y -= 16
        if sr["tot_neg"] > 0:
            for z in ["4", "2", "3", "8"]:
                cnt = sr["neg"].get(z, 0)
                pct = (cnt / sr["tot_neg"] * 100)
                label = "Posto 4" if z == "4" else ("Posto 2" if z == "2" else ("Centro (3)" if z == "3" else "Pipe"))
                c.setFont("Helvetica", 6.8)
                c.setFillColor(colors.black)
                c.drawString(300, p_y, f"• {label}: {pct:.0f}% ({cnt})")
                c.setFillColor(colors.HexColor("#C0392B"))
                c.rect(385, p_y + 1, max(2, 120 * (pct / 100)), 4, fill=1, stroke=0)
                p_y -= 11

        # 3. MONEY TIME (PUNTI DECISIVI 20-25)
        c.setFillColor(colors.white)
        c.setStrokeColor(colors.HexColor("#BDC3C7"))
        c.rect(560, box_y, col3_w, box_h, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#8E44AD"))
        c.rect(560, box_y + box_h - 18, col3_w, 18, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(566, box_y + box_h - 13, "3. MONEY TIME: SCELTE NEI PUNTI 20-25")

        c.setFont("Helvetica-Bold", 6.4)
        c.setFillColor(colors.HexColor("#7F8C8D"))
        c.drawString(566, box_y + box_h - 30, "# Nome         Tot  Vinc  Err   Efficienza")
        c.setStrokeColor(colors.HexColor("#BDC3C7"))
        c.line(566, box_y + box_h - 32, 560 + col3_w - 6, box_y + box_h - 32)

        m_y = box_y + box_h - 43
        sorted_mt = sorted(data["money_time"].items(), key=lambda x: x[1]["tot"], reverse=True)
        if sorted_mt:
            for p_num, m_info in sorted_mt[:6]:
                p_name = data["opp_players"].get(p_num, {}).get("name", "")[:8]
                eff = ((m_info["pts"] - m_info["err"]) / m_info["tot"] * 100) if m_info["tot"] > 0 else 0
                c.setFont("Helvetica", 6.8)
                c.setFillColor(colors.black)
                c.drawString(566, m_y, f"#{p_num} {p_name:<8} {m_info['tot']:<3}  {m_info['pts']:<3}   {m_info['err']:<3}   {eff:>4.0f}%")
                m_y -= 12
        else:
            c.setFont("Helvetica-Oblique", 6.5)
            c.setFillColor(colors.HexColor("#7F8C8D"))
            c.drawString(566, m_y, "Nessun attacco oltre quota 20")

        # Riga inferiore
        b_box_y, b_box_h = height - 505, 215

        # 4. FASI DI GIOCO: CP vs CONTRATTACCO
        c.setFillColor(colors.white)
        c.setStrokeColor(colors.HexColor("#BDC3C7"))
        c.rect(20, b_box_y, 380, b_box_h, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#16A085"))
        c.rect(20, b_box_y + b_box_h - 18, 380, 18, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(26, b_box_y + b_box_h - 13, "4. DISTRIBUZIONE ATTACCO: CAMBIO PALLA vs CONTRATTACCO")

        cp_y = b_box_y + b_box_h - 32
        tot_cp, tot_bp = data["phase_att"]["tot_cp"], data["phase_att"]["tot_bp"]
        c.setFont("Helvetica-Bold", 7.0)
        c.setFillColor(colors.HexColor("#2C3E50"))
        c.drawString(26, cp_y, f"CAMBIO PALLA (su loro ricezione - {tot_cp} pal):")
        cp_y -= 12
        for z in ["4", "3", "2", "8"]:
            cnt = data["phase_att"]["cp"].get(z, 0)
            pct = (cnt / tot_cp * 100) if tot_cp > 0 else 0
            label = "Posto 4" if z == "4" else ("Posto 3" if z == "3" else ("Posto 2" if z == "2" else "Pipe"))
            c.setFont("Helvetica", 6.8)
            c.drawString(30, cp_y, f"• {label}: {pct:.0f}% ({cnt})")
            c.setFillColor(colors.HexColor("#16A085"))
            c.rect(130, cp_y + 1, max(2, 180 * (pct / 100)), 4, fill=1, stroke=0)
            c.setFillColor(colors.black)
            cp_y -= 10

        cp_y -= 6
        c.setStrokeColor(colors.HexColor("#EAEDED"))
        c.line(26, cp_y + 4, 390, cp_y + 4)

        c.setFont("Helvetica-Bold", 7.0)
        c.setFillColor(colors.HexColor("#2C3E50"))
        c.drawString(26, cp_y - 4, f"CONTRATTACCO (dopo loro difesa/transizione - {tot_bp} pal):")
        cp_y -= 16
        for z in ["4", "2", "8", "3"]:
            cnt = data["phase_att"]["bp"].get(z, 0)
            pct = (cnt / tot_bp * 100) if tot_bp > 0 else 0
            label = "Posto 4" if z == "4" else ("Posto 2" if z == "2" else ("Pipe" if z == "8" else "Posto 3"))
            c.setFont("Helvetica", 6.8)
            c.drawString(30, cp_y, f"• {label}: {pct:.0f}% ({cnt})")
            c.setFillColor(colors.HexColor("#E67E22"))
            c.rect(130, cp_y + 1, max(2, 180 * (pct / 100)), 4, fill=1, stroke=0)
            c.setFillColor(colors.black)
            cp_y -= 10

        # 5. TIPOLOGIA DI COLPO (FORTE vs PALLONETTO/PIAZZATA)
        c.setFillColor(colors.white)
        c.setStrokeColor(colors.HexColor("#BDC3C7"))
        c.rect(410, b_box_y, 400, b_box_h, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#D35400"))
        c.rect(410, b_box_y + b_box_h - 18, 400, 18, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(416, b_box_y + b_box_h - 13, "5. TIPOLOGIA DI COLPO ATTACCANTI (FORTE vs PALLONETTO/PIAZZATA)")

        c.setFont("Helvetica-Bold", 6.4)
        c.setFillColor(colors.HexColor("#7F8C8D"))
        c.drawString(416, b_box_y + b_box_h - 30, "# Nome         Tot   Colpo Forte %   Pallonetto/Piazzata %   Tendenza")
        c.setStrokeColor(colors.HexColor("#BDC3C7"))
        c.line(416, b_box_y + b_box_h - 32, 800, b_box_h - 32)

        sh_y = b_box_y + b_box_h - 43
        sorted_sh = sorted(data["shot_types"].items(), key=lambda x: x[1]["tot"], reverse=True)
        for p_num, sh_info in sorted_sh[:8]:
            if sh_info["tot"] >= 4:
                p_name = data["opp_players"].get(p_num, {}).get("name", "")[:8]
                hard_pct = (sh_info["hard"] / sh_info["tot"] * 100)
                tip_pct = (sh_info["tip"] / sh_info["tot"] * 100)
                tend = "⚠️ Abusa Pallonetto" if tip_pct >= 30 else "Picchia Forte"
                c.setFont("Helvetica", 6.8)
                c.setFillColor(colors.HexColor("#C0392B") if tip_pct >= 30 else colors.black)
                c.drawString(416, sh_y, f"#{p_num} {p_name:<8} {sh_info['tot']:<4}  {hard_pct:>5.0f}%          {tip_pct:>5.0f}%               {tend}")
                sh_y -= 11

        c.showPage()

    c.save()
    buf.seek(0)
    return buf

# ==========================================================
# GENERATORE FOGLIO CARTACEO VERTICALE A4 DA STAMPARE
# ==========================================================
def generate_blank_sheet_pdf():
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    # 1. Header
    c.setFillColor(colors.HexColor("#1A252F"))
    c.rect(0, height - 38, width, 38, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(16, height - 18, "BUSNAGO VOLLEY - FOGLIO RILEVAZIONE TATTICA MANUALE")
    c.setFont("Helvetica", 7.5)
    c.drawString(16, height - 30, "Gara: ____________________ vs ____________________  |  Set: [ 1 ] [ 2 ] [ 3 ] [ 4 ] [ 5 ]  |  Data: __/__/____")

    c.setFont("Helvetica-Bold", 6.5)
    c.setFillColor(colors.HexColor("#27AE60"))
    c.drawString(width - 200, height - 18, "• Verde: Punto (#)")
    c.setFillColor(colors.HexColor("#E74C3C"))
    c.drawString(width - 130, height - 18, "• Rosso: Errore (=)")
    c.setFillColor(colors.HexColor("#F39C12"))
    c.drawString(width - 65, height - 18, "• Gioco/Dif.")

    # 2. I 6 Campi (P1, P6, P5, P4, P3, P2)
    positions = [1, 6, 5, 4, 3, 2]
    box_w, box_h = 278, 144
    coords = [
        (16, height - 188), (302, height - 188),
        (16, height - 338), (302, height - 338),
        (16, height - 488), (302, height - 488)
    ]

    for idx, p in enumerate(positions):
        bx, by = coords[idx]
        c.setStrokeColor(colors.HexColor("#BDC3C7"))
        c.setLineWidth(0.8)
        c.rect(bx, by, box_w, box_h)

        c.setFillColor(colors.HexColor("#2C3E50"))
        c.rect(bx, by + box_h - 14, box_w, 14, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 7.2)
        c.drawString(bx + 6, by + box_h - 10, f"FASE P{p} (P in Z{p})")

        pitch_w, pitch_h = 68, 124
        draw_full_pitch(c, bx + 5, by + 4, pitch_w, pitch_h, [])

        rx = bx + pitch_w + 10
        rw = box_w - pitch_w - 15

        c.setFillColor(colors.HexColor("#34495E"))
        c.rect(rx, by + box_h - 28, rw, 11, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 6.0)
        c.drawString(rx + 4, by + box_h - 25, "BATTITORE: # _____  (Zona: ____)")

        c.setFont("Helvetica-Bold", 6.2)
        c.setFillColor(colors.HexColor("#1A252F"))
        c.drawString(rx, by + box_h - 42, "BASE C -> SPINTA ALZATA:")

        c.setFont("Helvetica", 5.8)
        c.setFillColor(colors.black)
        c.drawString(rx + 2, by + box_h - 53, "• Base K1:  Z4 [ ]  Z2 [ ]  Z3 [ ]  Pipe [ ]")
        c.drawString(rx + 2, by + box_h - 64, "• Base K7:  Z2 [ ]  Z4 [ ]  Z3 [ ]  Pipe [ ]")
        c.drawString(rx + 2, by + box_h - 75, "• Base KC:  Z3 [ ]  Z4 [ ]  Z2 [ ]  Pipe [ ]")

        c.setStrokeColor(colors.HexColor("#ECEFF1"))
        c.line(rx, by + box_h - 80, rx + rw, by + box_h - 80)

        c.setFont("Helvetica-Bold", 6.0)
        c.setFillColor(colors.HexColor("#C0392B"))
        c.drawString(rx, by + box_h - 90, "PALLA SCONTATA/ALTA VA A:")
        c.setFont("Helvetica", 5.8)
        c.setFillColor(colors.black)
        c.drawString(rx + 2, by + box_h - 100, "[ ] Posto 4   [ ] Posto 2   [ ] Pipe")

        c.setFont("Helvetica-Bold", 6.0)
        c.setFillColor(colors.HexColor("#2C3E50"))
        c.drawString(rx, by + box_h - 112, "NOTE MURO / DIFESA:")
        c.setStrokeColor(colors.HexColor("#BDC3C7"))
        c.line(rx, by + box_h - 122, rx + rw, by + box_h - 122)
        c.line(rx, by + box_h - 132, rx + rw, by + box_h - 132)

    # 3. Sezione Inferiore: Modello Prestazione B1
    panel_y, panel_w, panel_h = 16, width - 32, height - 510
    c.setFillColor(colors.HexColor("#F8F9FA"))
    c.rect(16, panel_y, panel_w, panel_h, fill=1, stroke=0)
    c.setStrokeColor(colors.HexColor("#CFD8DC"))
    c.setLineWidth(1)
    c.rect(16, panel_y, panel_w, panel_h, fill=0, stroke=1)

    c.setFillColor(colors.HexColor("#263238"))
    c.rect(16, panel_y + panel_h - 16, panel_w, 16, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(22, panel_y + panel_h - 11, "RILEVAZIONE DATI vs MODELLO DI PRESTAZIONE B1 (2026-27)")

    c_w = (panel_w - 20) / 3.0
    cx1 = 21
    cy1 = panel_y + panel_h - 22

    # Colonna 1: Battuta & Ricezione
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.HexColor("#BDC3C7"))
    c.rect(cx1, cy1 - 70, c_w, 70, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#1B4F72"))
    c.rect(cx1, cy1 - 12, c_w, 12, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 6.2)
    c.drawString(cx1 + 4, cy1 - 9, "BATTUTA (Target: Ace >=6% | Err <=10%)")
    c.setFont("Helvetica", 6.0)
    c.setFillColor(colors.black)
    c.drawString(cx1 + 5, cy1 - 25, "Ace (#):        _______________________")
    c.drawString(cx1 + 5, cy1 - 40, "In Gioco:       _______________________")
    c.drawString(cx1 + 5, cy1 - 55, "Errori (=):     _______________________")

    cy1_rec = cy1 - 76
    c.setFillColor(colors.white)
    c.rect(cx1, cy1_rec - 70, c_w, 70, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#1B4F72"))
    c.rect(cx1, cy1_rec - 12, c_w, 12, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 6.2)
    c.drawString(cx1 + 4, cy1_rec - 9, "RICEZIONE (Target: #+ >=50% | Err <=7%)")
    c.setFont("Helvetica", 6.0)
    c.setFillColor(colors.black)
    c.drawString(cx1 + 5, cy1_rec - 25, "Perfetta/Pos (#+): ___________________")
    c.drawString(cx1 + 5, cy1_rec - 40, "Slash/Neg (!-):     ___________________")
    c.drawString(cx1 + 5, cy1_rec - 55, "Errori (=):          ___________________")

    # Colonna 2: Attacco CP & BP
    cx2 = cx1 + c_w + 5
    c.setFillColor(colors.white)
    c.rect(cx2, cy1 - 70, c_w, 70, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#2C3E50"))
    c.rect(cx2, cy1 - 12, c_w, 12, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 6.2)
    c.drawString(cx2 + 4, cy1 - 9, "ATTACCO CAMBIO PALLA (Target: >=35%)")
    c.setFont("Helvetica", 6.0)
    c.setFillColor(colors.black)
    c.drawString(cx2 + 5, cy1 - 25, "Vincenti (#):   _______________________")
    c.drawString(cx2 + 5, cy1 - 40, "In Gioco (+!-): _______________________")
    c.drawString(cx2 + 5, cy1 - 55, "Errori/Murati:  _______________________")

    c.setFillColor(colors.white)
    c.rect(cx2, cy1_rec - 70, c_w, 70, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#2C3E50"))
    c.rect(cx2, cy1_rec - 12, c_w, 12, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 6.2)
    c.drawString(cx2 + 4, cy1_rec - 9, "ATTACCO CONTRATTACCO (Target: >=30%)")
    c.setFont("Helvetica", 6.0)
    c.setFillColor(colors.black)
    c.drawString(cx2 + 5, cy1_rec - 25, "Vincenti (#):   _______________________")
    c.drawString(cx2 + 5, cy1_rec - 40, "In Gioco (+!-): _______________________")
    c.drawString(cx2 + 5, cy1_rec - 55, "Errori/Murati:  _______________________")

    # Colonna 3: Muro & Target Tattici
    cx3 = cx2 + c_w + 5
    c.setFillColor(colors.white)
    c.rect(cx3, cy1 - 70, c_w, 70, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#16A085"))
    c.rect(cx3, cy1 - 12, c_w, 12, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 6.2)
    c.drawString(cx3 + 4, cy1 - 9, "MURO (Target: Eff >=15% | Falli <=33%)")
    c.setFont("Helvetica", 6.0)
    c.setFillColor(colors.black)
    c.drawString(cx3 + 5, cy1 - 25, "Punti (#):        _____________________")
    c.drawString(cx3 + 5, cy1 - 40, "Tocco/Difesa:     _____________________")
    c.drawString(cx3 + 5, cy1 - 55, "Invasione/Fallo:  _____________________")

    c.setFillColor(colors.white)
    c.rect(cx3, cy1_rec - 70, c_w, 70, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#D35400"))
    c.rect(cx3, cy1_rec - 12, c_w, 12, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 6.2)
    c.drawString(cx3 + 4, cy1_rec - 9, "NOTE RAPIDE TATTICA & TARGET")
    c.setFont("Helvetica", 6.0)
    c.setFillColor(colors.black)
    c.drawString(cx3 + 5, cy1_rec - 25, "Battere su: # _____ (Punto debole)")
    c.drawString(cx3 + 5, cy1_rec - 40, "Attaccante chiave loro: # _____")
    c.drawString(cx3 + 5, cy1_rec - 55, "Palla alta loro va a: [ 4 ] [ 2 ]")

    c.showPage()
    c.save()
    buf.seek(0)
    return buf

# ==========================================================
# INTERFACCIA STREAMLIT
# ==========================================================
def main():
    st.set_page_config(page_title="Volley Scout Dashboard", layout="wide")
    st.sidebar.title("🏐 Scout Dashboard")
    modalita = st.sidebar.radio(
        "Seleziona Funzione:",
        ["🔴 Live Match (Set per Set)", "📊 Studio Pre-Gara (Multi-Gara)"]
    )

    # Pulsante download Foglio Carta/Penna sempre visibile nella sidebar
    st.sidebar.markdown("---")
    st.sidebar.subheader("🖨️ Foglio Carta e Penna (A4)")
    st.sidebar.write("Scarica il template A4 verticale da stampare per la rilevazione manuale.")
    blank_pdf_data = generate_blank_sheet_pdf()
    st.sidebar.download_button(
        label="📄 Scarica Foglio Cartaceo (A4)",
        data=blank_pdf_data,
        file_name="Foglio_Scout_Manuale_Busnago_A4.pdf",
        mime="application/pdf"
    )
    st.sidebar.markdown("---")

    if modalita == "🔴 Live Match (Set per Set)":
        st.title("🏐 Scheda Tattica Grafica Live Click&Scout")
        st.write("Aggiornamento fine set con confronto KPI Modello di Prestazione B1.")

        if "saved_pre_pdf_bytes" not in st.session_state:
            st.session_state["saved_pre_pdf_bytes"] = None
        if "saved_pre_pdf_name" not in st.session_state:
            st.session_state["saved_pre_pdf_name"] = ""

        col_pre, col_scout = st.columns(2)
        with col_pre:
            st.subheader("1. Studio Pre-Gara (Carica 1 volta sola)")
            if st.session_state["saved_pre_pdf_bytes"] is not None:
                st.success(f"✅ Pre-gara memorizzato: **{st.session_state['saved_pre_pdf_name']}**")
                if st.button("🗑️ Rimuovi / Cambia Pre-Gara"):
                    st.session_state["saved_pre_pdf_bytes"] = None
                    st.session_state["saved_pre_pdf_name"] = ""
                    st.rerun()
            else:
                uploaded_pre = st.file_uploader("Carica il PDF del tuo studio pre-gara:", type=["pdf"])
                if uploaded_pre:
                    st.session_state["saved_pre_pdf_bytes"] = uploaded_pre.getvalue()
                    st.session_state["saved_pre_pdf_name"] = uploaded_pre.name
                    st.success(f"✅ Memorizzato per tutti i set: **{uploaded_pre.name}**")
                    st.rerun()

        with col_scout:
            st.subheader("2. Dati Scout Live")
            metodo = st.radio("Modalità inserimento scout:", ["📁 Carica File Scout", "📋 Incolla Testo Scout"], horizontal=True)
            text = None
            if metodo == "📁 Carica File Scout":
                uploaded_file = st.file_uploader("Seleziona il file scout aggiornato:", type=None)
                if uploaded_file: text = uploaded_file.getvalue().decode("utf-8", errors="ignore")
            else:
                raw_text = st.text_area("Incolla qui il contenuto aggiornato di Click&Scout:", height=160)
                if raw_text.strip(): text = raw_text

        if text:
            col_set, _ = st.columns([3, 3])
            with col_set:
                set_choice = st.selectbox("Seleziona il Set:", ["Gara Completa", "Set 1", "Set 2", "Set 3", "Set 4", "Set 5"])
                
            t_set = None
            if set_choice != "Gara Completa":
                match_s = re.search(r"\d+", set_choice)
                if match_s: t_set = int(match_s.group(0))

            scout_data = parse_dvw(text, target_set=t_set)
            if not scout_data:
                st.error("Formato scout non valido.")
                return
                
            st.success(f"Dati elaborati: **{scout_data['teams']['opp']}** vs **{scout_data['teams']['home']}**")

            # SEZIONE KPI VIDEO STREAMLIT: MODELLO PRESTAZIONE B1
            st.markdown("### 🎯 Benchmark Busnago B1 2026-27 vs Rendimento Reale")
            ps = scout_data["phase_stats"]["home"]
            h_cp_val = (ps["cp_kill"] / ps["cp_tot"] * 100) if ps["cp_tot"] > 0 else 0
            
            tot_h_att = sum(scout_data["home_attack"][p]["tot"] for p in scout_data["home_attack"])
            kill_tot_val = (scout_data["skill_points"]["home"]["attack"] / tot_h_att * 100) if tot_h_att > 0 else 0

            tot_h_rec = sum(scout_data["home_reception"][p]["tot"] for p in scout_data["home_reception"])
            pos_rec_val = (sum(scout_data["home_reception"][p]["#"] + scout_data["home_reception"][p]["+"] for p in scout_data["home_reception"]) / tot_h_rec * 100) if tot_h_rec > 0 else 0
            err_rec_val = (sum(scout_data["home_reception"][p]["="] for p in scout_data["home_reception"]) / tot_h_rec * 100) if tot_h_rec > 0 else 0

            tot_h_srv = sum(scout_data["home_srv"][p]["tot"] for p in scout_data["home_srv"])
            ace_srv_val = (scout_data["skill_points"]["home"]["serve"] / tot_h_srv * 100) if tot_h_srv > 0 else 0
            err_srv_val = (scout_data["home_errors"]["serve"] / tot_h_srv * 100) if tot_h_srv > 0 else 0

            c_k1, c_k2, c_k3, c_k4 = st.columns(4)
            c_k1.metric("Attacco CP (Kill)", f"{h_cp_val:.0f}%", f"Target: ≥{BENCHMARK_B1['att_cp']['kill_min']:.0f}%", delta_color="normal")
            c_k2.metric("Attacco Totale", f"{kill_tot_val:.0f}%", f"Target: ≥{BENCHMARK_B1['att_tot']['kill_min']:.0f}%", delta_color="normal")
            c_k3.metric("Ricezione Pos (#+)", f"{pos_rec_val:.0f}%", f"Target: ≥{BENCHMARK_B1['reception']['pos_min']:.0f}%", delta_color="normal")
            c_k4.metric("Errori Battuta", f"{err_srv_val:.0f}%", f"Target: ≤{BENCHMARK_B1['serve']['err_max']:.0f}%", delta_color="inverse")

            live_pdf_buf = generate_pdf(scout_data, set_label=set_choice, is_pre_gara=False)

            if st.session_state["saved_pre_pdf_bytes"] is not None:
                merger = PdfWriter()
                r_pre = PdfReader(io.BytesIO(st.session_state["saved_pre_pdf_bytes"]))
                for page in r_pre.pages: merger.add_page(page)
                r_live = PdfReader(live_pdf_buf)
                for page in r_live.pages: merger.add_page(page)
                out_buf = io.BytesIO()
                merger.write(out_buf)
                out_buf.seek(0)
                final_data = out_buf
                btn_label = f"📄 Scarica Dossier Completo (Pre-Gara + Analisi {set_choice})"
                file_name_out = f"Dossier_Completo_{scout_data['teams']['opp']}_{set_choice.replace(' ', '_')}.pdf"
            else:
                final_data = live_pdf_buf
                btn_label = f"📄 Scarica Scheda Live ({set_choice})"
                file_name_out = f"Scheda_Live_{scout_data['teams']['opp']}_{set_choice.replace(' ', '_')}.pdf"

            st.download_button(label=btn_label, data=final_data, file_name=file_name_out, mime="application/pdf")

    else:
        st.title("📊 Studio Tattico Pre-Gara (Analisi Cumulativa 3–5 Gare)")
        st.write("Analisi approfondita dell'avversario su più gare: Battute, Palleggiatore su Ricezione, Money Time, CP vs BP e Tipologia Colpi.")

        target_opp = st.text_input("Nome squadra avversaria da studiare:", placeholder="Es. Scandicci, Vero Volley...")
        multi_files = st.file_uploader("Carica i file .dvw delle partite precedenti (fino a 5 o più):", accept_multiple_files=True, type=None)

        if multi_files:
            st.info(f"📂 Caricati {len(multi_files)} file scout. Elaborazione in corso...")
            scout_results = []
            for f in multi_files:
                f_text = f.getvalue().decode("utf-8", errors="ignore")
                parsed = parse_dvw(f_text, target_set=None, force_opp_name=target_opp if target_opp.strip() else None)
                if parsed: scout_results.append(parsed)

            if scout_results:
                opp_team_name = target_opp.strip() if target_opp.strip() else scout_results[0]["teams"]["opp"]
                agg_data = aggregate_scouts(scout_results, target_opp_name=opp_team_name)
                tot_attacks = sum(agg_data["rotations"][p]["total_att"] for p in range(1, 7))
                st.success(f"Analisi aggregata per **{opp_team_name}**: {len(scout_results)} partite, {tot_attacks} attacchi totali analizzati.")

                pdf_buf = generate_pdf(agg_data, set_label=f"Studio Pre-Gara ({len(scout_results)} Gare)", is_pre_gara=True)

                st.download_button(
                    label=f"📄 Scarica Dossier Completo a 3 Pagine ({opp_team_name})",
                    data=pdf_buf,
                    file_name=f"Dossier_PreGara_{opp_team_name}_{len(scout_results)}_Gare.pdf",
                    mime="application/pdf"
                )
            else:
                st.error("I file caricati non contengono dati scout validi.")

if __name__ == "__main__":
    main()
