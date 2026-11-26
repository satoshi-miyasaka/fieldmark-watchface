#!/usr/bin/env python3
"""Generates the FIELDMARK watch face (Watch Face Format v2).

A field watch for camping and fishing, drawn to save battery on OLED: a black
dial, thin print, outline hands with a lume strip, a seconds hand that steps
once a second (or is switched off), and a separate always-on layout.

    python3 tools/generate_fieldmark.py

Outputs:
    watchface/src/main/res/raw/watchface.xml
    watchface/src/main/res/drawable-nodpi/*.png

Two modes, chosen in the watch face editor:
    camp: wind (left), sunrise/sunset (right), current weather (bottom)
    fish: moon age and tide name (left), wind (right), tide graph (bottom)

Both modes show the next 12 hours of rain and snow between the hour markers:
the hour the hour hand is in is now, and each segment clockwise is one hour
later. Weather, the hourly forecast and the moon come from Wear OS itself.
Wind, sunrise/sunset and the tide come from the FIELDMARK companion app on
the watch (wear/), which reads Open-Meteo, through four fixed complication
slots. Keep the slot ids and their order once people use the face: the watch
remembers each slot's data source by its position.
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "watchface" / "src" / "main" / "res"
DRAWABLE = RES / "drawable-nodpi"

SIZE = 450
C = SIZE / 2
FULL = f'x="0" y="0" width="{SIZE}" height="{SIZE}"'
COMPANION = "io.github.satoshimiyasaka.fieldmark/io.github.satoshimiyasaka.fieldmark."

# Colours (ARGB). The dial stays black so the OLED leaves it off.
LUME = "FFD9D0A4"  # hour markers, hand strips
EDGE = "FFA39D8B"  # hand outlines, brand
TEXT = "FFCFC8B4"  # readings
MUTED = "FF8A8574"  # small labels
DIM = "FF6F6B5F"  # minute ticks, date window
RING = "FF4A4740"  # sub-dial rims
TRACK = "FF2C2A26"  # sun track, tide grid
RAIN = "FF6FA3CF"
SNOW = "FFDFE7EC"
MOON_LIT = "FFCFC6A4"
ACCENT = {"camp": "FFE0782F", "fish": "FFE3A446"}
# Always-on: one dim grey, rain and snow a little darker.
AMB = "FF8A8574"
AMB_RAIN = "FF5D86A8"
AMB_SNOW = "FF8A96A0"
AMB_MOON = "FF6F6B5F"

MODES = ("camp", "fish")
FONT = "barlow_medium"
FONT_BOLD = "barlow_semibold"
SYSTEM_FONT = "SYNC_TO_DEVICE"  # for Japanese text

# Layout (face pixels).
MINUTE_TICK_R = 213
HOUR_MARK_R = 190  # centre of the hour markers and of the forecast marks
HOUR_MARK_LEN = 14
SUB_R = 56
LEFT = (117.0, 205.0)
RIGHT = (333.0, 205.0)
BOTTOM = (225.0, 335.0)
BOTTOM_R = 52
SUB_LABEL_Y = 270  # top of the reading under each side sub-dial
TIDE_BOX = (157, 281, 136, 96)  # x, y, w, h
TIDE_GRAPH = (165, 293, 120, 38)  # where the companion's tide image goes
FORECAST_HOURS = 12
MARK = 18  # forecast mark size
AOD_DOT_R = 192

DOW = ("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT")

# Weather conditions (WEATHER.*.CONDITION, 0-15) as forecast marks.
# 0 unknown, 1 clear, 2 cloudy, 3 fog, 4 heavy rain, 5 heavy snow, 6 rain,
# 7 snow, 8 sunny, 9 thunderstorm, 10 sleet, 11 light snow, 12 light rain,
# 13 mist, 14 partly cloudy, 15 windy. Plain rain and snow count as light:
# only heavy rain, thunderstorms and heavy snow get the strong marks.
FORECAST_MARKS = (
    ("dry", (1, 2, 3, 8, 13, 14, 15)),
    ("rain_l", (6, 12)),
    ("rain_h", (4, 9)),
    ("snow_l", (7, 11)),
    ("snow_h", (5,)),
    ("sleet", (10,)),
)
# The current weather icon in camp mode.
WEATHER_ICONS = (
    ("sun", (1, 8, 14)),
    ("cloud", (2, 3, 13, 15)),
    ("rain", (4, 6, 12)),
    ("snow", (5, 7, 10, 11)),
    ("storm", (9,)),
)

# Tide names by moon age (whole days, 0-29), the usual Japanese table.
TIDE_NAMES = ("大潮", "大潮", "大潮", "中潮", "中潮", "中潮", "中潮", "小潮", "小潮", "小潮",
              "長潮", "若潮", "中潮", "中潮", "大潮", "大潮", "大潮", "大潮", "中潮", "中潮",
              "中潮", "小潮", "小潮", "小潮", "長潮", "若潮", "中潮", "中潮", "大潮", "大潮")
SYNODIC = 29.530589
# MOON_PHASE_POSITION runs 0-27 over a lunation; the age at the middle of a step.
MOON_AGE = f"(([MOON_PHASE_POSITION] + 0.5) * {SYNODIC / 28:.5f})"


# ---------------------------------------------------------------- XML helpers

def point(angle, r, cx=C, cy=C):
    a = math.radians(angle)
    return cx + r * math.sin(a), cy - r * math.cos(a)


HIDE_IN_AMBIENT = '<Variant mode="AMBIENT" target="alpha" value="0"/>'
SHOW_IN_AMBIENT = '<Variant mode="AMBIENT" target="alpha" value="255"/>'


def mode_parts(mode):
    return {"both": ("", ""), "active": ("", HIDE_IN_AMBIENT), "ambient": (' alpha="0"', SHOW_IN_AMBIENT)}[mode]


def box_attr(x, y, w, h):
    return f'x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}"'


def group(name, body, turn=None, mode="both", box=FULL, extra=""):
    alpha, variant = mode_parts(mode)
    tr = f'<Transform target="angle" value="{turn}"/>' if turn else ""
    return (f'<Group name="{name}" {box} pivotX="0.5" pivotY="0.5"{alpha}>'
            f"{variant}{tr}{extra}{body}</Group>")


def draw(name, body, mode="both", box=FULL):
    alpha, variant = mode_parts(mode)
    return f'<PartDraw name="{name}" {box}{alpha}>{variant}{body}</PartDraw>'


def image(name, resource, x, y, w, h, mode="both"):
    alpha, variant = mode_parts(mode)
    return (f'<PartImage name="{name}" {box_attr(x, y, w, h)}{alpha}>{variant}'
            f'<Image resource="{resource}"/></PartImage>')


def stroke(color, width, cap="BUTT"):
    return f'<Stroke color="#{color}" thickness="{width:g}" cap="{cap}"/>'


def arc(r, a0, a1, color, width, cx=C, cy=C, transforms=""):
    return (f'<Arc centerX="{cx:g}" centerY="{cy:g}" width="{2 * r:g}" height="{2 * r:g}" '
            f'startAngle="{a0:.2f}" endAngle="{a1:.2f}">{stroke(color, width)}{transforms}</Arc>')


def circle(r, color, width, cx=C, cy=C):
    return arc(r, 0, 360, color, width, cx, cy)


def disc(r, fill, cx=C, cy=C, edge=None, width=1.2):
    s = stroke(edge, width) if edge else ""
    return (f'<Ellipse x="{cx - r:g}" y="{cy - r:g}" width="{2 * r:g}" height="{2 * r:g}">'
            f'<Fill color="#{fill}"/>{s}</Ellipse>')


def line(x1, y1, x2, y2, color, width, cap="BUTT"):
    return (f'<Line startX="{x1:.2f}" startY="{y1:.2f}" endX="{x2:.2f}" endY="{y2:.2f}">'
            f"{stroke(color, width, cap)}</Line>")


def rect(x, y, w, h, color, width, radius=0):
    tag = "RoundRectangle" if radius else "Rectangle"
    rad = f' cornerRadiusX="{radius}" cornerRadiusY="{radius}"' if radius else ""
    return f'<{tag} {box_attr(x, y, w, h)}{rad}>{stroke(color, width)}</{tag}>'


def ticks(r1, r2, n, color, width, cx=C, cy=C):
    return "".join(line(*point(i * 360 / n, r1, cx, cy), *point(i * 360 / n, r2, cx, cy), color, width)
                   for i in range(n))


def text(name, x, y, w, h, size, color, content, family=FONT, align="CENTER", spacing=None, mode="both"):
    alpha, variant = mode_parts(mode)
    sp = f' letterSpacing="{spacing}"' if spacing else ""
    return (f'<PartText name="{name}" {box_attr(round(x), round(y), round(w), round(h))}{alpha}>{variant}'
            f'<Text align="{align}" ellipsis="TRUE">'
            f'<Font family="{family}" size="{size}" color="#{color}"{sp}>{content}</Font></Text></PartText>')


def template(fmt, *exprs):
    return "<Template>" + fmt + "".join(f'<Parameter expression="{e}"/>' for e in exprs) + "</Template>"


def condition(name, expr, body, default=""):
    d = f"<Default>{default}</Default>" if default else ""
    return (f'<Condition><Expressions><Expression name="{name}"><![CDATA[{expr}]]></Expression>'
            f'</Expressions><Compare expression="{name}">{body}</Compare>{d}</Condition>')


def choose(prefix, cases, default=""):
    """One Condition with a Compare per (suffix, expression, body); the first match wins."""
    exprs = "".join(f'<Expression name="{prefix}{s}"><![CDATA[{e}]]></Expression>' for s, e, _ in cases)
    compares = "".join(f'<Compare expression="{prefix}{s}">{b}</Compare>' for s, _, b in cases)
    d = f"<Default>{default}</Default>" if default else ""
    return f"<Condition><Expressions>{exprs}</Expressions>{compares}{d}</Condition>"


def empty(name="empty"):
    return f'<Group name="{name}" {FULL}/>'


def by_mode(name, parts):
    """A ListConfiguration on the mode with one body per mode."""
    options = "".join(f'<ListOption id="{m}">{group(f"{name}_{m}", parts.get(m) or empty(f"{name}_{m}E"))}'
                      "</ListOption>" for m in MODES)
    return group(name, f'<ListConfiguration id="mode">{options}</ListConfiguration>')


def sub_box(center, r=SUB_R):
    cx, cy = center
    return box_attr(cx - r, cy - r, 2 * r, 2 * r)


def is_any(expr, values):
    return " || ".join(f"{expr} == {v}" for v in values)


# ---------------------------------------------------------------- the dial

def dial(mode):
    """Minute ticks, hour markers, brand, date window, sub-dial rims and print."""
    accent = ACCENT[mode]
    tri = (line(C - 8, 25, C + 8, 25, LUME, 2, "ROUND") + line(C + 8, 25, C, 41, LUME, 2, "ROUND")
           + line(C, 41, C - 8, 25, LUME, 2, "ROUND"))
    hours = "".join(line(*point(i * 30, HOUR_MARK_R - HOUR_MARK_LEN / 2), *point(i * 30, HOUR_MARK_R + HOUR_MARK_LEN / 2),
                         LUME, 3) for i in range(1, 12))
    base = ticks(MINUTE_TICK_R + 2.5, MINUTE_TICK_R - 2.5, 60, DIM, 1) + hours + tri
    label = {"camp": "CAMP · AUTOMATIC", "fish": "TIDE · AUTOMATIC"}[mode]
    print_ = (text(f"brand{mode}", C - 80, 74, 160, 18, 14, EDGE, "FIELDMARK", family=FONT_BOLD, spacing=0.28)
              + text(f"label{mode}", C - 80, 90, 160, 12, 8, accent, label, spacing=0.3)
              + draw(f"dateWin{mode}", rect(C - 13, 105, 26, 18, DIM, 1.2, radius=2))
              + text(f"date{mode}", C - 13, 106, 26, 16, 12, TEXT, template("%d", "[DAY]"), family=FONT_BOLD))

    def rim(name, center, r=SUB_R):
        return draw(name, circle(r, RING, 1.2, *center))

    def compass(name, center):
        cx, cy = center
        out = draw(f"{name}Ticks", ticks(52, 48, 16, DIM, 1, cx, cy))
        for i, letter in enumerate("NESW"):
            x, y = point(i * 90, 38, cx, cy)
            out += text(f"{name}{letter}", x - 8, y - 7, 16, 14, 9, accent if letter == "N" else EDGE, letter,
                        family=FONT_BOLD)
        return out

    if mode == "camp":
        sun = RIGHT
        hours24 = "".join(text(f"sunH{h}", point(h * 15 + 180, 30, *sun)[0] - 8, point(h * 15 + 180, 30, *sun)[1] - 6,
                               16, 12, 7.5, MUTED, str(h)) for h in (6, 12, 18, 24))
        parts = (rim("windRim", LEFT) + compass("wind", LEFT)
                 + rim("sunRim", sun) + draw("sunTrack", circle(44, TRACK, 3, *sun)) + hours24
                 + rim("wxRim", BOTTOM, BOTTOM_R))
    else:
        x, y, w, h = TIDE_BOX
        gx, gy, gw, gh = TIDE_GRAPH
        grid = "".join(line(gx + gw * i / 4, gy, gx + gw * i / 4, gy + gh, TRACK, 1) for i in (1, 2, 3))
        grid += line(gx, gy + gh, gx + gw, gy + gh, RING, 1)
        hours_lbl = "".join(text(f"tideH{i}", gx + gw * i / 4 - 8, gy + gh + 6, 16, 10, 7, MUTED, str(i * 6))
                            for i in range(5))
        parts = (rim("moonRim", LEFT) + draw("moonTicks", ticks(52.5, 49.5, 30, DIM, 0.8, *LEFT))
                 + rim("windRim", RIGHT) + compass("wind", RIGHT)
                 + draw("tideBox", rect(x, y, w, h, RING, 1.2, radius=10) + grid) + hours_lbl
                 + text("tideLabel", x + 8, y + 4, 40, 10, 7, accent, "TIDE", spacing=0.2))
    return group(f"dial{mode}", draw(f"base{mode}", base) + print_ + parts, mode="active")


def ambient_dial(mode):
    dots = "".join(disc(2, AMB, *point(i * 30, AOD_DOT_R)) for i in range(1, 12))
    tri = (line(C - 6, 32, C + 6, 32, AMB, 1.4, "ROUND") + line(C + 6, 32, C, 44, AMB, 1.4, "ROUND")
           + line(C, 44, C - 6, 32, AMB, 1.4, "ROUND"))
    date = choose(f"aodDow{mode}", [(str(i), f"[DAY_OF_WEEK] == {i + 1}",
                                     text(f"aodDate{mode}{i}", C - 50, 112, 100, 18, 13, AMB,
                                          template(f"{name} %d", "[DAY]"), spacing=0.15))
                                    for i, name in enumerate(DOW)])
    return group(f"aod{mode}", draw(f"aodBase{mode}", dots + tri) + date, mode="ambient")


# ---------------------------------------------------------------- Wear OS data

def tide_name_text(name, x, y, w, h, size, color, mode="both"):
    """The tide name for the moon age, from the table above."""
    runs = []
    start = 0
    for i in range(1, len(TIDE_NAMES) + 1):
        if i == len(TIDE_NAMES) or TIDE_NAMES[i] != TIDE_NAMES[start]:
            runs.append((start, i, TIDE_NAMES[start]))
            start = i
    cases = [(str(k), f"{MOON_AGE} >= {lo} && {hi} > {MOON_AGE}" if hi < len(TIDE_NAMES) else f"{MOON_AGE} >= {lo}",
              text(f"{name}{k}", x, y, w, h, size, color, nm, family=SYSTEM_FONT, mode=mode))
             for k, (lo, hi, nm) in enumerate(runs)]
    return choose(name, cases)


def moon(mode):
    """Fish mode: the moon's shape (28 images), an age pointer on the rim and
    the tide name under it."""
    cx, cy = LEFT
    accent = ACCENT[mode]
    shapes = choose("moonShape", [(str(p), f"[MOON_PHASE_POSITION] == {p}",
                                   image(f"moon{p}", f"moon_{p:02d}", cx - 20, cy - 26, 40, 40)) for p in range(28)])
    pointer = group("moonAge", image("moonAgeTri", f"tri_{mode}", 52, 3, 8, 7),
                    turn="[MOON_PHASE_POSITION] / 28 * 360", box=sub_box(LEFT))
    labels = (tide_name_text("tideName", cx - 30, cy + 25, 60, 18, 12, accent)
              + text("moonAgeText", cx - 50, SUB_LABEL_Y, 100, 14, 10, TEXT,
                     template("MOON AGE %d", f"floor({MOON_AGE})"), spacing=0.1))
    return group("moon", shapes + pointer + labels, mode="active")


def ambient_moon(mode):
    cx, cy = C, 300.0
    shapes = choose("aodMoonShape", [(str(p), f"[MOON_PHASE_POSITION] == {p}",
                                      image(f"aodMoon{p}", f"moon_amb_{p:02d}", cx - 12, cy - 12, 24, 24))
                                     for p in range(28)])
    return group("aodMoon", shapes + tide_name_text("aodTideName", C - 40, 318, 80, 16, 12, AMB), mode="ambient")


def sun_hand(mode):
    """Camp mode: the 24-hour hand of the sun dial (native time, no data)."""
    accent = ACCENT[mode]
    cx, cy = RIGHT
    body = image("sunHandImg", f"sun_hand_{mode}", SUB_R - 5, SUB_R - 45, 10, 53)
    return group("sunHand", body, turn="[HOUR_0_23_MINUTE] / 24 * 360 + 180", box=sub_box(RIGHT), mode="active")


def current_weather(mode):
    """Camp mode: icon, temperature, low/high and chance of rain."""
    cx, cy = BOTTOM
    ok = "[WEATHER.IS_AVAILABLE] && !([WEATHER.IS_ERROR])"
    icon = choose("wxNow", [(k, f"{ok} && ({is_any('[WEATHER.CONDITION]', v)})",
                             image(f"wxNow{k}", f"wx_{k}_{mode}", cx - 14, cy - 44, 28, 28))
                            for k, v in WEATHER_ICONS])
    readings = (text("wxTemp", cx - 40, cy - 14, 80, 26, 22, TEXT, template("%d°", "[WEATHER.TEMPERATURE]"),
                     family=FONT_BOLD)
                + text("wxHiLo", cx - 46, cy + 12, 92, 12, 9, MUTED,
                       template("L%d° H%d°", "[WEATHER.TEMPERATURE_LOW]", "[WEATHER.TEMPERATURE_HIGH]"), spacing=0.08)
                + text("wxPop", cx - 46, cy + 24, 92, 14, 10, MUTED,
                       template("降水 %d％", "[WEATHER.CHANCE_OF_PRECIPITATION]"), family=SYSTEM_FONT))
    none = text("wxNone", cx - 40, cy - 14, 80, 26, 22, MUTED, "--°", family=FONT_BOLD)
    return group("wxNowGroup", icon + condition("wxOk", ok, readings, none), mode="active")


def forecast_marks():
    """The next 12 hours between the hour markers. Hour k sits in the middle of
    the segment k hours after the one the hour hand is in, kept upright."""
    out = []
    for amb in (False, True):
        sfx = "A" if amb else ""
        mode = "ambient" if amb else "active"
        for k in range(FORECAST_HOURS):
            avail = f"[WEATHER.HOURS.{k}.IS_AVAILABLE]"
            cond = f"[WEATHER.HOURS.{k}.CONDITION]"
            angle = f"([HOUR_0_11] + {k} + 0.5) * 30"
            cases = []
            for kind, values in FORECAST_MARKS:
                if amb and kind == "dry":
                    continue  # nothing lit for dry hours in ambient
                res = f"fc_{kind}{'_amb' if amb else ''}"
                cases.append((kind, f"{avail} && ({is_any(cond, values)})",
                              image(f"fc{sfx}{k}{kind}", res, 0, 0, MARK, MARK)))
            mark = group(f"fcUp{sfx}{k}", choose(f"fc{sfx}{k}", cases), turn=f"-({angle})",
                         box=box_attr(C - MARK / 2, C - HOUR_MARK_R - MARK / 2, MARK, MARK))
            out.append(group(f"fcHour{sfx}{k}", mark, turn=angle, mode=mode))
    return "".join(out)


# ---------------------------------------------------------------- companion data

def data_slot(slot_id, name, source, kind, body):
    """A full-face slot fixed to one of the companion's data sources."""
    return (f'<ComplicationSlot slotId="{slot_id}" name="{name}" displayName="@string/{name}" '
            f'{FULL} supportedTypes="{kind}" isCustomizable="FALSE">'
            f'<DefaultProviderPolicy defaultSystemProvider="EMPTY" defaultSystemProviderType="{kind}" '
            f'primaryProvider="{COMPANION}{source}" primaryProviderType="{kind}"/>'
            f'<BoundingBox {FULL}/>'
            f'<Complication type="{kind}">{body}</Complication></ComplicationSlot>')


def wind_parts(mode, center):
    """Arrow (pointing to where the wind comes from) and the reading under it.
    RANGED_VALUE: value = direction in degrees, title = compass point, text = m/s."""
    cx, cy = center
    arrow = group(f"windArrow{mode}", image(f"windArrowImg{mode}", f"wind_arrow_{mode}", SUB_R - 5, SUB_R - 43, 10, 66),
                  turn="[COMPLICATION.RANGED_VALUE_VALUE]", box=sub_box(center), mode="active")
    cap = draw(f"windCap{mode}", disc(3.5, "FF000000", cx, cy, EDGE, 1.2), mode="active")
    reading = text(f"windText{mode}", cx - 55, SUB_LABEL_Y, 110, 14, 10, TEXT,
                   template("WIND %s %s m/s", "[COMPLICATION.TITLE]", "[COMPLICATION.TEXT]"), spacing=0.1,
                   mode="active")
    out = arrow + cap + reading
    if mode == "camp":
        out += text("aodWind", C - 80, 345, 160, 16, 11, AMB,
                    template("WIND %s %s m/s", "[COMPLICATION.TITLE]", "[COMPLICATION.TEXT]"), spacing=0.15,
                    mode="ambient")
    return out


def sun_parts(mode):
    """Camp mode: daylight arc and the times. RANGED_VALUE: min = sunrise and
    max = sunset in minutes after midnight, text = sunrise, title = sunset."""
    cx, cy = RIGHT
    accent = ACCENT[mode]
    to_angle = lambda m: f"{m} / 1440 * 360 + 180"
    day = (f'<Arc centerX="{cx:g}" centerY="{cy:g}" width="88" height="88" startAngle="270" endAngle="90">'
           f'{stroke(accent, 3, "ROUND")}'
           f'<Transform target="startAngle" value="{to_angle("[COMPLICATION.RANGED_VALUE_MIN]")}"/>'
           f'<Transform target="endAngle" value="{to_angle("[COMPLICATION.RANGED_VALUE_MAX]")}"/></Arc>')
    return (draw("dayArc", day, mode="active")
            + text("sunText", cx - 55, SUB_LABEL_Y, 110, 14, 10, TEXT,
                   template("SUN %s – %s", "[COMPLICATION.TEXT]", "[COMPLICATION.TITLE]"), spacing=0.1, mode="active")
            + text("aodSun", C - 80, 327, 160, 18, 13, AMB, template("SUNSET %s", "[COMPLICATION.TITLE]"),
                   spacing=0.15, mode="ambient"))


def tide_graph_parts():
    gx, gy, gw, gh = TIDE_GRAPH
    return (f'<PartImage name="tideGraph" {box_attr(gx, gy, gw, gh)}>{HIDE_IN_AMBIENT}'
            '<Image resource="[COMPLICATION.PHOTO_IMAGE]"/></PartImage>')


def tide_times_parts():
    """SHORT_TEXT: text = next high water, title = next low water."""
    x, y, w, h = TIDE_BOX
    return (text("tideTimes", x + 4, y + 70, w - 8, 18, 11, TEXT,
                 template("満潮 %s  干潮 %s", "[COMPLICATION.TEXT]", "[COMPLICATION.TITLE]"), family=SYSTEM_FONT,
                 mode="active")
            + text("aodTide", C - 80, 337, 160, 18, 12, AMB, template("満潮 %s", "[COMPLICATION.TEXT]"),
                   family=SYSTEM_FONT, mode="ambient"))


def companion_slots():
    return (data_slot(1, "slot_wind", "WindDataSource", "RANGED_VALUE",
                      by_mode("wind", {"camp": wind_parts("camp", LEFT), "fish": wind_parts("fish", RIGHT)}))
            + data_slot(2, "slot_sun", "SunDataSource", "RANGED_VALUE", by_mode("sun", {"camp": sun_parts("camp")}))
            + data_slot(3, "slot_tide_graph", "TideGraphDataSource", "PHOTO_IMAGE",
                        by_mode("tideGraph", {"fish": tide_graph_parts()}))
            + data_slot(4, "slot_tide_times", "TideTimesDataSource", "SHORT_TEXT",
                        by_mode("tideTimes", {"fish": tide_times_parts()})))


# ---------------------------------------------------------------- hands

# Hand images: (resource, box half width, length to the tip, tail length).
HANDS = {"hour": (8, 121, 13), "min": (6, 193, 17), "sec": (3, 197, 29)}


def hand(name, kind, resource, turn, mode):
    hw, tip, tail = HANDS[kind]
    return group(name, image(f"{name}Img", resource, C - hw, C - tip, 2 * hw, tip + tail), turn=turn, mode=mode)


def hands():
    out = (hand("hourHand", "hour", "hand_hour", "[HOUR_0_11_MINUTE] * 30", "active")
           + hand("minHand", "min", "hand_min", "[MINUTE] * 6", "active")
           + hand("hourHandAmb", "hour", "hand_hour_amb", "[HOUR_0_11_MINUTE] * 30", "ambient")
           + hand("minHandAmb", "min", "hand_min_amb", "[MINUTE] * 6", "ambient"))
    # The seconds hand steps once a second, in the mode's accent, or is off.
    sec = by_mode("secHand", {m: group(f"secHandSel{m}", (
        '<ListConfiguration id="secHand">'
        f'<ListOption id="tick">{hand(f"secHand{m}", "sec", f"hand_sec_{m}", "[SECOND] * 6", "active")}</ListOption>'
        f'<ListOption id="off">{empty(f"secOff{m}")}</ListOption></ListConfiguration>')) for m in MODES})
    caps = by_mode("cap", {m: draw(f"cap{m}", disc(5, "FF000000", edge=EDGE, width=1.4) + disc(1.8, ACCENT[m]),
                                   mode="active") for m in MODES})
    amb_cap = draw("capAmb", disc(5, "FF000000", edge=AMB, width=1.4), mode="ambient")
    return out + sec + caps + amb_cap


# ---------------------------------------------------------------- the face

def user_configurations():
    return ("<UserConfigurations>"
            '<ListConfiguration id="mode" displayName="@string/cfg_mode" defaultValue="camp">'
            '<ListOption id="camp" displayName="@string/mode_camp"/>'
            '<ListOption id="fish" displayName="@string/mode_fish"/></ListConfiguration>'
            '<ListConfiguration id="secHand" displayName="@string/cfg_sec_hand" defaultValue="tick">'
            '<ListOption id="tick" displayName="@string/sec_hand_tick"/>'
            '<ListOption id="off" displayName="@string/sec_hand_off"/></ListConfiguration>'
            "</UserConfigurations>")


def watchface_xml():
    dials = by_mode("dial", {m: dial(m) + ambient_dial(m) for m in MODES})
    native = by_mode("native", {"camp": sun_hand("camp") + current_weather("camp"),
                                "fish": moon("fish") + ambient_moon("fish")})
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!-- Generated by tools/generate_fieldmark.py. Edit the script, not this file. -->
<WatchFace width="{SIZE}" height="{SIZE}" clipShape="CIRCLE">
  <Metadata key="CLOCK_TYPE" value="ANALOG"/>
  <Metadata key="PREVIEW_TIME" value="10:08:32"/>
  {user_configurations()}
  <Scene backgroundColor="#FF000000">
    {dials}
    {companion_slots()}
    {native}
    {forecast_marks()}
    {hands()}
  </Scene>
</WatchFace>
"""


# ---------------------------------------------------------------- images

SS = 4  # supersampling for the images


def rgba(argb, alpha=None):
    r, g, b, a = (int(argb[i:i + 2], 16) for i in (2, 4, 6, 0))
    return (r, g, b, a if alpha is None else alpha)


class Canvas:
    """A transparent image drawn in face pixels at `scale` pixels each, supersampled."""

    def __init__(self, w, h, scale=2):
        self.w, self.h, self.scale = w, h, scale
        self.k = scale * SS
        self.img = Image.new("RGBA", (round(w * self.k), round(h * self.k)), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def p(self, x, y):
        return (x * self.k, y * self.k)

    def poly(self, pts, fill=None, outline=None, width=1.0):
        pts = [self.p(x, y) for x, y in pts]
        if fill:
            self.d.polygon(pts, fill=rgba(fill))
        if outline:
            self.d.line(pts + [pts[0]], fill=rgba(outline), width=max(1, round(width * self.k)), joint="curve")

    def line(self, pts, color, width):
        self.d.line([self.p(x, y) for x, y in pts], fill=rgba(color), width=max(1, round(width * self.k)),
                    joint="curve")

    def circle(self, cx, cy, r, fill=None, outline=None, width=1.0):
        box = [*self.p(cx - r, cy - r), *self.p(cx + r, cy + r)]
        self.d.ellipse(box, fill=rgba(fill) if fill else None, outline=rgba(outline) if outline else None,
                       width=max(1, round(width * self.k)) if outline else 0)

    def save(self, name):
        out = self.img.resize((round(self.w * self.scale), round(self.h * self.scale)), Image.LANCZOS)
        out.save(DRAWABLE / f"{name}.png", optimize=True)
        return out


def hand_images():
    for amb in (False, True):
        sfx = "_amb" if amb else ""
        edge = AMB if amb else EDGE
        for kind, shoulder, hw_body, strip in (("hour", 16, 6, (12, 86, 2.5)), ("min", 14, 4.5, (10, 164, 2))):
            hw, tip, tail = HANDS[kind]
            c = Canvas(2 * hw, tip + tail)
            body = [(hw, 1), (hw + hw_body, 1 + shoulder), (hw + hw_body, tip + tail - 1),
                    (hw - hw_body, tip + tail - 1), (hw - hw_body, 1 + shoulder)]
            c.poly(body, fill="FF000000", outline=edge, width=1.4)
            if not amb:
                s0, s1, sw = strip
                c.poly([(hw, 1 + s0), (hw + sw, 1 + s0 + 8), (hw + sw, 1 + s1), (hw - sw, 1 + s1), (hw - sw, 1 + s0 + 8)],
                       fill=LUME)
            c.save(f"hand_{kind}{sfx}")
    for m in MODES:
        hw, tip, tail = HANDS["sec"]
        c = Canvas(2 * hw, tip + tail)
        c.line([(hw, 0.5), (hw, tip + tail - 0.5)], ACCENT[m], 1.4)
        c.save(f"hand_sec_{m}")


def mode_images():
    for m in MODES:
        accent = ACCENT[m]
        # Wind arrow: accent tip to the centre, outline tail.
        c = Canvas(10, 66)
        c.poly([(5, 1), (9, 43), (1, 43)], fill=accent)
        c.poly([(1, 43), (9, 43), (5, 65)], outline=EDGE, width=1.2)
        c.save(f"wind_arrow_{m}")
        # The small triangle of the moon-age pointer.
        c = Canvas(8, 7)
        c.poly([(4, 0.5), (7.5, 6.5), (0.5, 6.5)], fill=accent)
        c.save(f"tri_{m}")
        # Sun hand: a line from the centre with an outline sun at its end.
        c = Canvas(10, 53)
        c.line([(5, 9), (5, 51)], EDGE, 1.2)
        c.circle(5, 5, 3.5, outline=accent, width=1.6)
        c.circle(5, 45, 3, fill="FF000000", outline=EDGE, width=1.2)
        c.save(f"sun_hand_{m}")
        weather_icons(m, accent)


def drop(c, cx, cy, s, fill=None, outline=None, width=1.4):
    """A raindrop centred near (cx, cy), s = its radius."""
    pts = []
    for i in range(0, 41):
        t = i / 40 * 2 * math.pi
        # A circle with its top pulled into a point.
        x = math.sin(t) * s
        y = -math.cos(t) * s
        if y < 0:
            y *= 1 + 0.9 * (1 - abs(math.sin(t))) ** 2
            x *= 1 - 0.35 * (1 - abs(math.sin(t)))
        pts.append((cx + x, cy + y + s * 0.3))
    c.poly(pts, fill=fill, outline=outline, width=width)


def flake(c, cx, cy, s, color, width):
    for i in range(3):
        a = math.radians(i * 60 + 90)
        c.line([(cx + s * math.cos(a), cy + s * math.sin(a)), (cx - s * math.cos(a), cy - s * math.sin(a))], color, width)


def forecast_images():
    for amb in (False, True):
        sfx = "_amb" if amb else ""
        rain = AMB_RAIN if amb else RAIN
        snow = AMB_SNOW if amb else SNOW
        h = MARK / 2
        for kind, _ in FORECAST_MARKS:
            if amb and kind == "dry":
                continue
            c = Canvas(MARK, MARK, scale=3)
            if kind == "dry":
                c.circle(h, h, 1.6, fill=RING)
            elif kind == "rain_l":
                drop(c, h, h, 3.8, outline=rain, width=1.4)
            elif kind == "rain_h":
                drop(c, h - 3.4, h + 1.2, 3.2, fill=rain)
                drop(c, h + 3.4, h - 1.6, 3.2, fill=rain)
            elif kind == "snow_l":
                flake(c, h, h, 4.5, snow, 1.3)
            elif kind == "snow_h":
                flake(c, h - 3.8, h + 1.6, 3.6, snow, 1.6)
                flake(c, h + 3.8, h - 2.0, 3.6, snow, 1.6)
            else:  # sleet: a drop and a flake side by side
                drop(c, h - 3.6, h + 0.6, 3.0, fill=rain)
                flake(c, h + 3.8, h - 0.6, 3.6, snow, 1.3)
            c.save(f"fc_{kind}{sfx}")


def weather_icons(m, accent):
    for kind, _ in WEATHER_ICONS:
        c = Canvas(28, 28)

        def cloud(dy=0):
            pts = []
            for cx, cy, r, a0, a1 in ((9, 17, 5, 90, 270), (14.5, 12.5, 6.5, 200, 340), (20, 16, 5, 270, 450)):
                for i in range(13):
                    a = math.radians(a0 + (a1 - a0) * i / 12)
                    pts.append((cx + r * math.cos(a), cy + dy + r * math.sin(a)))
            c.poly(pts, fill="FF000000", outline=EDGE, width=1.4)

        if kind == "sun":
            c.circle(14, 14, 5, outline=accent, width=1.6)
            for i in range(8):
                a = math.radians(i * 45)
                c.line([(14 + 8 * math.cos(a), 14 + 8 * math.sin(a)), (14 + 11 * math.cos(a), 14 + 11 * math.sin(a))],
                       accent, 1.4)
        elif kind == "cloud":
            c.circle(18, 9, 4.5, outline=accent, width=1.4)
            cloud(2)
        elif kind == "rain":
            cloud(-3)
            for dx in (-5, 0, 5):
                c.line([(14 + dx, 21), (13 + dx, 25)], RAIN, 1.4)
        elif kind == "snow":
            flake(c, 14, 14, 9, SNOW, 1.4)
        else:
            cloud(-3)
            c.poly([(15, 19), (11, 24), (14, 24), (12, 27.5), (17.5, 22), (14.5, 22)], fill=accent)
        c.save(f"wx_{kind}_{m}")


def moon_images():
    """28 phases for MOON_PHASE_POSITION 0-27 (0 = new moon, 14 = full)."""
    for amb in (False, True):
        size = 24 if amb else 40
        r = size / 2 - 1.5
        lit = rgba(AMB_MOON if amb else MOON_LIT)
        for p in range(28):
            f = (p + 0.5) / 28
            k = 4
            n = size * k
            img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
            px = img.load()
            rr = r * k
            for yy in range(n):
                y = (yy + 0.5) - n / 2
                if abs(y) >= rr:
                    continue
                half = math.sqrt(rr * rr - y * y)
                term = half * math.cos(2 * math.pi * f)
                for xx in range(n):
                    x = (xx + 0.5) - n / 2
                    if abs(x) >= half:
                        continue
                    on = x > term if f < 0.5 else x < -term
                    if on:
                        px[xx, yy] = lit
            d = ImageDraw.Draw(img)
            edge = rgba(AMB_MOON if amb else RING)
            d.ellipse([n / 2 - rr, n / 2 - rr, n / 2 + rr, n / 2 + rr], outline=edge, width=k)
            img.resize((size * 2, size * 2), Image.LANCZOS).save(
                DRAWABLE / f"moon{'_amb' if amb else ''}_{p:02d}.png", optimize=True)


# ---------------------------------------------------------------- preview

def preview_png():
    """Camp mode at 10:08:32, for the watch face picker."""
    k = 2
    img = Image.new("RGBA", (SIZE * k, SIZE * k), (0, 0, 0, 255))
    d = ImageDraw.Draw(img)
    from PIL import ImageFont
    font = lambda name, size: ImageFont.truetype(str(RES / "font" / f"{name}.ttf"), round(size * k * 1.2))
    P = lambda x, y: (round(x * k), round(y * k))

    def ln(x1, y1, x2, y2, color, w):
        d.line([P(x1, y1), P(x2, y2)], fill=rgba(color), width=max(1, round(w * k)))

    def ring(cx, cy, r, color, w):
        d.ellipse([*P(cx - r, cy - r), *P(cx + r, cy + r)], outline=rgba(color), width=max(1, round(w * k)))

    def txt(x, y, s, size, color, name=FONT):
        d.text(P(x, y), s, font=font(name, size), fill=rgba(color), anchor="mm")

    accent = ACCENT["camp"]
    for i in range(60):
        ln(*point(i * 6, MINUTE_TICK_R + 2.5), *point(i * 6, MINUTE_TICK_R - 2.5), DIM, 1)
    for i in range(1, 12):
        ln(*point(i * 30, HOUR_MARK_R - 7), *point(i * 30, HOUR_MARK_R + 7), LUME, 3)
    d.line([P(C - 8, 25), P(C + 8, 25), P(C, 41), P(C - 8, 25)], fill=rgba(LUME), width=2 * k)
    txt(C, 83, "FIELDMARK", 14, EDGE, FONT_BOLD)
    txt(C, 96, "CAMP · AUTOMATIC", 8, accent)
    d.rounded_rectangle([*P(C - 13, 105), *P(C + 13, 123)], radius=2 * k, outline=rgba(DIM), width=k)
    txt(C, 114, "27", 12, TEXT, FONT_BOLD)
    for center in (LEFT, RIGHT):
        ring(*center, SUB_R, RING, 1.2)
    ring(*BOTTOM, BOTTOM_R, RING, 1.2)
    cx, cy = LEFT
    for i in range(16):
        ln(*point(i * 22.5, 52, cx, cy), *point(i * 22.5, 48, cx, cy), DIM, 1)
    for i, letter in enumerate("NESW"):
        txt(*point(i * 90, 38, cx, cy), letter, 9, accent if letter == "N" else EDGE, FONT_BOLD)
    arrow = Image.open(DRAWABLE / "wind_arrow_camp.png").resize((10 * k, 66 * k), Image.LANCZOS)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    layer.paste(arrow, P(cx - 5, cy - 43))
    img.alpha_composite(layer.rotate(45, center=P(cx, cy), resample=Image.BICUBIC))
    txt(cx, SUB_LABEL_Y + 7, "WIND NW 3.2 m/s", 10, TEXT)
    sx, sy = RIGHT
    ring(sx, sy, 44, TRACK, 3)
    d.arc([*P(sx - 44, sy - 44), *P(sx + 44, sy + 44)], start=6.2 / 24 * 360 + 90, end=16.6 / 24 * 360 + 90,
          fill=rgba(accent), width=3 * k)
    for h in (6, 12, 18, 24):
        txt(*point(h * 15 + 180, 30, sx, sy), str(h), 7.5, MUTED)
    txt(sx, SUB_LABEL_Y + 7, "SUN 06:13 – 16:38", 10, TEXT)
    sun = Image.open(DRAWABLE / "sun_hand_camp.png").resize((10 * k, 53 * k), Image.LANCZOS)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    layer.paste(sun, P(sx - 5, sy - 45))
    img.alpha_composite(layer.rotate(-(10.14 / 24 * 360 + 180), center=P(sx, sy), resample=Image.BICUBIC))
    bx, by = BOTTOM
    icon = Image.open(DRAWABLE / "wx_cloud_camp.png").resize((28 * k, 28 * k), Image.LANCZOS)
    img.alpha_composite(icon, P(bx - 14, by - 44))
    txt(bx, by, "15°", 22, TEXT, FONT_BOLD)
    txt(bx, by + 18, "L7° H17°", 9, MUTED)
    sample = ("dry", "dry", "rain_l", "rain_l", "rain_h", "rain_h", "rain_l", "sleet", "snow_l", "snow_h", "snow_l", "dry")
    for i, kind in enumerate(sample):
        mark = Image.open(DRAWABLE / f"fc_{kind}.png").resize((MARK * k, MARK * k), Image.LANCZOS)
        x, y = point((10 + i + 0.5) * 30, HOUR_MARK_R)
        img.alpha_composite(mark, P(x - MARK / 2, y - MARK / 2))

    def put_hand(name, kind, angle):
        hw, tip, tail = HANDS[kind]
        hand_img = Image.open(DRAWABLE / f"{name}.png").resize((2 * hw * k, (tip + tail) * k), Image.LANCZOS)
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        layer.paste(hand_img, P(C - hw, C - tip))
        img.alpha_composite(layer.rotate(-angle, center=P(C, C), resample=Image.BICUBIC))

    put_hand("hand_hour", "hour", (10 + 8 / 60) * 30)
    put_hand("hand_min", "min", 8 * 6)
    put_hand("hand_sec_camp", "sec", 32 * 6)
    d = ImageDraw.Draw(img)
    d.ellipse([*P(C - 5, C - 5), *P(C + 5, C + 5)], fill=(0, 0, 0, 255), outline=rgba(EDGE), width=round(1.4 * k))
    d.ellipse([*P(C - 1.8, C - 1.8), *P(C + 1.8, C + 1.8)], fill=rgba(accent))
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).ellipse([0, 0, SIZE * k - 1, SIZE * k - 1], fill=255)
    out = Image.new("RGB", img.size, (0, 0, 0))
    out.paste(img, mask=mask)
    out.resize((SIZE, SIZE), Image.LANCZOS).save(DRAWABLE / "preview.png", optimize=True)


def main():
    for sub in ("raw", "drawable-nodpi"):
        (RES / sub).mkdir(parents=True, exist_ok=True)
    (RES / "raw" / "watchface.xml").write_text(watchface_xml(), encoding="utf-8")
    hand_images()
    mode_images()
    forecast_images()
    moon_images()
    preview_png()


if __name__ == "__main__":
    main()
