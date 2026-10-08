import io
import math
import re
from collections import defaultdict
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

# ==========================================================
# COORDINATE CAMPO
# ==========================================================
ATTACK_POS = {
    "4": (0.18, 0.90),
    "3": (0.50, 0.90),
    "2": (0.82, 0.90),
    "8": (0.50, 0.60),
    "6": (0.50, 0.60),
}

DEFENSE_POS = {
    "1": (0.80, 0.15),
    "6": (0.50, 0.15),
    "5": (0.20, 0.15),
    "9": (0.80, 0.45),
    "8": (0.50, 0.45),
    "7": (0.20, 0.45),
    "2": (0.80, 0.70),
    "3": (0.50, 0.70),
    "4": (0.20, 0.70),
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
          "serves_received": [],
          "att_dist": defaultdict(int),
          "bases": defaultdict(int),
          "total_att": 0,
      }
      for p in range(1, 7)
  }

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
      if (
          pinfo.get("role") == "5"
          or "P" in pinfo.get("name", "")
          or num == "01"
          or num == "1"
      ):
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

    # Ricezione Avversaria
    if code.startswith("a") and skill == "R":
      reception_stats[player]["tot"] += 1
      if eval_char in reception_stats[player]:
        reception_stats[player][eval_char] += 1

    # Attacco Avversario (SOLO ATTACCO)
    elif code.startswith("a") and skill == "A":
      attack_stats[player]["tot"] += 1
      if eval_char in attack_stats[player]:
        attack_stats[player][eval_char] += 1

      if start_z:
        rotations[p_rot]["total_att"] += 1
        rotations[p_rot]["att_dist"][start_z] += 1
        rotations[p_rot]["attacks"].append((player, start_z, end_z, eval_char))

        p_role = opp_players.get(player, {}).get("role", "")
        if (
            start_z == "3"
            or p_role == "4"
            or "C" in opp_players.get(player, {}).get("name", "")
        ):
          if end_z in ["2", "1"]:
            rotations[p_rot]["bases"]["K7"] += 1
          elif end_z in ["4", "5"]:
            rotations[p_rot]["bases"]["K1"] += 1
          else:
            rotations[p_rot]["bases"]["KC"] += 1

    # Battute Avversarie Ricevute dalla nostra squadra in quella rotazione
    elif code.startswith("a") and skill == "S":
      if end_z:
        rotations[p_rot]["serves_received"].append(
            (player, start_z, end_z, eval_char)
        )

  return {
      "teams": teams,
      "players": opp_players,
      "rotations": rotations,
      "reception": reception_stats,
      "attack": attack_stats,
  }


# ==========================================================
# GRAFICA VETTORIALE FRECCE
# ==========================================================
def draw_arrow(c, x1, y1, x2, y2, color, line_w=1.2):
  c.setStrokeColor(color)
  c.setFillColor(color)
  c.setLineWidth(line_w)
  c.line(x1, y1, x2, y2)

  ang = math.atan2(y2 - y1, x2 - x1)
  alen = 4.5
  awid = math.pi / 6

  p = c.beginPath()
  p.moveTo(x2, y2)
  p.lineTo(x2 - alen * math.cos(ang - awid), y2 - alen * math.sin(ang - awid))
  p.lineTo(x2 - alen * math.cos(ang + awid), y2 - alen * math.sin(ang + awid))
  p.close()
  c.drawPath(p, fill=1, stroke=0)


# ==========================================================
# DISEGNO DEL CAMPO ATTACCO E MINI-CAMPO BATTUTA
# ==========================================================
def draw_attack_pitch(c, x, y, w, h, rot_data):
  # Campo attacco
  c.setFillColor(colors.HexColor("#FEF9E7"))
  c.setStrokeColor(colors.black)
  c.setLineWidth(0.8)
  c.rect(x, y, w, h, fill=1, stroke=1)

  # Rete
  c.setStrokeColor(colors.HexColor("#C0392B"))
  c.setLineWidth(2.2)
  c.line(x, y + h, x + w, y + h)

  # 3 Metri
  c.setStrokeColor(colors.HexColor("#BDC3C7"))
  c.setLineWidth(0.7)
  c.line(x, y + h * 0.67, x + w, y + h * 0.67)

  # Percentuali a rete
  tot = max(1, rot_data["total_att"])
  p4 = rot_data["att_dist"].get("4", 0)
  p3 = rot_data["att_dist"].get("3", 0)
  p2 = rot_data["att_dist"].get("2", 0)

  c.setFillColor(colors.HexColor("#2C3E50"))
  c.rect(x + 1, y + h - 12, 28, 10, fill=1, stroke=0)
  c.rect(x + w / 2 - 14, y + h - 12, 28, 10, fill=1, stroke=0)
  c.rect(x + w - 29, y + h - 12, 28, 10, fill=1, stroke=0)

  c.setFillColor(colors.white)
  c.setFont("Helvetica-Bold", 6)
  c.drawString(x + 3, y + h - 9, f"4:{p4*100//tot}%")
  c.drawString(x + w / 2 - 12, y + h - 9, f"3:{p3*100//tot}%")
  c.drawString(x + w - 27, y + h - 9, f"2:{p2*100//tot}%")

  # Frecce SOLTANTO d'Attacco
  for att in rot_data["attacks"]:
    _, sz, ez, ev = att
    if sz in ATTACK_POS and ez in DEFENSE_POS:
      x1 = x + ATTACK_POS[sz][0] * w
      y1 = y + ATTACK_POS[sz][1] * h
      x2 = x + DEFENSE_POS[ez][0] * w
      y2 = y + DEFENSE_POS[ez][1] * h

      if ev == "#":
        col = colors.HexColor("#27AE60")
        lw = 1.4
      elif ev in ["=", "/"]:
        col = colors.HexColor("#E74C3C")
        lw = 1.4
      else:
        col = colors.HexColor("#2980B9")
        lw = 0.8
      draw_arrow(c, x1, y1, x2, y2, col, line_w=lw)


def draw_serve_box(c, x, y, w, h, serves_list):
  # Mini campetto di ricezione (dove atterra la battuta)
  c.setFillColor(colors.HexColor("#EAEDED"))
  c.setStrokeColor(colors.HexColor("#7F8C8D"))
  c.setLineWidth(0.6)
  c.rect(x, y, w, h, fill=1, stroke=1)

  # Linea 3m
  c.line(x, y + h * 0.33, x + w, y + h * 0.33)
  # Rete mini
  c.setStrokeColor(colors.HexColor("#C0392B"))
  c.setLineWidth(1.5)
  c.line(x, y, x + w, y)

  # Frecce o punti caduta battuta
  c.setFont("Helvetica-Bold", 5.5)
  c.setFillColor(colors.HexColor("#2C3E50"))
  c.drawString(x + 2, y + h - 7, "ARRIVO BATTUTE:")

  counts = defaultdict(int)
  for _, _, ez, _ in serves_list:
    if ez:
      counts[ez] += 1

  # Visualizza conteggio battute per zona sul mini-campo
  zone_coords_mini = {
      "4": (0.20, 0.20),
      "3": (0.50, 0.20),
      "2": (0.80, 0.20),
      "7": (0.20, 0.45),
      "8": (0.50, 0.45),
      "9": (0.80, 0.45),
      "5": (0.20, 0.70),
      "6": (0.50, 0.70),
      "1": (0.80, 0.70),
  }
  for zn, cnt in counts.items():
    if zn in zone_coords_mini:
      zx = x + zone_coords_mini[zn][0] * w
      zy = y + zone_coords_mini[zn][1] * h
      c.setFillColor(colors.HexColor("#8E44AD"))
      c.circle(zx, zy, 4.5, fill=1, stroke=0)
      c.setFillColor(colors.white)
      c.setFont("Helvetica-Bold", 5)
      c.drawCentredString(zx, zy - 1.5, str(cnt))


# ==========================================================
# GENERATORE PDF FINALE (SOLO FILE LIVE)
# ==========================================================
def generate_pdf(data, set_label="Gara"):
  buf = io.BytesIO()
  c = canvas.Canvas(buf, pagesize=landscape(A4))
  width, height = landscape(A4)

  # Testata
  c.setFillColor(colors.HexColor("#1A252F"))
  c.rect(0, height - 34, width, 34, fill=1, stroke=0)
  c.setFillColor(colors.white)
  c.setFont("Helvetica-Bold", 11)
  c.drawString(
      20,
      height - 20,
      f"STUDIO TATTICO LIVE: {data['teams']['opp']} vs {data['teams']['home']}",
  )
  c.setFont("Helvetica", 8)
  c.drawString(
      20,
      height - 30,
      f"Analisi: {set_label}  |  Attacchi Reali divisi dalle Battute  |  Target & Punti Deboli",
  )

  c.setFont("Helvetica-Bold", 7.5)
  c.setFillColor(colors.HexColor("#27AE60"))
  c.drawString(width - 240, height - 20, "▲ Punto (#)")
  c.setFillColor(colors.HexColor("#E74C3C"))
  c.drawString(width - 175, height - 20, "▲ Errore/Murato (=, /)")
  c.setFillColor(colors.HexColor("#2980B9"))
  c.drawString(width - 85, height - 20, "▲ Gioco (+, -)")

  positions = [1, 6, 5, 4, 3, 2]
  coords = [
      (20, height - 262),
      (222, height - 262),
      (424, height - 262),
      (20, height - 500),
      (222, height - 500),
      (424, height - 500),
  ]

  bw, bh = 196, 228
  cw, ch = 104, 134

  for idx, p in enumerate(positions):
    bx, by = coords[idx]
    rot = data["rotations"][p]

    # Bordo box fase
    c.setStrokeColor(colors.HexColor("#BDC3C7"))
    c.setLineWidth(0.8)
    c.rect(bx, by, bw, bh)

    # Titolo Fase
    c.setFillColor(colors.HexColor("#2C3E50"))
    c.rect(bx, by + bh - 16, bw, 16, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(
        bx + 6, by + bh - 12, f"FASE P{p} (P in Z{p}) - {rot['total_att']} Att"
    )

    # 1. CAMPO PRINCIPALE (SOLO ATTACCO)
    cx, cy = bx + 5, by + 8
    draw_attack_pitch(c, cx, cy, cw, ch, rot)

    # 2. MINI CAMPO BATTUTA (SEPARATO)
    sx, sy = bx + cw + 10, by + 8
    sw, sh = bw - cw - 15, 62
    draw_serve_box(c, sx, sy, sw, sh, rot["serves_received"])

    # 3. BASI CENTRALI (IN ALTO A DESTRA)
    dx = bx + cw + 10
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(dx, by + bh - 28, "BASI C1/C2:")
    c.setFont("Helvetica", 6.8)
    c.drawString(dx, by + bh - 39, f"• K1: {rot['bases'].get('K1', 0)}")
    c.drawString(dx, by + bh - 49, f"• KC: {rot['bases'].get('KC', 0)}")
    c.drawString(dx, by + bh - 59, f"• K7: {rot['bases'].get('K7', 0)}")

  # ==========================================================
  # PANNELLO DESTRO: EVIDENZIAZIONI TARGET E GIOCATORI
  # ==========================================================
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

  # --- RICEZIONE ---
  c.setFillColor(colors.black)
  c.setFont("Helvetica-Bold", 7.5)
  c.drawString(px + 8, py + ph - 30, "RICEZIONE AVVERSARIA:")

  rec_sorted = []
  for num, st_r in data["reception"].items():
    if st_r["tot"] > 0:
      pos_pct = (st_r["#"] + st_r["+"]) / st_r["tot"] * 100
      prf_pct = st_r["#"] / st_r["tot"] * 100
      rec_sorted.append((num, st_r["tot"], pos_pct, prf_pct, st_r["="]))
  rec_sorted.sort(key=lambda x: x[2])  # Il più debole (Pos% più bassa) in cima

  c.setFont("Helvetica", 6.5)
  c.drawString(px + 8, py + ph - 42, "#   Nome       Tot  Pos%  Prf%  Err")
  c.line(px + 8, py + ph - 45, px + pw - 8, py + ph - 45)

  ry = py + ph - 56
  for i, r in enumerate(rec_sorted[:5]):
    pname = data["players"].get(r[0], {}).get("name", "")[:9]
    # Evidenziazione: Peggiore in ROSSO (bersaglio), Migliore in VERDE
    if i == 0:
      c.setFillColor(colors.HexColor("#C0392B"))  # BERSAGLIO BATTUTA
      prefix = "🎯 "
    elif i == len(rec_sorted) - 1:
      c.setFillColor(colors.HexColor("#1E8449"))  # SICURO / EVITARE
      prefix = "🛡️ "
    else:
      c.setFillColor(colors.black)
      prefix = ""

    c.drawString(
        px + 8,
        ry,
        f"{prefix}#{r[0]} {pname:<9} {r[1]:<3} {r[2]:.0f}%   {r[3]:.0f}%"
        f"   {r[4]}",
    )
    ry -= 11

  # --- ATTACCO ---
  c.setFillColor(colors.black)
  c.setFont("Helvetica-Bold", 7.5)
  c.drawString(px + 8, ry - 10, "ATTACCO AVVERSARIO:")

  att_sorted = []
  for num, st_a in data["attack"].items():
    if st_a["tot"] > 0:
      eff = ((st_a["#"] - st_a["="] - st_a["/"]) / st_a["tot"]) * 100
      pt_pct = st_a["#"] / st_a["tot"] * 100
      att_sorted.append((num, st_a["tot"], st_a["#"], eff, pt_pct))

  # Ordinamento per volume di palloni giocati
  att_sorted.sort(key=lambda x: x[1], reverse=True)
  max_eff_player = (
      max(att_sorted, key=lambda x: x[3])[0] if att_sorted else None
  )

  c.setFont("Helvetica", 6.5)
  c.drawString(px + 8, ry - 22, "#   Nome       Tot  Pt   Eff%  Pt%")
  c.line(px + 8, ry - 25, px + pw - 8, ry - 25)

  ay = ry - 36
  for i, a in enumerate(att_sorted[:6]):
    pname = data["players"].get(a[0], {}).get("name", "")[:9]

    # Evidenziazione: Più servito in ARANCIONE, Più efficace in ROSSO
    if i == 0:
      c.setFillColor(colors.HexColor("#D35400"))  # PIÙ SERVITO
      prefix = "🔥 "
    elif a[0] == max_eff_player and a[1] >= 3:
      c.setFillColor(colors.HexColor("#922B21"))  # PIÙ PERICOLOSO/EFFICACE
      prefix = "⚡ "
    else:
      c.setFillColor(colors.black)
      prefix = ""

    c.drawString(
        px + 8,
        ay,
        f"{prefix}#{a[0]} {pname:<9} {a[1]:<3} {a[2]:<3} {a[3]:.0f}% "
        f" {a[4]:.0f}%",
    )
    ay -= 11

  # --- BOX INDICAZIONI CHIAVE DA PANCHINA ---
  c.setFillColor(colors.HexColor("#EAEDED"))
  c.rect(px + 6, py + 10, pw - 12, ay - py + 5, fill=1, stroke=0)

  c.setFillColor(colors.HexColor("#1A252F"))
  c.setFont("Helvetica-Bold", 7.5)
  c.drawString(px + 10, ay - 6, "DECISIONI TATTICHE:")

  c.setFont("Helvetica", 6.8)
  c.setFillColor(colors.black)
  if rec_sorted:
    c.drawString(
        px + 10,
        ay - 18,
        f"• Battuta su: #{rec_sorted[0][0]} ({rec_sorted[0][2]:.0f}% Pos)",
    )
    c.drawString(
        px + 10,
        ay - 28,
        f"• Evita battuta su: #{rec_sorted[-1][0]} ({rec_sorted[-1][2]:.0f}%)",
    )
  if att_sorted:
    c.drawString(
        px + 10,
        ay - 39,
        f"• Muro/Difesa Focus: #{att_sorted[0][0]} ({att_sorted[0][1]} attacchi)",
    )
    if max_eff_player:
      c.drawString(
          px + 10,
          ay - 49,
          f"• Attaccante Pericoloso: #{max_eff_player} (Alta Eff%)",
      )

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
  st.write(
      "Carica il file `.dvw` a fine set per generare la scheda tattica con i 6"
      " campi d'attacco, mini-box battuta e target evidenziati."
  )

  dvw_file = st.file_uploader(
      "Trascina qui il file .dvw di Click&Scout:", type=["dvw"]
  )

  if dvw_file:
    text = dvw_file.getvalue().decode("utf-8", errors="ignore")

    col_set, _ = st.columns([3, 3])
    with col_set:
      set_choice = st.selectbox(
          "Seleziona il Set da analizzare:",
          ["Gara Completa", "Set 1", "Set 2", "Set 3", "Set 4", "Set 5"],
      )

    t_set = None
    if set_choice != "Gara Completa":
      match_s = re.search(r"\d+", set_choice)
      if match_s:
        t_set = int(match_s.group(0))

    scout_data = parse_dvw(text, target_set=t_set)

    if not scout_data:
      st.error("Formato file scout non valido o vuoto.")
      return

    st.success(
        f"Dati elaborati: **{scout_data['teams']['opp']}** vs"
        f" **{scout_data['teams']['home']}**"
    )

    pdf_buffer = generate_pdf(scout_data, set_label=set_choice)

    st.download_button(
        label="📄 Scarica Scheda Tattica Grafica (PDF)",
        data=pdf_buffer,
        file_name=(
            f"Scheda_Tattica_{scout_data['teams']['opp']}_{set_choice.replace(' ', '_')}.pdf"
        ),
        mime="application/pdf",
    )


if __name__ == "__main__":
  main()
