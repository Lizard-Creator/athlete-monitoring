"""Generate the Power BI Project (PBIP): TMDL semantic model + PBIR report.

Run once to bootstrap (python powerbi/build_pbip.py), then open powerbi/AthleteMonitoring.pbip in
Power BI Desktop. After you start editing in Desktop, Desktop owns the files - don't regenerate over your work.
"""
import json
import re
import shutil
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "AthleteMonitoring"
MODEL, REPORT = HERE / f"{NAME}.SemanticModel", HERE / f"{NAME}.Report"
# The repo copy uses a placeholder (--placeholder) so no local path or username is published;
# a normal run writes this machine's path so Power BI can refresh.
PLACEHOLDER = "C:\\path\\to\\athlete-monitoring\\outputs\\powerbi\\"
DATA_FOLDER = PLACEHOLDER if "--placeholder" in sys.argv else str(HERE.parent / "outputs" / "powerbi") + "\\"
NS = uuid.UUID("6f1c2a52-3b1e-4b8e-9a51-0c7d2f7e9a11")
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"


def tag(*parts) -> str:
    """Deterministic lineageTag so regenerating doesn't churn every file."""
    return str(uuid.uuid5(NS, "/".join(parts)))


def q(name: str) -> str:
    """Quote a TMDL/DAX object name when needed."""
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) and name not in {"Date"}:
        return name
    return "'" + name.replace("'", "''") + "'"


# ---------------------------------------------------------------- semantic model
# column: (csv column, model name, type, hidden)
TYPES = {"text": ("string", "type text"), "int": ("int64", "Int64.Type"),
         "num": ("double", "type number"), "date": ("dateTime", "type date")}
FORMATS = {"int": "0", "num": "#,0.00", "date": "yyyy-mm-dd"}

TABLES = {
    "Players": dict(csv="players.csv", columns=[
        ("player_id", "Player", "text", False), ("position", "Position", "text", False),
        ("status", "Squad Status", "text", False), ("source_game", "source_game", "text", True),
        ("jersey", "jersey", "int", True), ("max_speed_ms", "max_speed_ms", "num", True)]),
    "Sessions": dict(csv="sessions.csv", md_order=True, columns=[
        ("player_id", "Player", "text", True), ("date", "Date", "date", True),
        ("session_type", "Session Type", "text", False), ("md_code", "MD Code", "text", False),
        ("duration_min", "duration_min", "int", True), ("total_distance_m", "total_distance_m", "num", True),
        ("hsr_distance_m", "hsr_distance_m", "num", True), ("sprint_distance_m", "sprint_distance_m", "num", True),
        ("sprint_efforts", "sprint_efforts", "int", True), ("accels", "accels", "int", True),
        ("decels", "decels", "int", True), ("max_speed_ms", "max_speed_ms", "num", True),
        ("rpe", "rpe", "int", True), ("srpe_au", "srpe_au", "int", True)]),
    "Daily Load": dict(csv="daily_load.csv", columns=[
        ("player_id", "Player", "text", True), ("date", "Date", "date", True),
        ("srpe_au", "srpe_au", "num", True), ("total_distance_m", "total_distance_m", "num", True),
        ("hsr_distance_m", "hsr_distance_m", "num", True), ("acute_7d", "acute_7d", "num", True),
        ("chronic_28d", "chronic_28d", "num", True), ("acwr", "acwr_value", "num", True),
        ("acwr_ewma", "acwr_ewma", "num", True), ("acwr_flag", "acwr_flag", "text", True)]),
    "Wellness": dict(csv="wellness.csv", columns=[
        ("player_id", "Player", "text", True), ("date", "Date", "date", True),
        ("sleep_quality", "sleep_quality", "int", True), ("fatigue", "fatigue_score", "int", True),
        ("soreness", "soreness_score", "int", True)]),
    "Injuries": dict(csv="injuries.csv", columns=[
        ("player_id", "Player", "text", True), ("injury_date", "Injury Date", "date", False),
        ("return_date", "Return Date", "date", False), ("days_out", "days_out", "int", True)]),
    "Match Loads": dict(csv="match_loads.csv", columns=[
        ("player_id", "Player", "text", True), ("source_game", "source_game", "text", True),
        ("minutes", "minutes", "num", True), ("total_distance_m", "total_distance_m", "num", True),
        ("hsr_distance_m", "hsr_distance_m", "num", True), ("sprint_distance_m", "sprint_distance_m", "num", True),
        ("sprint_efforts", "sprint_efforts", "int", True), ("accels", "accels", "int", True),
        ("decels", "decels", "int", True), ("max_speed_ms", "max_speed_ms", "num", True)]),
}

MD_ORDER_STEP = ('    WithOrder = Table.AddColumn(Renamed, "md_order", each Record.FieldOrDefault('
                 '[#"MD-4" = 1, #"MD-3" = 2, #"MD-2" = 3, #"MD-1" = 4, MD = 5, #"MD+1" = 6, COMP = 7, REHAB = 8], '
                 '[MD Code], 9), Int64.Type)')

DATE_M = """let
    Dates = List.Buffer(Sessions[Date]),
    Start = List.Min(Dates),
    DateList = List.Dates(Start, Duration.Days(List.Max(Dates) - Start) + 1, #duration(1, 0, 0, 0)),
    Base = Table.FromList(DateList, Splitter.SplitByNothing(), type table [Date = date]),
    WeekStart = Table.AddColumn(Base, "Week Start", each Date.StartOfWeek([Date], Day.Monday), type date),
    Weekday = Table.AddColumn(WeekStart, "Weekday", each Date.ToText([Date], "ddd", "en-US"), type text),
    WeekdayNo = Table.AddColumn(Weekday, "Weekday No", each Date.DayOfWeek([Date], Day.Monday) + 1, Int64.Type),
    Month = Table.AddColumn(WeekdayNo, "Month", each Date.ToText([Date], "MMM yyyy", "en-US"), type text),
    MonthNo = Table.AddColumn(Month, "Month No", each Date.Year([Date]) * 100 + Date.Month([Date]), Int64.Type)
in
    MonthNo"""

AS_OF = "VAR d = [Report Date]\nRETURN CALCULATE({expr}, 'Date'[Date] = d)"

# measure: (table, name, DAX, format, display folder)
MEASURES = [
    ("Sessions", "Distance (km)", "DIVIDE(SUM(Sessions[total_distance_m]), 1000)", "#,0.0", "Load"),
    ("Sessions", "HSR (m)", "SUM(Sessions[hsr_distance_m])", "#,0", "Load"),
    ("Sessions", "Sprint Distance (m)", "SUM(Sessions[sprint_distance_m])", "#,0", "Load"),
    ("Sessions", "Sprint Efforts", "SUM(Sessions[sprint_efforts])", "#,0", "Load"),
    ("Sessions", "Accels + Decels", "SUM(Sessions[accels]) + SUM(Sessions[decels])", "#,0", "Load"),
    ("Sessions", "sRPE (AU)", "SUM(Sessions[srpe_au])", "#,0", "Load"),
    ("Sessions", "Session Count", "COUNTROWS(Sessions)", "#,0", "Load"),
    ("Sessions", "Matches Played", 'CALCULATE(COUNTROWS(Sessions), Sessions[Session Type] = "Match") + 0', "0", "Load"),
    ("Sessions", "Top Speed (m/s)", "MAX(Sessions[max_speed_ms])", "0.0", "Load"),
    ("Sessions", "Avg Distance per Session (m)", "AVERAGE(Sessions[total_distance_m])", "#,0", "Periodization"),
    ("Sessions", "Avg HSR per Session (m)", "AVERAGE(Sessions[hsr_distance_m])", "#,0", "Periodization"),
    ("Sessions", "Avg sRPE per Session", "AVERAGE(Sessions[srpe_au])", "#,0", "Periodization"),
    ("Sessions", "Squad Avg sRPE (AU)", "AVERAGEX(VALUES(Players[Player]), [sRPE (AU)])", "#,0", "Periodization"),
    ("Sessions", "Weekly Load WoW %",
     "VAR cur = [sRPE (AU)]\nVAR prev = CALCULATE([sRPE (AU)], DATEADD('Date'[Date], -7, DAY))\n"
     "RETURN DIVIDE(cur - prev, prev)", "0.0%", "Periodization"),

    ("Daily Load", "Report Date", "MAX('Date'[Date])", "d mmm yy", "Status"),
    ("Daily Load", "Daily sRPE (AU)", "SUM('Daily Load'[srpe_au])", "#,0", "ACWR"),
    ("Daily Load", "ACWR", AS_OF.format(expr="AVERAGE('Daily Load'[acwr_value])"), "0.00", "ACWR"),
    ("Daily Load", "ACWR (EWMA)", AS_OF.format(expr="AVERAGE('Daily Load'[acwr_ewma])"), "0.00", "ACWR"),
    ("Daily Load", "Acute Load (7d)", AS_OF.format(expr="AVERAGE('Daily Load'[acute_7d])"), "#,0", "ACWR"),
    ("Daily Load", "Chronic Load (28d)", AS_OF.format(expr="AVERAGE('Daily Load'[chronic_28d])"), "#,0", "ACWR"),
    ("Daily Load", "ACWR Upper Band", "1.5", "0.0", "ACWR"),
    ("Daily Load", "ACWR Lower Band", "0.8", "0.0", "ACWR"),
    ("Daily Load", "ACWR Status",
     'VAR a = [ACWR]\nRETURN SWITCH(TRUE(), ISBLANK(a), "No data", a >= 1.5, "High", a < 0.8, "Low", "Normal")',
     None, "ACWR"),
    ("Daily Load", "ACWR Colour",
     'VAR a = [ACWR]\nRETURN SWITCH(TRUE(), ISBLANK(a), "#E0E0E0", a >= 1.5, "#EF9A9A", a < 0.8, "#FFE082", "#A5D6A7")',
     None, "ACWR"),
    ("Daily Load", "Players High ACWR", "COUNTROWS(FILTER(VALUES(Players[Player]), [ACWR] >= 1.5)) + 0", "0", "Status"),
    ("Daily Load", "Players Low ACWR", "COUNTROWS(FILTER(VALUES(Players[Player]), [ACWR] < 0.8)) + 0", "0", "Status"),

    ("Injuries", "Injured Players",
     "VAR d = [Report Date]\nRETURN COUNTROWS(DISTINCT(SELECTCOLUMNS(\n"
     "    FILTER(Injuries, Injuries[Injury Date] <= d && Injuries[Return Date] > d),\n"
     '    "p", Injuries[Player]))) + 0', "0", "Status"),
    ("Injuries", "Available Players", "COUNTROWS(Players) - [Injured Players]", "0", "Status"),
    ("Injuries", "Availability", 'IF([Injured Players] > 0, "Injured", "Available")', None, "Status"),
    ("Injuries", "Days Injured", "SUM(Injuries[days_out]) + 0", "0", "Status"),  # card: 0 instead of blank
    # Table rows: must stay BLANK for other players, or Power BI shows every injury row with 0
    ("Injuries", "Days Out", "SUM(Injuries[days_out])", "0", "Status"),

    ("Wellness", "Sleep", AS_OF.format(expr="AVERAGE(Wellness[sleep_quality])"), "0.0", "Wellness"),
    ("Wellness", "Fatigue", AS_OF.format(expr="AVERAGE(Wellness[fatigue_score])"), "0.0", "Wellness"),
    ("Wellness", "Soreness", AS_OF.format(expr="AVERAGE(Wellness[soreness_score])"), "0.0", "Wellness"),
    ("Wellness", "Wellness Score", AS_OF.format(
        expr="AVERAGEX(Wellness, (Wellness[sleep_quality] + Wellness[fatigue_score] + Wellness[soreness_score]) / 3)"),
     "0.0", "Wellness"),

    ("Match Loads", "Match Minutes", "SUM('Match Loads'[minutes])", "0", "Match (real data)"),
    ("Match Loads", "Match Distance (km)", "DIVIDE(SUM('Match Loads'[total_distance_m]), 1000)", "0.0", "Match (real data)"),
    ("Match Loads", "Match HSR (m)", "SUM('Match Loads'[hsr_distance_m])", "#,0", "Match (real data)"),
    ("Match Loads", "Match Sprint Efforts", "SUM('Match Loads'[sprint_efforts])", "0", "Match (real data)"),
    ("Match Loads", "Match Accels + Decels", "SUM('Match Loads'[accels]) + SUM('Match Loads'[decels])", "0", "Match (real data)"),
    ("Match Loads", "Match Top Speed (m/s)", "MAX('Match Loads'[max_speed_ms])", "0.0", "Match (real data)"),
    ("Match Loads", "Distance per 90 (m)",
     "DIVIDE(SUM('Match Loads'[total_distance_m]), SUM('Match Loads'[minutes])) * 90", "#,0", "Match (real data)"),
    ("Match Loads", "HSR per 90 (m)",
     "DIVIDE(SUM('Match Loads'[hsr_distance_m]), SUM('Match Loads'[minutes])) * 90", "#,0", "Match (real data)"),
]

RELATIONSHIPS = [("Sessions", "Player", "Players", "Player"), ("Daily Load", "Player", "Players", "Player"),
                 ("Wellness", "Player", "Players", "Player"), ("Injuries", "Player", "Players", "Player"),
                 ("Match Loads", "Player", "Players", "Player"), ("Sessions", "Date", "Date", "Date"),
                 ("Daily Load", "Date", "Date", "Date"), ("Wellness", "Date", "Date", "Date")]


def indent(text: str, tabs: int) -> str:
    return "\n".join("\t" * tabs + line for line in text.splitlines())


def column_tmdl(table, name, typ, hidden, extra=()) -> str:
    lines = [f"\tcolumn {q(name)}", f"\t\tdataType: {TYPES[typ][0]}"]
    if hidden:
        lines.append("\t\tisHidden")
    if typ in FORMATS:
        lines.append(f"\t\tformatString: {FORMATS[typ]}")
    lines += [f"\t\tlineageTag: {tag(table, name)}", "\t\tsummarizeBy: none", f"\t\tsourceColumn: {name}"]
    lines += [f"\t\t{e}" for e in extra]
    lines.append("")
    if typ == "date":
        lines.append("\t\tannotation UnderlyingDateTimeDataType = Date")
    lines.append("\t\tannotation SummarizationSetBy = Automatic")
    return "\n".join(lines)


def measure_tmdl(table, name, dax, fmt, folder) -> str:
    lines = [f"\tmeasure {q(name)} = ```", indent(dax, 3), "\t\t\t```"]
    if fmt:
        lines.append(f"\t\tformatString: {fmt}")
    lines += [f"\t\tdisplayFolder: {folder}", f"\t\tlineageTag: {tag(table, 'measure', name)}"]
    return "\n".join(lines)


def csv_m(spec) -> str:
    cols = spec["columns"]
    keep = ", ".join(f'"{c[0]}"' for c in cols)
    types = ", ".join(f'{{"{c[0]}", {TYPES[c[2]][1]}}}' for c in cols)
    renames = ", ".join(f'{{"{c[0]}", "{c[1]}"}}' for c in cols if c[0] != c[1])
    steps = [
        f'    Source = Csv.Document(File.Contents(DataFolder & "{spec["csv"]}"), '
        '[Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
        "    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
        f"    Kept = Table.SelectColumns(Headers, {{{keep}}}),",
        f'    Typed = Table.TransformColumnTypes(Kept, {{{types}}}, "en-US"),',
        f"    Renamed = Table.RenameColumns(Typed, {{{renames}}})" if renames else "    Renamed = Typed",
    ]
    last = "Renamed"
    if spec.get("md_order"):
        steps[-1] += ","
        steps.append(MD_ORDER_STEP)
        last = "WithOrder"
    return "let\n" + "\n".join(steps) + f"\nin\n    {last}"


def table_tmdl(name, spec) -> str:
    parts = [f"table {q(name)}", f"\tlineageTag: {tag(name)}", ""]
    for _, col, typ, hidden in spec["columns"]:
        extra = ["sortByColumn: md_order"] if spec.get("md_order") and col == "MD Code" else ()
        parts += [column_tmdl(name, col, typ, hidden, extra=extra), ""]
    if spec.get("md_order"):
        parts += [column_tmdl(name, "md_order", "int", True), ""]
    for t, mname, dax, fmt, folder in MEASURES:
        if t == name:
            parts += [measure_tmdl(t, mname, dax, fmt, folder), ""]
    parts += [f"\tpartition {q(name)} = m", "\t\tmode: import", "\t\tsource =", indent(csv_m(spec), 4), ""]
    return "\n".join(parts)


def date_tmdl() -> str:
    cols = [("Date", "date", False, ["isKey"]), ("Week Start", "date", False, []),
            ("Weekday", "text", False, ["sortByColumn: 'Weekday No'"]), ("Weekday No", "int", True, []),
            ("Month", "text", False, ["sortByColumn: 'Month No'"]), ("Month No", "int", True, [])]
    parts = ["table 'Date'", f"\tlineageTag: {tag('Date')}", "\tdataCategory: Time", ""]
    for col, typ, hidden, extra in cols:
        parts += [column_tmdl("Date", col, typ, hidden, extra=extra), ""]
    parts += ["\tpartition 'Date' = m", "\t\tmode: import", "\t\tsource =", indent(DATE_M, 4), ""]
    return "\n".join(parts)


def check_names():
    """Power BI names are case-insensitive: a measure can't share a name with any measure or column."""
    cols = {col.lower() for spec in TABLES.values() for _, col, _, _ in spec["columns"]} | {"md_order"}
    seen = set()
    for _, name, *_ in MEASURES:
        key = name.lower()
        if key in cols or key in seen:
            raise SystemExit(f"Name clash (case-insensitive): measure '{name}'")
        seen.add(key)


def build_model():
    check_names()
    d = MODEL / "definition"
    shutil.rmtree(d, ignore_errors=True)
    (d / "tables").mkdir(parents=True)
    write_json(MODEL / "definition.pbism", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.2", "settings": {"qnaEnabled": False}})
    (d / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1601\n\n", encoding="utf-8")
    order = ["DataFolder", *TABLES, "Date"]
    refs = "\n".join(f"ref table {q(t)}" for t in [*TABLES, "Date"])
    (d / "model.tmdl").write_text(
        "model Model\n\tculture: en-US\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
        "\tdiscourageImplicitMeasures\n\tsourceQueryCulture: en-US\n\tdataAccessOptions\n"
        "\t\tlegacyRedirects\n\t\treturnErrorValuesAsNull\n\n"
        f"annotation PBI_QueryOrder = {json.dumps(order)}\n\n"
        "annotation __PBI_TimeIntelligenceEnabled = 0\n\n" + refs + "\n", encoding="utf-8")
    (d / "expressions.tmdl").write_text(
        "/// Folder containing the CSVs written by src/pipeline.py (must end with a backslash)\n"
        f'expression DataFolder = "{DATA_FOLDER}" meta [IsParameterQuery = true, Type = "Text", '
        "IsParameterQueryRequired = true]\n"
        f"\tlineageTag: {tag('DataFolder')}\n\n\tannotation PBI_ResultType = Text\n", encoding="utf-8")
    rels = [f"relationship {tag('rel', ft, fc, tt)}\n\tfromColumn: {q(ft)}.{q(fc)}\n\ttoColumn: {q(tt)}.{q(tc)}\n"
            for ft, fc, tt, tc in RELATIONSHIPS]
    (d / "relationships.tmdl").write_text("\n".join(rels), encoding="utf-8")
    for name, spec in TABLES.items():
        (d / "tables" / f"{name}.tmdl").write_text(table_tmdl(name, spec), encoding="utf-8")
    (d / "tables" / "Date.tmdl").write_text(date_tmdl(), encoding="utf-8")


# ---------------------------------------------------------------- report
def lit(value) -> dict:
    return {"expr": {"Literal": {"Value": value}}}


def field(entity, prop, kind="Measure") -> dict:
    return {kind: {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def m(entity, prop):
    return ("Measure", entity, prop)


def c(entity, prop):
    return ("Column", entity, prop)


def projections(fields) -> dict:
    return {"projections": [{"field": field(e, p, k), "queryRef": f"{e}.{p}", "nativeQueryRef": p}
                            for k, e, p in fields]}


def visual(name, vtype, pos, roles=None, text=None, sort=None, objects=None, title=None, totals=True):
    x, y, w, h = pos
    v = {"visualType": vtype}
    if roles:
        v["query"] = {"queryState": {role: projections(fs) for role, fs in roles.items()}}
        if sort:
            (k, e, p), direction = sort
            v["query"]["sortDefinition"] = {"sort": [{"field": field(e, p, k), "direction": direction}]}
    if text:
        v["objects"] = {"general": [{"properties": {"paragraphs": [
            {"textRuns": [{"value": t, "textStyle": style}]} for t, style in text]}}]}
    if objects:
        v.setdefault("objects", {}).update(objects)
    if not totals:
        v.setdefault("objects", {})["total"] = [{"properties": {"totals": lit("false")}}]
    if title:
        v["visualContainerObjects"] = {"title": [{"properties": {"show": lit("true"), "text": lit(f"'{title}'")}}]}
    v["drillFilterOtherVisuals"] = True
    return {"$schema": f"{SCHEMA}/visualContainer/2.9.0/schema.json", "name": name,
            "position": {"x": x, "y": y, "z": 0, "height": h, "width": w, "tabOrder": 0}, "visual": v}


H1 = {"fontSize": "20pt", "fontWeight": "bold", "color": "#1F2933"}
SUB = {"fontSize": "11pt", "color": "#52606D"}
BODY = {"fontSize": "12pt", "color": "#1F2933"}


def header(title_text, subtitle):
    return [visual("title", "textbox", (20, 5, 900, 58), text=[(title_text, H1)]),
            visual("subtitle", "textbox", (20, 58, 900, 36), text=[(subtitle, SUB)])]


def dropdown_slicer(name, pos, fld, default):
    """Single-select dropdown with a preselected value (slicers store their selection as a filter)."""
    _, entity, prop = fld
    selected = {"Version": 2, "From": [{"Name": "s", "Entity": entity, "Type": 0}], "Where": [{"Condition": {"In": {
        "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": prop}}],
        "Values": [[{"Literal": {"Value": f"'{default}'"}}]]}}}]}
    return visual(name, "slicer", pos, roles={"Values": [fld]}, objects={
        "data": [{"properties": {"mode": lit("'Dropdown'")}}],
        "selection": [{"properties": {"singleSelect": lit("true")}}],
        "general": [{"properties": {"filter": {"filter": selected}}}]})


ACWR_BG = {"values": [{
    "properties": {"backColor": {"solid": {"color": {"expr": field("Daily Load", "ACWR Colour")}}}},
    "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": "Daily Load.ACWR"}}]}

PAGES = [
    ("morning", "Morning Report", [
        *header("Squad Morning Report",
                "Status per player on the report date (last date selected in the slicer; defaults to the latest day)."),
        visual("dateSlicer", "slicer", (940, 10, 320, 75), roles={"Values": [c("Date", "Date")]}),
        visual("kpis", "cardVisual", (20, 95, 1240, 105), roles={"Data": [
            m("Daily Load", "Report Date"), m("Injuries", "Available Players"), m("Injuries", "Injured Players"),
            m("Daily Load", "Players High ACWR"), m("Daily Load", "Players Low ACWR")]}),
        visual("statusTable", "tableEx", (20, 215, 1240, 490), roles={"Values": [
            c("Players", "Player"), c("Players", "Position"), m("Injuries", "Availability"),
            m("Daily Load", "ACWR"), m("Daily Load", "ACWR Status"), m("Daily Load", "ACWR (EWMA)"),
            m("Daily Load", "Acute Load (7d)"), m("Daily Load", "Chronic Load (28d)"),
            m("Wellness", "Sleep"), m("Wellness", "Fatigue"), m("Wellness", "Soreness")]},
            sort=(m("Daily Load", "ACWR"), "Descending"), objects=ACWR_BG, title="Player status", totals=False),
    ]),
    ("profile", "Player Profile", [
        *header("Player Profile", "Pick a player. ACWR bands: below 0.8 = low, 0.8 to 1.5 = normal, 1.5 and above = high."),
        dropdown_slicer("playerSlicer", (940, 10, 320, 75), c("Players", "Player"), default="G1-08"),
        visual("kpis", "cardVisual", (20, 95, 1240, 100), roles={"Data": [
            m("Sessions", "Distance (km)"), m("Sessions", "Matches Played"), m("Sessions", "Session Count"),
            m("Sessions", "Top Speed (m/s)"), m("Injuries", "Days Injured")]}),
        visual("loadAcwr", "lineClusteredColumnComboChart", (20, 210, 830, 290), roles={
            "Category": [c("Date", "Date")], "Y": [m("Daily Load", "Daily sRPE (AU)")],
            "Y2": [m("Daily Load", "ACWR"), m("Daily Load", "ACWR Upper Band"), m("Daily Load", "ACWR Lower Band")]},
            title="Daily load (sRPE) and ACWR"),
        visual("wellness", "lineChart", (20, 510, 830, 195), roles={
            "Category": [c("Date", "Date")], "Y": [m("Wellness", "Wellness Score")]},
            title="Wellness score (1-5, higher is better)"),
        visual("injuries", "tableEx", (870, 210, 390, 495), roles={"Values": [
            c("Injuries", "Injury Date"), c("Injuries", "Return Date"), m("Injuries", "Days Out")]},
            title="Injury history"),
    ]),
    ("periodization", "Weekly Periodization", [
        *header("Weekly Periodization", "How load is distributed across the week relative to match day (MD)."),
        visual("mdDistance", "clusteredColumnChart", (20, 95, 405, 285), roles={
            "Category": [c("Sessions", "MD Code")], "Y": [m("Sessions", "Avg Distance per Session (m)")]},
            sort=(c("Sessions", "MD Code"), "Ascending"), title="Avg distance by matchday code"),
        visual("mdHsr", "clusteredColumnChart", (437, 95, 405, 285), roles={
            "Category": [c("Sessions", "MD Code")], "Y": [m("Sessions", "Avg HSR per Session (m)")]},
            sort=(c("Sessions", "MD Code"), "Ascending"), title="Avg high-speed running by matchday code"),
        visual("mdSrpe", "clusteredColumnChart", (855, 95, 405, 285), roles={
            "Category": [c("Sessions", "MD Code")], "Y": [m("Sessions", "Avg sRPE per Session")]},
            sort=(c("Sessions", "MD Code"), "Ascending"), title="Avg sRPE by matchday code"),
        visual("weeklyMatrix", "pivotTable", (20, 395, 830, 310), roles={
            "Rows": [c("Players", "Player")], "Columns": [c("Date", "Week Start")], "Values": [m("Sessions", "sRPE (AU)")]},
            title="Weekly sRPE per player"),
        visual("squadTrend", "lineChart", (870, 395, 390, 310), roles={
            "Category": [c("Date", "Week Start")], "Y": [m("Sessions", "Squad Avg sRPE (AU)")]},
            title="Squad average weekly sRPE"),
    ]),
    ("match", "Match Physical Report", [
        *header("Match Physical Report",
                "Source: Metrica Sports open tracking data (real). All other pages use the simulated season."),
        visual("distance", "clusteredBarChart", (20, 95, 405, 300), roles={
            "Category": [c("Players", "Player")], "Y": [m("Match Loads", "Match Distance (km)")]},
            sort=(m("Match Loads", "Match Distance (km)"), "Descending"), title="Total distance (km)"),
        visual("hsr", "clusteredBarChart", (437, 95, 405, 300), roles={
            "Category": [c("Players", "Player")], "Y": [m("Match Loads", "Match HSR (m)")]},
            sort=(m("Match Loads", "Match HSR (m)"), "Descending"), title="High-speed running (m)"),
        visual("profiles", "scatterChart", (855, 95, 405, 300), roles={
            "Category": [c("Players", "Player")], "X": [m("Match Loads", "Distance per 90 (m)")],
            "Y": [m("Match Loads", "HSR per 90 (m)")]}, title="Running profile: distance vs HSR per 90"),
        visual("matchTable", "tableEx", (20, 410, 1240, 295), roles={"Values": [
            c("Players", "Player"), c("Players", "Position"), m("Match Loads", "Match Minutes"),
            m("Match Loads", "Match Distance (km)"), m("Match Loads", "Match HSR (m)"),
            m("Match Loads", "Match Sprint Efforts"), m("Match Loads", "Match Accels + Decels"),
            m("Match Loads", "Match Top Speed (m/s)")]},
            sort=(m("Match Loads", "Match Distance (km)"), "Descending"), title="Match physical outputs", totals=False),
    ]),
    ("about", "About the Data", [
        visual("title", "textbox", (20, 5, 900, 58), text=[("About the Data", H1)]),
        visual("notes", "textbox", (20, 75, 1240, 625), text=[(t, BODY) for para in [p for p in [
            "REAL: match physical profiles (distance, high-speed running, sprints, accelerations, top speed) "
            "computed from Metrica Sports open 25 Hz tracking data, 2 matches, 26 players.",
            "SIMULATED: the 30-week season (training, matches, sRPE, wellness, injuries), calibrated from each "
            "player's real per-90 output. Injuries are random, so no load-injury relationship here is real evidence.",
            "HSR = distance at 5.5 m/s or faster. Sprint = 7.0 m/s or faster for at least 1 s. "
            "Accel/decel = +/-3 m/s2 for at least 0.5 s. sRPE = session RPE x minutes.",
            "ACWR = 7-day mean load / 28-day mean load (EWMA version also shown). ACWR is a communication tool "
            "for sudden load changes, not an injury predictor (Impellizzeri et al. 2020).",
            "Pipeline: Python (pandas) -> SQLite -> Power BI. Code: github.com/Lizard-Creator/athlete-monitoring",
        ]] for t in (para, " ")][:-1]),
    ]),
]

THEME = {
    "name": "Athlete Monitoring",
    "dataColors": ["#1F4E79", "#2A9D8F", "#E9A23B", "#C8553D", "#6C757D", "#8AB17D", "#5B8DB8", "#264653"],
    "background": "#FFFFFF", "foreground": "#1F2933", "tableAccent": "#1F4E79",
    "good": "#388E3C", "neutral": "#F9A825", "bad": "#D32F2F",
}


def build_report():
    d = REPORT / "definition"
    shutil.rmtree(d, ignore_errors=True)
    write_json(REPORT / "definition.pbir", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}})
    write_json(d / "version.json", {"$schema": f"{SCHEMA}/versionMetadata/1.0.0/schema.json", "version": "2.0.0"})
    ver = {"visual": "2.9.0", "report": "3.3.0", "page": "2.1.0"}
    write_json(d / "report.json", {
        "$schema": f"{SCHEMA}/report/3.3.0/schema.json",
        "themeCollection": {
            "baseTheme": {"name": "CY24SU10", "reportVersionAtImport": ver, "type": "SharedResources"},
            "customTheme": {"name": "theme.json", "reportVersionAtImport": ver, "type": "RegisteredResources"}},
        "resourcePackages": [
            {"name": "SharedResources", "type": "SharedResources",
             "items": [{"name": "CY24SU10", "path": "BaseThemes/CY24SU10.json", "type": "BaseTheme"}]},
            {"name": "RegisteredResources", "type": "RegisteredResources",
             "items": [{"name": "theme.json", "path": "theme.json", "type": "CustomTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True,
                     "allowChangeFilterTypes": True, "useEnhancedTooltips": True}})
    write_json(d / "pages" / "pages.json", {"$schema": f"{SCHEMA}/pagesMetadata/1.1.0/schema.json",
                                            "pageOrder": [p[0] for p in PAGES], "activePageName": PAGES[0][0]})
    for name, display, visuals in PAGES:
        write_json(d / "pages" / name / "page.json", {
            "$schema": f"{SCHEMA}/page/2.1.0/schema.json", "name": name, "displayName": display,
            "displayOption": "FitToPage", "height": 720, "width": 1280})
        for i, v in enumerate(visuals):  # stack + tab order follow list order
            v["position"]["z"] = v["position"]["tabOrder"] = i * 1000
            write_json(d / "pages" / name / "visuals" / v["name"] / "visual.json", v)
    write_json(REPORT / "StaticResources" / "RegisteredResources" / "theme.json", THEME)
    base = REPORT / "StaticResources" / "SharedResources" / "BaseThemes" / "CY24SU10.json"
    if not base.exists():
        raise SystemExit(f"Missing base theme {base} (Power BI's built-in CY24SU10 theme file)")


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def main():
    build_model()
    build_report()
    write_json(HERE / f"{NAME}.pbip", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0", "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
        "settings": {"enableAutoRecovery": True}})
    print(f"Wrote {HERE / (NAME + '.pbip')}\nDataFolder parameter = {DATA_FOLDER}")


if __name__ == "__main__":
    main()
