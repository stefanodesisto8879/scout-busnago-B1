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
            "serves": defaultdict(int),
            "att_dist": defaultdict(int),
            "bases": defaultdict(int),
            "total_att": 0,
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

        # RICEZIONE
        if skill == "R":
            reception_stats[player]["tot"] += 1
            if eval_char in reception_stats[player]:
                reception_stats[player][eval_char] += 1

        # ATTACCO
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

        # BATTUTA
        elif skill == "S":
            if start_z and end_z:
                rotations[p_rot]["serves"][f"#{player} Z{start_z}»Z{end_z}"] += 1

    return {
        "teams": teams,
        "players": opp_players,
        "rotations": rotations,
        "reception": reception_stats,
        "attack": attack_stats,
    }

# ==========================================================
# GRAFICA VETTORIALE CAMPO & FRECCE
# ==========================================================
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
    c.rect(x + w / 2 - 15, y + h - 13, 30, 11, fill=1, stroke=0)
    c.rect(x + w - 32, y + h - 13, 30, 11, fill=1, stroke=0)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawString(x + 4, y + h - 10, f"4:{p4*100//tot}%")
    c.drawString(x + w / 2 - 13, y + h - 10, f"3:{p3*100//tot}%")
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

            draw_arrow(c, x1, y1, x2, y2, col, line_w=lw)

# ==========================================================
# GENERATORE PDF
# ==========================================================
def generate_pdf(data, set_label="Gara"):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4))
    width, height = landscape(A4)

    c.setFillColor(colors.HexColor("#1A252F"))
    c.rect(0, height - 36, width, 36, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20, height - 22, f"STUDIO GARA LIVE: {data['teams']['opp']} vs {data['teams']['home']}")
    c.setFont("Helvetica", 8)
    c.drawString(20, height - 32, f"Set: {set_label}  |  Distribuzione Palleggiatore, Traiettorie d'Attacco e Basi Centrale")

    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(colors.HexColor("#27AE60"))
    c.drawString(width - 230, height - 22, "▲ Punto (#)")
    c.setFillColor(colors.HexColor("#E74C3C"))
    c.drawString(width - 165, height - 22, "▲ Errore/Murato (=, /)")
    c.setFillColor(colors.HexColor("#2980B9"))
    c.drawString(width - 75, height - 22, "▲ Gioco (+, -)")

    positions = [1, 6, 5, 4, 3, 2]
    coords = [
        (20, height - 260),
        (220, height - 260),
        (420, height - 260),
        (20, height - 495),
        (220, height - 495),
        (420, height - 495),
    ]

    bw, bh = 192, 225
    cw, ch = 105, 130

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
        c.drawString(bx + 6, by + bh - 12, f"FASE P{p} (P in Z{p}) - {rot['total_att']} Att")

        cx, cy = bx + 6, by + 10
        draw_pitch(c, cx, cy, cw, ch, rot)

        dx = bx + cw + 10
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 7)
        c.drawString(dx, by + bh - 30, "BASI C1/C2:")
        c.setFont("Helvetica", 7)
        c.drawString(dx, by + bh - 42, f"• K1: {rot['bases'].get('K1', 0)}")
        c.drawString(dx, by + bh - 52, f"• KC: {rot['bases'].get('KC', 0)}")
        c.drawString(dx, by + bh - 62, f"• K7: {rot['bases'].get('K7', 0)}")

        c.setFont("Helvetica-Bold", 7)
        c.drawString(dx, by + bh - 80, "BATTUTE RICEVUTE:")
        c.setFont("Helvetica", 6.5)
        if rot["serves"]:
            sy = by + bh - 90
            for s_str, cnt in sorted(rot["serves"].items(), key=lambda x: x[1], reverse=True)[:3]:
                c.drawString(dx, sy, f"• {s_str} ({cnt})")
                sy -= 9
        else:
            c.drawString(dx, by + bh - 90, "• Nessuna")

    sx = 620
    sy = height - 495
    sw = width - sx - 15
    sh = 460

    c.setStrokeColor(colors.HexColor("#2C3E50"))
    c.rect(sx, sy, sw, sh)
    c.setFillColor(colors.HexColor("#2C3E50"))
    c.rect(sx, sy + sh - 18, sw, 18, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(sx + 8, sy + sh - 13, "ANALISI GIOCATORI AVVERSARI")

    # Ricezione
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(sx + 8, sy + sh - 30, "RICEZIONE:")
    rec_sorted = []
    for num, st_r in data["reception"].items():
        if st_r["tot"] > 0:
            pos_pct = (st_r["#"] + st_r["+"]) / st_r["tot"] * 100
            prf_pct = st_r["#"] / st_r["tot"] * 100
            rec_sorted.append((num, st_r["tot"], pos_pct, prf_pct, st_r["="]))
    rec_sorted.sort(key=lambda x: x[2])

    c.setFont("Helvetica", 6.5)
    c.drawString(sx + 8, sy + sh - 42, "#   Nome       Tot  Pos%  Prf%  Err")
    c.line(sx + 8, sy + sh - 45, sx + sw - 8, sy + sh - 45)
    ry = sy + sh - 55
    for r in rec_sorted[:5]:
        pname = data["players"].get(r[0], {}).get("name", "")[:9]
        c.drawString(sx + 8, ry, f"#{r[0]} {pname:<10} {r[1]:<3} {r[2]:.0f}%   {r[3]:.0f}%   {r[4]}")
        ry -= 10

    # Attacco
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(sx + 8, ry - 10, "ATTACCO:")
    att_sorted = []
    for num, st_a in data["attack"].items():
        if st_a["tot"] > 0:
            eff = ((st_a["#"] - st_a["="] - st_a["/"]) / st_a["tot"]) * 100
            pt_pct = st_a["#"] / st_a["tot"] * 100
            att_sorted.append((num, st_a["tot"], st_a["#"], eff, pt_pct))
    att_sorted.sort(key=lambda x: x[1], reverse=True)

    c.setFont("Helvetica", 6.5)
    c.drawString(sx + 8, ry - 22, "#   Nome       Tot  Pt   Eff%  Pt%")
    c.line(sx + 8, ry - 25, sx + sw - 8, ry - 25)
    ay = ry - 35
    for a in att_sorted[:6]:
        pname = data["players"].get(a[0], {}).get("name", "")[:9]
        c.drawString(sx + 8, ay, f"#{a[0]} {pname:<10} {a[1]:<3} {a[2]:<3} {a[3]:.0f}%  {a[4]:.0f}%")
        ay -= 10

    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(sx + 8, ay - 10, "NOTE CHIAVE:")
    c.setFont("Helvetica", 6.5)
    if rec_sorted:
        c.drawString(sx + 8, ay - 22, f"• Target Battuta: #{rec_sorted[0][0]} ({rec_sorted[0][2]:.0f}%)")
    if att_sorted:
        c.drawString(sx + 8, ay - 32, f"• Più Servito: #{att_sorted[0][0]} ({att_sorted[0][1]} att)")
        eff_max = max(att_sorted, key=lambda x: x[3])
        c.drawString(sx + 8, ay - 42, f"• Più Efficace: #{eff_max[0]} ({eff_max[3]:.0f}% eff)")

    c.showPage()
    c.save()
    buf.seek(0)
    return buf

# ==========================================================
# INTERFACCIA STREAMLIT
# ==========================================================
def main():
    st.set_page_config(page_title="Volley Scout Dashboard", layout="wide")
    st.title("🏐 Elaboratore Tattico Click&Scout")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("1. Piano Pre-Gara (PDF)")
        pre_pdf = st.file_uploader("Carica lo studio preparato prima della gara:", type=["pdf"])
    with col2:
        st.subheader("2. File Scout (.dvw)")
        dvw_file = st.file_uploader("Trascina qui il file .dvw di Click&Scout:", type=["dvw"])

    if dvw_file:
        text = dvw_file.getvalue().decode("utf-8", errors="ignore")

        c_set, _ = st.columns([2, 4])
        with c_set:
            set_choice = st.selectbox(
                "Seleziona il Set:",
                ["Gara Completa", "Set 1", "Set 2", "Set 3", "Set 4", "Set 5"]
            )

        t_set = None
        if set_choice != "Gara Completa":
            match_s = re.search(r"\d+", set_choice)
            if match_s:
                t_set = int(match_s.group(0))

        scout_data = parse_dvw(text, target_set=t_set)

        if not scout_data:
            st.error("Formato scout non valido.")
            return

        st.success(f"Caricato: **{scout_data['teams']['opp']}** vs **{scout_data['teams']['home']}**")
        live_pdf = generate_pdf(scout_data, set_label=set_choice)

        if pre_pdf:
            merger = PdfWriter()
            r_pre = PdfReader(pre_pdf)
            for page in r_pre.pages:
                merger.add_page(page)
            r_live = PdfReader(live_pdf)
            for page in r_live.pages:
                merger.add_page(page)
            out = io.BytesIO()
            merger.write(out)
            out.seek(0)
            btn_data = out
            btn_txt = "📄 Scarica Dossier Completo (Pre-Gara + Dati Live)"
        else:
            btn_data = live_pdf
            btn_txt = "📄 Scarica Scheda Tattica Grafica Live"

        st.download_button(
            label=btn_txt,
            data=btn_data,
            file_name=f"Studio_Gara_{set_choice.replace(' ', '_')}.pdf",
            mime="application/pdf"
        )

if __name__ == "__main__":
    main()
