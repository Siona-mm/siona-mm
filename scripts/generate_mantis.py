import datetime
import json
import os
import urllib.request
from pathlib import Path

# ------------------------------------------------------------------
# DYNAMIC ANIMATED SVG ORCHID MANTIS + GITHUB CONTRIBUTION MATRIX
# Walks from smallest-commit squares to biggest-commit squares!
# ------------------------------------------------------------------

OUTPUT_SVG = Path("mantis.svg")

COLS = 36          # Visible weeks (set to 52 for full year)
ROWS = 7           # Sunday -> Saturday
CELL_SIZE = 14
CELL_GAP = 4
PITCH = CELL_SIZE + CELL_GAP
PAD_X = 36
PAD_Y = 44

GREEN_LEVELS = {
    0: "rgba(130, 140, 155, 0.22)",
    1: "#9be9a8",
    2: "#40c463",
    3: "#30a14e",
    4: "#216e39",
}

PINK_LEVELS = {
    1: "#ffb8de",
    2: "#ff8ac8",
    3: "#f55eb0",
    4: "#d93892",
}


def fetch_github_contributions(username: str, token: str):
    """Fetch real contribution counts and levels via GitHub GraphQL API."""
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
            "User-Agent": "orchid-mantis-svg",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    weeks = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    recent_weeks = weeks[-COLS:]
    num_cols = len(recent_weeks)

    level_map = {
        "NONE": 0,
        "FIRST_QUARTILE": 1,
        "SECOND_QUARTILE": 2,
        "THIRD_QUARTILE": 3,
        "FOURTH_QUARTILE": 4,
    }

    grid_levels = [[0] * num_cols for _ in range(ROWS)]
    grid_counts = [[0] * num_cols for _ in range(ROWS)]

    today_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    commits_today = 0

    for c, week in enumerate(recent_weeks):
        for r, day in enumerate(week["contributionDays"]):
            if r < ROWS:
                cnt = int(day["contributionCount"])
                lvl = level_map.get(day["contributionLevel"], 0)
                grid_counts[r][c] = cnt
                grid_levels[r][c] = lvl
                if day["date"] == today_str:
                    commits_today = cnt

    if commits_today == 0 and recent_weeks and recent_weeks[-1]["contributionDays"]:
        commits_today = int(recent_weeks[-1]["contributionDays"][-1]["contributionCount"])

    return grid_levels, grid_counts, commits_today


def build_mantis_svg(grid_levels, grid_counts, commits_today: int) -> str:
    cols = len(grid_levels[0])
    rows = len(grid_levels)
    width = PAD_X * 2 + cols * PITCH - CELL_GAP
    height = PAD_Y + rows * PITCH - CELL_GAP + 14

    if commits_today == 0:
        mood = "sad"
        step_dt = 0.11
        collect_pause = 0.16
    elif commits_today <= 3:
        mood = "slow"
        step_dt = 0.085
        collect_pause = 0.13
    else:
        mood = "glow"
        step_dt = 0.065
        collect_pause = 0.10

    # 1. Group active squares by exact commit count and sort SMALLEST -> BIGGEST
    by_count = {}
    for c in range(cols):
        for r in range(rows):
            cnt = grid_counts[r][c]
            if cnt > 0:
                by_count.setdefault(cnt, []).append((c, r))

    ordered_targets = []
    if by_count:
        smallest_cnt = min(by_count.keys())
        cur_c, cur_r = by_count[smallest_cnt][0]
        for cnt in sorted(by_count.keys()):
            remaining = list(by_count[cnt])
            while remaining:
                remaining.sort(key=lambda pos: abs(pos[0] - cur_c) + abs(pos[1] - cur_r))
                nxt = remaining.pop(0)
                ordered_targets.append((cnt, nxt[0], nxt[1]))
                cur_c, cur_r = nxt

    # 2. Route orthogonal path from smallest commit square to biggest commit square
    waypoints = []
    eat_times = {}
    t_now = 0.0

    if ordered_targets:
        _, sc, sr = ordered_targets[0]
        waypoints.append((sc, sr, t_now))
        eat_times[(sc, sr)] = t_now
        t_now += collect_pause
        cur_c, cur_r = sc, sr

        for _, tc, tr in ordered_targets[1:]:
            while cur_c != tc:
                cur_c += 1 if tc > cur_c else -1
                is_t = (cur_c == tc and cur_r == tr)
                waypoints.append((cur_c, cur_r, t_now))
                t_now += collect_pause if is_t else step_dt
            while cur_r != tr:
                cur_r += 1 if tr > cur_r else -1
                is_t = (cur_c == tc and cur_r == tr)
                waypoints.append((cur_c, cur_r, t_now))
                t_now += collect_pause if is_t else step_dt
            if (tc, tr) not in eat_times:
                eat_times[(tc, tr)] = waypoints[-1][2]
    else:
        waypoints.append((0, 3, 0.0))
        t_now = 2.0

    total_dur = max(2.0, t_now + 1.2)

    pos_times, pos_vals = [], []
    flip_times, flip_vals = [], []
    last_dir = 1

    for idx, (wc, wr, wt) in enumerate(waypoints):
        kt = min(1.0, wt / total_dur)
        px = PAD_X + wc * PITCH + CELL_SIZE / 2.0
        py = PAD_Y + wr * PITCH + CELL_SIZE / 2.0 + 3.0
        pos_times.append(f"{kt:.5f}")
        pos_vals.append(f"{px:.1f},{py:.1f}")

        if idx + 1 < len(waypoints):
            nc = waypoints[idx + 1][0]
            if nc > wc:
                last_dir = 1
            elif nc < wc:
                last_dir = -1
        flip_times.append(f"{kt:.5f}")
        flip_vals.append(f"{last_dir},1")

    if pos_times[-1] != "1.00000":
        pos_times.append("1.00000")
        pos_vals.append(pos_vals[-1])
        flip_times.append("1.00000")
        flip_vals.append(flip_vals[-1])

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
        "<defs>",
        '  <filter id="orchidGlow" x="-40%" y="-40%" width="180%" height="180%">',
        '    <feGaussianBlur stdDeviation="2.4" result="blur"/>',
        '    <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>',
        "  </filter>",
        "</defs>",
        '<g id="matrix">',
    ]

    for r in range(rows):
        for c in range(cols):
            x0 = PAD_X + c * PITCH
            y0 = PAD_Y + r * PITCH
            lvl = grid_levels[r][c]
            cnt = grid_counts[r][c]
            green_col = GREEN_LEVELS[lvl]

            if (c, r) in eat_times and lvl > 0:
                pink_col = PINK_LEVELS[lvl]
                kt_eat = max(0.0001, min(0.9999, eat_times[(c, r)] / total_dur))
                parts.append(
                    f'  <rect x="{x0}" y="{y0}" width="{CELL_SIZE}" height="{CELL_SIZE}" rx="3" fill="{green_col}">'
                    f'<title>{cnt} commit{"s" if cnt != 1 else ""}</title>'
                    f'<animate attributeName="fill" values="{green_col};{pink_col};{pink_col}" '
                    f'keyTimes="0;{kt_eat:.5f};1" dur="{total_dur:.2f}s" calcMode="discrete" repeatCount="indefinite"/>'
                    f"</rect>"
                )
            else:
                parts.append(
                    f'  <rect x="{x0}" y="{y0}" width="{CELL_SIZE}" height="{CELL_SIZE}" rx="3" fill="{green_col}">'
                    f'<title>{cnt} commits</title></rect>'
                )
    parts.append("</g>")

    glow_attr = ' filter="url(#orchidGlow)"' if mood == "glow" else ""
    sad_style = ' style="filter: saturate(0.35) brightness(0.92);"' if mood == "sad" else ""
    bob_dur = "0.52s" if mood == "glow" else ("0.75s" if mood == "slow" else "1.1s")
    leg_dur = "0.44s" if mood == "glow" else ("0.65s" if mood == "slow" else "0.95s")
    wing_dur = "1.4s" if mood == "glow" else ("2.1s" if mood == "slow" else "3.0s")
    ring_col = "#ff4da6" if mood != "sad" else "#789be1"

    parts.append(f'<g id="mantis-mover"{glow_attr}{sad_style}>')
    parts.append(
        f'  <animateTransform attributeName="transform" type="translate" '
        f'values="{";".join(pos_vals)}" keyTimes="{";".join(pos_times)}" '
        f'dur="{total_dur:.2f}s" repeatCount="indefinite"/>'
    )
    parts.append(
        f'  <rect x="-9" y="-12" width="18" height="18" rx="4" fill="none" stroke="{ring_col}" stroke-width="2">'
        f'<animate attributeName="opacity" values="0.95;0.45;0.95" dur="1.1s" repeatCount="indefinite"/>'
        f"</rect>"
    )
    parts.append('  <g id="mantis-flip">')
    parts.append(
        f'    <animateTransform attributeName="transform" type="scale" '
        f'values="{";".join(flip_vals)}" keyTimes="{";".join(flip_times)}" '
        f'dur="{total_dur:.2f}s" calcMode="discrete" repeatCount="indefinite"/>'
    )
    parts.append('    <g transform="scale(1.8)" shape-rendering="crispEdges">')
    parts.append('      <ellipse cx="0" cy="0" rx="14" ry="2" fill="rgba(63,36,59,0.45)"/>')

    # Back 2-bend walking legs
    parts.append('      <g id="back-legs">')
    parts.append(f'        <animateTransform attributeName="transform" type="translate" values="0,0; -1.2,-1.4; 0,0; 1.2,0; 0,0" dur="{leg_dur}" repeatCount="indefinite"/>')
    parts.append('        <polyline points="2,-9 5,-3 11,-11 13,0 15,0" fill="none" stroke="#763a60" stroke-width="3.2" stroke-linejoin="miter"/>')
    parts.append('        <polyline points="2,-9 5,-3 11,-11 13,0 15,0" fill="none" stroke="#f4b2ca" stroke-width="1.4" stroke-linejoin="miter"/>')
    parts.append('        <polyline points="-2,-9 -4,-3 -10,-12 -12,0 -14,0" fill="none" stroke="#763a60" stroke-width="3.2" stroke-linejoin="miter"/>')
    parts.append('        <polyline points="-2,-9 -4,-3 -10,-12 -12,0 -14,0" fill="none" stroke="#f4b2ca" stroke-width="1.4" stroke-linejoin="miter"/>')
    parts.append("      </g>")

    # Body bob group
    parts.append('      <g id="body-bob">')
    parts.append(f'        <animateTransform attributeName="transform" type="translate" values="0,0; 0,-1.2; 0,0" dur="{bob_dur}" repeatCount="indefinite"/>')
    parts.append('        <ellipse cx="-7" cy="-9" rx="6" ry="3.2" fill="#9a6c96" stroke="#763a60" stroke-width="1.2"/>')
    parts.append('        <ellipse cx="-7" cy="-9.5" rx="5" ry="2.2" fill="#c092b8"/>')

    # Orchid-petal wings
    parts.append('        <g id="orchid-wings">')
    parts.append(f'          <animateTransform attributeName="transform" type="rotate" values="0 -2 -10; -7 -2 -10; 2 -2 -10; -5 -2 -10; 0 -2 -10" dur="{wing_dur}" repeatCount="indefinite"/>')
    parts.append('          <polygon points="-2,-10 -15,-12 -10,-7" fill="#e080ac" stroke="#763a60" stroke-width="1.1"/>')
    parts.append('          <polygon points="-2,-10 -14,-16 -8,-10" fill="#f4b2ca" stroke="#763a60" stroke-width="1.1"/>')
    parts.append('          <polygon points="-2,-10 -11,-19 -5,-11" fill="#f5ced8" stroke="#763a60" stroke-width="1.1"/>')
    parts.append('          <polygon points="-2,-10 -7,-20 -3,-12" fill="#faece8" stroke="#763a60" stroke-width="1.1"/>')
    parts.append("        </g>")

    # Prothorax
    parts.append('        <polygon points="1,-17 3,-17 1,-9 -2,-9" fill="#faece8" stroke="#763a60" stroke-width="1.2"/>')
    parts.append('        <ellipse cx="0" cy="-9.5" rx="3.2" ry="2.2" fill="#f5ced8" stroke="#763a60" stroke-width="1.1"/>')

    # Foreground 2-bend zig-zag walking legs
    parts.append('        <g id="front-legs">')
    parts.append(f'          <animateTransform attributeName="transform" type="translate" values="0,0; 1.3,-1.5; 0,0; -1.3,0; 0,0" dur="{leg_dur}" repeatCount="indefinite"/>')
    parts.append('          <polyline points="0,-8 -2,-2.5 -8,-10.5 -10.5,0 -12.5,0" fill="none" stroke="#763a60" stroke-width="3.4" stroke-linejoin="miter"/>')
    parts.append('          <polyline points="0,-8 -2,-2.5 -8,-10.5 -10.5,0 -12.5,0" fill="none" stroke="#faece8" stroke-width="1.6" stroke-linejoin="miter"/>')
    parts.append('          <line x1="-10.5" y1="0" x2="-12.5" y2="0" stroke="#e080ac" stroke-width="1.6"/>')
    parts.append('          <polyline points="-3,-8 -7,-2.5 -16,-15 -18,0 -20,0" fill="none" stroke="#763a60" stroke-width="3.4" stroke-linejoin="miter"/>')
    parts.append('          <polyline points="-3,-8 -7,-2.5 -16,-15 -18,0 -20,0" fill="none" stroke="#faece8" stroke-width="1.6" stroke-linejoin="miter"/>')
    parts.append('          <line x1="-18" y1="0" x2="-20" y2="0" stroke="#e080ac" stroke-width="1.6"/>')
    parts.append("        </g>")

    # Folded 2-bend raptorial claws
    parts.append('        <g id="raptorial-claws">')
    parts.append(f'          <animateTransform attributeName="transform" type="rotate" values="0 2 -14; 6 2 -14; 0 2 -14" dur="{bob_dur}" repeatCount="indefinite"/>')
    parts.append('          <polyline points="2,-14 4,-9 8,-14 8.5,-9" fill="none" stroke="#763a60" stroke-width="3.2" stroke-linejoin="miter"/>')
    parts.append('          <polyline points="2,-14 4,-9 8,-14" fill="none" stroke="#f5ced8" stroke-width="1.5" stroke-linejoin="miter"/>')
    parts.append('          <line x1="8" y1="-14" x2="8.5" y2="-9" stroke="#e080ac" stroke-width="1.5"/>')
    parts.append("        </g>")

    # Head, compound eyes & dual antennae
    parts.append('        <g id="head-group">')
    parts.append(f'          <animateTransform attributeName="transform" type="rotate" values="-4 2 -17; 6 2 -17; -4 2 -17" dur="{wing_dur}" repeatCount="indefinite"/>')
    parts.append('          <polygon points="2.5,-21 2.5,-25 4,-22" fill="#f5ced8" stroke="#763a60" stroke-width="1"/>')
    parts.append('          <polygon points="1,-20 -1,-23 2,-21" fill="#f4b2ca" stroke="#763a60" stroke-width="1"/>')
    parts.append('          <polygon points="0,-20 3,-22 6,-20 4.5,-16.5 2.5,-15.5 0.5,-16.5" fill="#faece8" stroke="#763a60" stroke-width="1.1"/>')
    parts.append('          <ellipse cx="0.6" cy="-19.2" rx="1.4" ry="1.8" fill="#c4669a" stroke="#763a60" stroke-width="0.9"/>')
    parts.append('          <rect x="0.3" y="-20" width="0.8" height="0.8" fill="#fdf6f8"/>')
    parts.append('          <ellipse cx="5.2" cy="-19.2" rx="1.5" ry="1.8" fill="#c4669a" stroke="#763a60" stroke-width="0.9"/>')
    parts.append('          <rect x="5.0" y="-20" width="0.8" height="0.8" fill="#fdf6f8"/>')
    parts.append('          <g id="antennae">')
    parts.append(f'            <animateTransform attributeName="transform" type="rotate" values="-5 3 -22; 7 3 -22; -5 3 -22" dur="0.9s" repeatCount="indefinite"/>')
    parts.append('            <path d="M 2.2,-21.5 Q -1,-27 -6,-25" fill="none" stroke="#b6588a" stroke-width="1.1"/>')
    parts.append('            <circle cx="-6" cy="-25" r="0.8" fill="#e080ac"/>')
    parts.append('            <path d="M 3.8,-21.5 Q 7,-27 12,-24.5" fill="none" stroke="#b6588a" stroke-width="1.1"/>')
    parts.append('            <circle cx="12" cy="-24.5" r="0.8" fill="#e080ac"/>')
    parts.append("          </g>")
    if mood == "sad":
        parts.append('          <circle cx="5.6" cy="-17" r="0.9" fill="#69beff"><animate attributeName="cy" values="-17;-11" dur="1.1s" repeatCount="indefinite"/></circle>')
    parts.append("        </g>")

    parts.append("      </g>")
    parts.append("    </g>")
    parts.append("  </g>")
    parts.append("</g>")
    parts.append("</svg>")

    return "\n".join(parts)


def main():
    username = os.getenv("GITHUB_REPOSITORY_OWNER", "")
    token = os.getenv("GITHUB_TOKEN", "")

    if username and token:
        grid_levels, grid_counts, commits_today = fetch_github_contributions(username, token)
    else:
        grid_levels = [[0] * COLS for _ in range(ROWS)]
        grid_counts = [[0] * COLS for _ in range(ROWS)]
        grid_levels[3][2], grid_counts[3][2] = 1, 1
        grid_levels[2][8], grid_counts[2][8] = 3, 5
        commits_today = 5

    svg_output = build_mantis_svg(grid_levels, grid_counts, commits_today)
    OUTPUT_SVG.write_text(svg_output, encoding="utf-8")
    print(f"Saved {OUTPUT_SVG} (commits_today={commits_today})")


if __name__ == "__main__":
    main()
