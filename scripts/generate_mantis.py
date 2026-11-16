import datetime
import json
import math
import os
import random
import urllib.request
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUTPUT_GIF = Path("mantis-matrix.gif")

COLS = 36          # Visible weeks in matrix (set to 52 for a full year)
ROWS = 7           # 7 days (Sunday -> Saturday)
CELL_SIZE = 16
CELL_GAP = 4
PAD_X = 44
PAD_Y = 48
SPRITE_SCALE = 2   # Crisp 2x integer pixel scaling

PALETTE = {
    "outline": (118, 58, 96, 255),      # Deep orchid-plum 1px outline
    "dark_plum": (63, 36, 59, 255),     # Ground shadow / deep accent
    "eye_deep": (135, 62, 108, 255),    # Compound eye shadow
    "eye_mid": (196, 102, 154, 255),    # Compound eye midtone
    "eye_bright": (236, 156, 198, 255), # Compound eye highlight
    "white": (253, 246, 248, 255),      # Specular catchlight
    "pearl": (250, 236, 232, 255),      # Creamy pearl-white body/petal
    "blush": (245, 206, 216, 255),      # Soft pastel blush
    "sakura": (244, 178, 202, 255),     # Mid sakura pink
    "rose": (224, 128, 172, 255),       # Rich rose pink tips
    "ant_stem": (182, 88, 138, 255),    # Crisp antenna stem
    "lavender": (192, 146, 184, 255),   # Lavender abdomen shading
    "lav_dark": (154, 108, 150, 255),   # Deep lavender shadow
    "tear": (105, 190, 255, 245),       # Sad teardrop
    "tear_hi": (210, 242, 255, 245),
}


def fetch_github_contributions(username: str, token: str):
    """Fetch real contribution matrix levels and today's commit count via GraphQL."""
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            weeks {
              contributionDays {
                date
                contributionCount
                contributionLevel
              }
            }
          }
        }
      }
    }
    """
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"login": username}}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "orchid-mantis-matrix",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    weeks = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    recent_weeks = weeks[-COLS:]

    level_map = {
        "NONE": 0,
        "FIRST_QUARTILE": 1,
        "SECOND_QUARTILE": 2,
        "THIRD_QUARTILE": 3,
        "FOURTH_QUARTILE": 4,
    }

    grid = np.zeros((ROWS, len(recent_weeks)), dtype=int)
    today_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    commits_today = 0

    for c, week in enumerate(recent_weeks):
        for r, day in enumerate(week["contributionDays"]):
            if r < ROWS:
                grid[r, c] = level_map.get(day["contributionLevel"], 0)
                if day["date"] == today_str:
                    commits_today = int(day["contributionCount"])

    if commits_today == 0 and recent_weeks and recent_weeks[-1]["contributionDays"]:
        commits_today = int(recent_weeks[-1]["contributionDays"][-1]["contributionCount"])

    return grid, commits_today


def add_pixel_outline(layer: np.ndarray, outline_rgba=PALETTE["outline"]) -> np.ndarray:
    """Add a crisp 1-pixel 4-connected outline around opaque pixels in an RGBA grid."""
    alpha = layer[:, :, 3] > 0
    if not np.any(alpha):
        return layer
    up = np.pad(alpha[1:, :], ((0, 1), (0, 0)))
    dn = np.pad(alpha[:-1, :], ((1, 0), (0, 0)))
    lt = np.pad(alpha[:, 1:], ((0, 0), (0, 1)))
    rt = np.pad(alpha[:, :-1], ((0, 0), (1, 0)))
    border = (up | dn | lt | rt) & (~alpha)
    out = layer.copy()
    out[border] = outline_rgba
    return out


def draw_bezier_pixels(draw: ImageDraw.ImageDraw, pts, color, tip_color=None):
    """Rasterize a smooth quadratic/cubic Bezier curve as crisp integer pixels."""
    steps = 36
    coords = []
    for i in range(steps + 1):
        t = i / steps
        if len(pts) == 3:
            p0, p1, p2 = pts
            x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0]
            y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1]
        else:
            p0, p1, p2, p3 = pts
            x = (
                (1 - t) ** 3 * p0[0]
                + 3 * (1 - t) ** 2 * t * p1[0]
                + 3 * (1 - t) * t ** 2 * p2[0]
                + t ** 3 * p3[0]
            )
            y = (
                (1 - t) ** 3 * p0[1]
                + 3 * (1 - t) ** 2 * t * p1[1]
                + 3 * (1 - t) * t ** 2 * p2[1]
                + t ** 3 * p3[1]
            )
        ix, iy = int(round(x)), int(round(y))
        if not coords or (ix, iy) != coords[-1]:
            coords.append((ix, iy))

    n = len(coords)
    for idx, (ix, iy) in enumerate(coords):
        col = tip_color if (tip_color is not None and idx > n * 0.72) else color
        draw.point((ix, iy), fill=col)


def draw_double_bend_mantis_leg(
    draw: ImageDraw.ImageDraw,
    hip: tuple,
    coxa_bend: tuple,
    knee_peak: tuple,
    ankle: tuple,
    toe: tuple,
    is_front: bool = True,
):
    """Draw a 2-bend zig-zag mantis leg: hip -> low coxa dip -> high knee -> ankle -> toe."""
    coxa_col = PALETTE["blush"] if is_front else PALETTE["sakura"]
    femur_col = PALETTE["pearl"] if is_front else PALETTE["blush"]
    tibia_col = PALETTE["blush"] if is_front else PALETTE["sakura"]
    tarsus_col = PALETTE["rose"]

    draw.line([hip, coxa_bend], fill=coxa_col, width=1)
    draw.line([coxa_bend, knee_peak], fill=femur_col, width=2 if is_front else 1)
    draw.line([knee_peak, ankle], fill=tibia_col, width=1)
    draw.line([ankle, toe], fill=tarsus_col, width=1)


def draw_orchid_petal(
    draw: ImageDraw.ImageDraw,
    base: tuple,
    tip: tuple,
    width_px: float,
    base_col=PALETTE["pearl"],
    mid_col=PALETTE["blush"],
    tip_col=PALETTE["sakura"],
):
    """Draw a pointed, multi-shaded orchid petal polygon from base to tip."""
    bx, by = base
    tx, ty = tip
    vx, vy = tx - bx, ty - by
    length = math.hypot(vx, vy)
    if length < 1e-3:
        return
    px, py = -vy / length, vx / length

    p_base = (bx, by)
    p_left_mid = (bx + vx * 0.45 + px * width_px, by + vy * 0.45 + py * width_px)
    p_left_tip = (bx + vx * 0.78 + px * width_px * 0.55, by + vy * 0.78 + py * width_px * 0.55)
    p_tip = (tx, ty)
    p_right_tip = (bx + vx * 0.78 - px * width_px * 0.55, by + vy * 0.78 - py * width_px * 0.55)
    p_right_mid = (bx + vx * 0.45 - px * width_px, by + vy * 0.45 - py * width_px)

    poly = [
        (round(x), round(y))
        for x, y in [p_base, p_left_mid, p_left_tip, p_tip, p_right_tip, p_right_mid]
    ]
    draw.polygon(poly, fill=tip_col)

    inner_mid = [
        (round(bx + (x - bx) * 0.78), round(by + (y - by) * 0.78))
        for x, y in [p_base, p_left_mid, p_tip, p_right_mid]
    ]
    draw.polygon(inner_mid, fill=mid_col)

    inner_core = [
        (round(bx + (x - bx) * 0.52), round(by + (y - by) * 0.52))
        for x, y in [p_base, p_left_mid, p_tip, p_right_mid]
    ]
    draw.polygon(inner_core, fill=base_col)


def draw_petite_orchid_mantis(
    t_sec: float,
    mood: str = "glow",
    facing_right: bool = True,
    scale: int = SPRITE_SCALE,
) -> Image.Image:
    """Draw the petite 16-bit Orchid Mantis with 2-bend zig-zag legs & independent animations."""
    GW, GH = 44, 32
    GROUND_Y = 29.0

    speed = 0.55 if mood == "sad" else (1.35 if mood == "glow" else 0.95)
    w_walk = 2.0 * math.pi * 1.25 * speed

    walk_phase = t_sec * w_walk
    body_bob = -abs(math.sin(walk_phase)) * (0.35 if mood == "sad" else 0.65)
    body_sway = math.sin(walk_phase) * (0.2 if mood == "sad" else 0.45)

    wing_breath = math.sin(t_sec * 3.0 * speed)
    flutter_burst = (
        math.sin(t_sec * 21.0) * max(0.0, math.sin(t_sec * 2.2)) ** 5
        if mood != "sad"
        else 0.0
    )
    wing_lift = (
        -1.0
        if mood == "sad"
        else (0.65 + 0.75 * wing_breath + 1.1 * flutter_burst + (0.5 if mood == "glow" else 0.0))
    )
    wing_spread = (
        -0.6
        if mood == "sad"
        else (0.4 + 0.65 * wing_breath + 0.9 * flutter_burst + (0.45 if mood == "glow" else 0.0))
    )

    head_rot_deg = (
        -8.5 + 1.2 * math.sin(t_sec * 1.4)
        if mood == "sad"
        else math.sin(t_sec * 2.5 * speed + 0.5) * 7.5 + math.sin(t_sec * 1.1) * 3.0
    )
    head_nod = (
        -0.8 + 0.2 * math.sin(t_sec * 1.5)
        if mood == "sad"
        else math.sin(t_sec * 3.4 * speed + 0.8) * 0.7
    )
    head_tilt_x = -0.35 if mood == "sad" else math.cos(t_sec * 2.2 * speed) * 0.6
    eye_look_x = 0 if mood == "sad" else int(round(math.sin(t_sec * 1.8) * 0.6))
    eye_look_y = 1 if mood == "sad" else int(round(math.cos(t_sec * 2.3) * 0.4))

    ant_wave_l = math.sin(t_sec * 4.5 * speed) * 2.0 + math.sin(t_sec * 10.5 * speed) * 0.55
    ant_wave_r = math.cos(t_sec * 3.9 * speed + 1.1) * 2.2 + math.cos(t_sec * 9.2 * speed) * 0.55
    ant_droop = 2.6 if mood == "sad" else (-0.6 * wing_breath)

    cx = 17.5 + body_sway
    cy = 19.5 + body_bob

    # LAYER 0: Ground shadow
    shadow_img = Image.new("RGBA", (GW, GH), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow_img)
    sh_expand = int(round(abs(math.sin(walk_phase)) * 0.8))
    s_draw.ellipse([6 - sh_expand, 28, 37 + sh_expand, 30], fill=(63, 36, 59, 140))

    # LAYER 1: Back 2-bend walking legs
    back_legs_img = Image.new("RGBA", (GW, GH), (0, 0, 0, 0))
    bl_draw = ImageDraw.Draw(back_legs_img)
    for hip_off, coxa_rel, knee_rel, ankle_x, toe_dx, stride_amp, p_off in [
        ((0.0, 1.5), (-1.2, 5.2), (-6.8, -1.8), -8.2, -2.0, 2.2, math.pi),
        ((3.5, 1.5), (1.5, 5.2), (7.5, -2.2), 9.5, 2.0, 2.4, 0.0),
    ]:
        ph = walk_phase + p_off
        amp_scale = 0.45 if mood == "sad" else 1.0
        step_x = math.sin(ph) * stride_amp * amp_scale
        lift_y = -max(0.0, math.cos(ph)) * (0.75 if mood == "sad" else 1.8)

        hx, hy = cx + hip_off[0], cy + hip_off[1]
        bx = hx + coxa_rel[0] + step_x * 0.25
        by = hy + coxa_rel[1] + lift_y * 0.35
        kx = hx + knee_rel[0] + step_x * 0.6
        ky = hy + knee_rel[1] + lift_y * 0.75
        ax = cx + ankle_x + step_x
        ay = GROUND_Y + lift_y
        tx = ax + toe_dx
        ty = ay

        draw_double_bend_mantis_leg(
            bl_draw,
            (round(hx), round(hy)),
            (round(bx), round(by)),
            (round(kx), round(ky)),
            (round(ax), round(ay)),
            (round(tx), round(ty)),
            is_front=False,
        )
    back_legs_arr = add_pixel_outline(np.array(back_legs_img))

    # LAYER 2: Orchid-petal wings & abdomen
    wings_img = Image.new("RGBA", (GW, GH), (0, 0, 0, 0))
    w_draw = ImageDraw.Draw(wings_img)
    abd_x = cx + 2.5
    abd_y = cy - 0.5 - wing_lift * 0.22

    w_draw.ellipse([round(abd_x - 1), round(abd_y + 0.5), round(abd_x + 12.0), round(abd_y + 6.5)], fill=PALETTE["lav_dark"])
    w_draw.ellipse([round(abd_x), round(abd_y), round(abd_x + 11.0), round(abd_y + 5.2)], fill=PALETTE["lavender"])
    for seg_dx in (2.5, 5.5, 8.2):
        w_draw.arc([round(abd_x + seg_dx - 1), round(abd_y + 0.5), round(abd_x + seg_dx + 1.5), round(abd_y + 5)], start=250, end=100, fill=PALETTE["lav_dark"], width=1)

    petals_spec = [
        (12.2 + wing_spread * 0.55, -1.8 - wing_lift * 0.4, 2.4, PALETTE["blush"], PALETTE["sakura"], PALETTE["rose"]),
        (10.8 + wing_spread * 0.42, -4.8 - wing_lift * 0.65, 2.7, PALETTE["pearl"], PALETTE["blush"], PALETTE["sakura"]),
        (8.2 + wing_spread * 0.25, -7.2 - wing_lift * 0.85, 2.6, PALETTE["pearl"], PALETTE["blush"], PALETTE["rose"]),
        (5.5 + wing_spread * 0.10, -8.2 - wing_lift * 0.72, 2.2, PALETTE["pearl"], PALETTE["pearl"], PALETTE["sakura"]),
    ]
    for dx_t, dy_t, pw, c_base, c_mid, c_tip in petals_spec:
        draw_orchid_petal(
            w_draw,
            base=(abd_x + 0.5, abd_y + 1.5),
            tip=(abd_x + dx_t, abd_y + dy_t),
            width_px=pw,
            base_col=c_base,
            mid_col=c_mid,
            tip_col=c_tip,
        )
    wings_arr = add_pixel_outline(np.array(wings_img))

    # LAYER 3: Prothorax & foreground 2-bend zig-zag walking legs
    thorax_img = Image.new("RGBA", (GW, GH), (0, 0, 0, 0))
    t_draw = ImageDraw.Draw(thorax_img)
    neck_x = cx - 2.2 + head_tilt_x * 0.3
    neck_y = cy - 6.2 + head_nod * 0.2

    t_draw.polygon(
        [
            (round(neck_x - 1.2), round(neck_y)),
            (round(neck_x + 1.2), round(neck_y)),
            (round(cx + 1.5), round(cy + 1)),
            (round(cx - 1.2), round(cy + 1.2)),
        ],
        fill=PALETTE["pearl"],
    )
    t_draw.ellipse([round(cx - 1.5), round(cy - 0.8), round(cx + 4.0), round(cy + 3.2)], fill=PALETTE["blush"])
    t_draw.ellipse([round(cx - 1.0), round(cy), round(cx + 2.8), round(cy + 2.5)], fill=PALETTE["pearl"])

    for hip_off, coxa_rel, knee_rel, ankle_x, toe_dx, stride_amp, p_off in [
        ((0.8, 1.8), (2.2, 5.5), (8.2, -1.6), 11.4, 2.0, 2.4, 0.0),
        ((3.2, 1.8), (5.5, 5.5), (16.5, -5.2), 19.2, 2.2, 2.6, math.pi),
    ]:
        ph = walk_phase + p_off
        amp_scale = 0.45 if mood == "sad" else 1.0
        step_x = math.sin(ph) * stride_amp * amp_scale
        lift_y = -max(0.0, math.cos(ph)) * (0.85 if mood == "sad" else 2.0)

        hx, hy = cx + hip_off[0], cy + hip_off[1]
        bx = hx + coxa_rel[0] + step_x * 0.25
        by = hy + coxa_rel[1] + lift_y * 0.35
        kx = hx + knee_rel[0] + step_x * 0.6
        ky = hy + knee_rel[1] + lift_y * 0.75
        ax = cx + ankle_x + step_x
        ay = GROUND_Y + lift_y
        tx = ax + toe_dx
        ty = ay

        draw_double_bend_mantis_leg(
            t_draw,
            (round(hx), round(hy)),
            (round(bx), round(by)),
            (round(kx), round(ky)),
            (round(ax), round(ay)),
            (round(tx), round(ty)),
            is_front=True,
        )
    thorax_arr = add_pixel_outline(np.array(thorax_img))

    # LAYER 4: Folded 2-bend raptorial forelegs
    claws_img = Image.new("RGBA", (GW, GH), (0, 0, 0, 0))
    c_draw = ImageDraw.Draw(claws_img)
    claw_sway_x = math.sin(walk_phase + 0.6) * (0.25 if mood == "sad" else 0.6)
    claw_sway_y = math.cos(walk_phase + 0.6) * (0.3 if mood == "sad" else 0.55) + (0.6 if mood == "sad" else 0.0)
    shoulder_x = neck_x - 0.5
    shoulder_y = neck_y + 2.0

    for c_off_x, c_off_y in [(-2.2, 0.2), (0.2, 0.6)]:
        low_elbow_x = shoulder_x - 1.5 + c_off_x + claw_sway_x * 0.5
        low_elbow_y = shoulder_y + 5.2 + c_off_y + claw_sway_y * 0.5
        high_wrist_x = low_elbow_x - 3.6 + claw_sway_x
        high_wrist_y = low_elbow_y - 4.2 + claw_sway_y
        blade_tip_x = high_wrist_x - 0.5
        blade_tip_y = high_wrist_y + 4.8

        c_draw.line([(round(shoulder_x + c_off_x * 0.4), round(shoulder_y)), (round(low_elbow_x), round(low_elbow_y))], fill=PALETTE["blush"], width=1)
        draw_orchid_petal(
            c_draw,
            base=(low_elbow_x, low_elbow_y),
            tip=(high_wrist_x, high_wrist_y),
            width_px=1.4,
            base_col=PALETTE["pearl"],
            mid_col=PALETTE["blush"],
            tip_col=PALETTE["sakura"],
        )
        draw_bezier_pixels(
            c_draw,
            [(high_wrist_x, high_wrist_y), (high_wrist_x - 1.0, high_wrist_y + 2.4), (blade_tip_x, blade_tip_y)],
            color=PALETTE["rose"],
        )
    claws_arr = add_pixel_outline(np.array(claws_img))

    # LAYER 5: Rotating head & compound eyes
    raw_head = Image.new("RGBA", (GW, GH), (0, 0, 0, 0))
    h_draw = ImageDraw.Draw(raw_head)
    hx = neck_x - 0.8 + head_tilt_x
    hy = neck_y - 2.6 + head_nod

    draw_orchid_petal(h_draw, base=(hx, hy - 1.2), tip=(hx - 0.2, hy - 4.8), width_px=1.4, base_col=PALETTE["pearl"], mid_col=PALETTE["pearl"], tip_col=PALETTE["blush"])
    draw_orchid_petal(h_draw, base=(hx - 1.1, hy - 0.8), tip=(hx - 3.2, hy - 3.4), width_px=1.1, base_col=PALETTE["pearl"], mid_col=PALETTE["blush"], tip_col=PALETTE["sakura"])
    draw_orchid_petal(h_draw, base=(hx + 1.1, hy - 0.8), tip=(hx + 3.0, hy - 3.4), width_px=1.1, base_col=PALETTE["pearl"], mid_col=PALETTE["blush"], tip_col=PALETTE["sakura"])

    face_poly = [
        (round(hx - 3.2), round(hy - 1.2)),
        (round(hx), round(hy - 2.8)),
        (round(hx + 3.2), round(hy - 1.2)),
        (round(hx + 1.6), round(hy + 2.4)),
        (round(hx - 0.4), round(hy + 3.3)),
        (round(hx - 2.8), round(hy + 1.6)),
    ]
    h_draw.polygon(face_poly, fill=PALETTE["pearl"])

    lx0, ly0 = round(hx - 4.0), round(hy - 2.4)
    h_draw.ellipse([lx0, ly0, lx0 + 2.5, ly0 + 3.2], fill=PALETTE["eye_deep"])
    h_draw.ellipse([lx0, ly0, lx0 + 1.8, ly0 + 2.4], fill=PALETTE["eye_mid"])
    h_draw.point((lx0 + max(0, eye_look_x), ly0 + max(0, eye_look_y)), fill=PALETTE["white"])

    rx0, ry0 = round(hx + 1.2), round(hy - 2.4)
    h_draw.ellipse([rx0, ry0, rx0 + 2.8, ry0 + 3.2], fill=PALETTE["eye_deep"])
    h_draw.ellipse([rx0 + 0.4, ry0, rx0 + 2.8, ry0 + 2.4], fill=PALETTE["eye_mid"])
    h_draw.point((rx0 + 1 + eye_look_x, ry0 + eye_look_y), fill=PALETTE["white"])

    if mood == "sad":
        h_draw.rectangle([lx0, ly0, lx0 + 2, ly0 + 1], fill=PALETTE["blush"])
        h_draw.rectangle([rx0, ry0, rx0 + 3, ry0 + 1], fill=PALETTE["blush"])

    rot_head = raw_head.rotate(head_rot_deg, resample=Image.Resampling.NEAREST, center=(round(neck_x), round(neck_y)))
    head_arr = add_pixel_outline(np.array(rot_head))

    # LAYER 6: Dual antennae anchored to rotated crown
    ant_img = Image.new("RGBA", (GW, GH), (0, 0, 0, 0))
    a_draw = ImageDraw.Draw(ant_img)

    rad = math.radians(-head_rot_deg)
    rel_cx = hx - neck_x
    rel_cy = (hy - 2.8) - neck_y
    crown_x = neck_x + rel_cx * math.cos(rad) - rel_cy * math.sin(rad)
    crown_y = neck_y + rel_cx * math.sin(rad) + rel_cy * math.cos(rad)

    ant_l_pts = [
        (crown_x - 0.8, crown_y),
        (crown_x - 2.6 + ant_wave_l * 0.45, crown_y - 5.2 + ant_droop * 0.4),
        (crown_x - 6.8 + ant_wave_l * 0.85, crown_y - 6.8 + ant_droop * 0.8),
        (crown_x - 10.2 + ant_wave_l, crown_y - 4.4 + ant_droop),
    ]
    draw_bezier_pixels(a_draw, ant_l_pts, color=PALETTE["ant_stem"], tip_color=PALETTE["rose"])
    a_draw.point((round(ant_l_pts[-1][0]), round(ant_l_pts[-1][1])), fill=PALETTE["sakura"])

    ant_r_pts = [
        (crown_x + 0.8, crown_y),
        (crown_x + 3.0 + ant_wave_r * 0.45, crown_y - 4.8 + ant_droop * 0.4),
        (crown_x + 7.6 + ant_wave_r * 0.85, crown_y - 6.0 + ant_droop * 0.8),
        (crown_x + 11.0 + ant_wave_r, crown_y - 3.4 + ant_droop),
    ]
    draw_bezier_pixels(a_draw, ant_r_pts, color=PALETTE["ant_stem"], tip_color=PALETTE["rose"])
    a_draw.point((round(ant_r_pts[-1][0]), round(ant_r_pts[-1][1])), fill=PALETTE["sakura"])

    if mood == "sad":
        tear_prog = (t_sec * 1.4) % 1.0
        tx = round(hx - 3.2)
        ty = round(hy + 1.2 + tear_prog * 6.0)
        a_draw.point((tx, ty), fill=PALETTE["tear"])
        a_draw.point((tx, ty - 1), fill=PALETTE["tear_hi"])

    ant_arr = np.array(ant_img)

    sprite = shadow_img.copy()
    for layer_arr in (back_legs_arr, wings_arr, thorax_arr, claws_arr, head_arr, ant_arr):
        layer_pil = Image.fromarray(layer_arr, "RGBA")
        sprite.paste(layer_pil, (0, 0), layer_pil)

    s_arr = np.array(sprite, dtype=np.float32)
    alpha_mask = s_arr[:, :, 3] > 0
    if mood == "sad":
        rgb = s_arr[:, :, :3]
        gray = rgb.mean(axis=2, keepdims=True)
        rgb = rgb * 0.35 + gray * 0.65
        rgb[:, :, 0] *= 0.88
        rgb[:, :, 1] *= 0.88
        rgb[:, :, 2] *= 0.98
        s_arr[:, :, :3] = np.where(alpha_mask[..., None], np.clip(rgb, 0, 255), 0)
    elif mood == "glow":
        rgb = np.clip(s_arr[:, :, :3] * 1.06 + 8, 0, 255)
        s_arr[:, :, :3] = np.where(alpha_mask[..., None], rgb, 0)

    sprite = Image.fromarray(s_arr.astype(np.uint8), "RGBA")
    sprite = sprite.resize((GW * scale, GH * scale), Image.Resampling.NEAREST)

    pad = 10
    full = Image.new("RGBA", (sprite.width + pad * 2, sprite.height + pad * 2), (0, 0, 0, 0))

    if mood == "glow":
        pulse = 0.75 + 0.25 * math.sin(t_sec * 6.0)
        a_ch = sprite.getchannel("A")
        outer = Image.new("RGBA", sprite.size, (255, 110, 195, 0))
        outer.putalpha(a_ch.filter(ImageFilter.GaussianBlur(3.2)).point(lambda a: int(min(255, a * 0.85 * pulse))))
        inner = Image.new("RGBA", sprite.size, (255, 225, 245, 0))
        inner.putalpha(a_ch.filter(ImageFilter.GaussianBlur(1.4)).point(lambda a: int(min(255, a * 0.95 * pulse))))
        full.paste(outer, (pad, pad), outer)
        full.paste(inner, (pad, pad), inner)

    full.paste(sprite, (pad, pad), sprite)

    if mood != "sad":
        p_draw = ImageDraw.Draw(full)
        bx = pad + int(round(36 * scale + math.cos(t_sec * 2.1) * 1.8))
        by = pad + int(round(10 * scale + math.sin(t_sec * 2.6) * 2.0))
        for pdx, pdy in [(0, -2), (2, -1), (1, 2), (-1, 2), (-2, -1)]:
            p_draw.point((bx + pdx, by + pdy), fill=PALETTE["sakura"])
        p_draw.point((bx, by), fill=PALETTE["rose"])

        twinkle = math.sin(t_sec * 5.0)
        if twinkle > -0.1:
            arm = 2 if twinkle > 0.5 else 1
            sx = pad + int(6 * scale)
            sy = pad + int(14 * scale + math.cos(t_sec * 2.2) * 1.2)
            p_draw.line([(sx - arm, sy), (sx + arm, sy)], fill=PALETTE["blush"], width=1)
            p_draw.line([(sx, sy - arm), (sx, sy + arm)], fill=PALETTE["blush"], width=1)
            p_draw.point((sx, sy), fill=PALETTE["white"])

    if facing_right:
        full = full.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

    return full


def rgba_to_clean_transparent_gif_frame(canvas: Image.Image) -> Image.Image:
    """Convert RGBA canvas to a crisp 255-color paletted GIF frame with clean index-255 transparency."""
    alpha = np.array(canvas.getchannel("A"))
    opaque = alpha > 110
    bg = Image.new("RGBA", canvas.size, (255, 255, 255, 255))
    comp = Image.alpha_composite(bg, canvas).convert("RGB")
    q = comp.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    q_arr = np.array(q)
    q_arr[~opaque] = 255
    out = Image.fromarray(q_arr, mode="P")
    raw_pal = q.getpalette() or []
    if len(raw_pal) < 255 * 3:
        raw_pal = raw_pal + [255] * (255 * 3 - len(raw_pal))
    pal = raw_pal[: 255 * 3] + [255, 255, 255]
    out.putpalette(pal)
    out.info["transparency"] = 255
    return out


def generate_random_matrix_path(cols: int, rows: int, steps: int = 24):
    """Pick a fresh random walk across the matrix cells on every run."""
    c = random.randint(1, max(1, cols // 4))
    r = random.randint(1, rows - 2)
    path = [(c, r)]
    visited = {(c, r)}
    directions = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 0), (1, 0)]

    for _ in range(steps - 1):
        neighbors = []
        for dc, dr in directions:
            nc, nr = c + dc, r + dr
            if 0 <= nc < cols and 0 <= nr < rows:
                if len(path) >= 2 and (nc, nr) == path[-2]:
                    continue
                weight = 4 if (nc, nr) not in visited else 1
                neighbors.extend([(nc, nr)] * weight)
        if not neighbors:
            for dc, dr in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nc, nr = c + dc, r + dr
                if 0 <= nc < cols and 0 <= nr < rows:
                    neighbors.append((nc, nr))
        c, r = random.choice(neighbors)
        path.append((c, r))
        visited.add((c, r))

    return path


def main():
    username = os.getenv("GITHUB_REPOSITORY_OWNER", "")
    token = os.getenv("GITHUB_TOKEN", "")

    if username and token:
        grid_levels, commits_today = fetch_github_contributions(username, token)
    else:
        grid_levels = np.random.choice([0, 0, 1, 2, 3, 4], size=(ROWS, COLS))
        commits_today = int(os.getenv("TEST_COMMITS", "6"))

    if commits_today == 0:
        mood, frame_duration_ms, substeps_per_cell = "sad", 90, 5
    elif commits_today <= 3:
        mood, frame_duration_ms, substeps_per_cell = "slow", 70, 5
    else:
        mood, frame_duration_ms, substeps_per_cell = "glow", 45, 4

    cols = grid_levels.shape[1]
    pitch = CELL_SIZE + CELL_GAP
    width = PAD_X * 2 + cols * pitch - CELL_GAP
    height = PAD_Y + ROWS * pitch - CELL_GAP + 14

    base_colors = {
        0: (130, 140, 155, 55),
        1: (155, 233, 168, 190),
        2: (64, 196, 99, 210),
        3: (48, 161, 78, 225),
        4: (33, 110, 57, 240),
    }
    trail_color = (255, 130, 195, 220) if mood == "glow" else (215, 155, 190, 175)

    path = generate_random_matrix_path(cols, ROWS, steps=24)
    visited_cells = set()
    frames = []
    facing_right = True
    t_sec = 0.0
    dt = frame_duration_ms / 1000.0

    for idx in range(len(path) - 1):
        c0, r0 = path[idx]
        c1, r1 = path[idx + 1]
        visited_cells.add((c0, r0))

        if c1 > c0:
            facing_right = True
        elif c1 < c0:
            facing_right = False

        for s in range(substeps_per_cell):
            smooth_t = 0.5 - 0.5 * math.cos(math.pi * (s / substeps_per_cell))
            fc = c0 + (c1 - c0) * smooth_t
            fr = r0 + (r1 - r0) * smooth_t

            active_c = int(round(fc))
            active_r = int(round(fr))

            canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(canvas)

            for r in range(ROWS):
                for c in range(cols):
                    x0 = PAD_X + c * pitch
                    y0 = PAD_Y + r * pitch
                    fill = trail_color if (c, r) in visited_cells else base_colors[grid_levels[r, c]]
                    draw.rounded_rectangle([x0, y0, x0 + CELL_SIZE, y0 + CELL_SIZE], radius=3, fill=fill)

                    if c == active_c and r == active_r:
                        ring_col = (255, 70, 165, 255) if mood != "sad" else (120, 155, 225, 255)
                        draw.rounded_rectangle(
                            [x0 - 2, y0 - 2, x0 + CELL_SIZE + 2, y0 + CELL_SIZE + 2],
                            radius=4,
                            outline=ring_col,
                            width=2,
                        )

            sprite = draw_petite_orchid_mantis(t_sec=t_sec, mood=mood, facing_right=facing_right, scale=SPRITE_SCALE)
            sw, sh = sprite.size
            cx_px = PAD_X + fc * pitch + CELL_SIZE // 2
            cy_px = PAD_Y + fr * pitch + CELL_SIZE // 2 + 3
            foot_y_in_sprite = int(29 * SPRITE_SCALE + 10)
            canvas.paste(sprite, (int(round(cx_px - sw // 2)), int(round(cy_px - foot_y_in_sprite))), sprite)

            frames.append(rgba_to_clean_transparent_gif_frame(canvas))
            t_sec += dt

    frames[0].save(
        OUTPUT_GIF,
        save_all=True,
        append_images=frames[1:],
        duration=frame_duration_ms,
        loop=0,
        disposal=2,
        transparency=255,
    )
    print(f"Saved {OUTPUT_GIF} (commits_today={commits_today}, mood={mood})")


if __name__ == "__main__":
    main()
