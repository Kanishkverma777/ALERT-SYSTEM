from __future__ import annotations

import json
import operator
import sys
import time
from typing import Annotated, Literal, TypedDict

from dotenv import load_dotenv
from groq import BadRequestError, Groq, RateLimitError
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, ValidationError
from tavily import TavilyClient

import geo

load_dotenv()

# Comment out the print override to avoid recursion issues
# import builtins
# _original_print = builtins.print
# def _safe_print(*args, **kwargs):
#     try:
#         _original_print(*args, **kwargs)
#     except OSError:
#         pass
# builtins.print = _safe_print

client = Groq()  # reads GROQ_API_KEY from the environment
search_client = TavilyClient()  # reads TAVILY_API_KEY from the environment

# gpt-oss-20b for cheap/low-latency stages, 120b for the ones that need reasoning.
FAST = "openai/gpt-oss-20b"
SMART = "openai/gpt-oss-120b"


# --------------------------------------------------------------------------- #
# LLM helper
# --------------------------------------------------------------------------- #

def _retry_after(exc: RateLimitError) -> float:
    """Honour Groq's retry-after header when present."""
    response = getattr(exc, "response", None)
    if response is not None:
        value = response.headers.get("retry-after")
        if value:
            try:
                return min(float(value), 30.0)
            except ValueError:
                pass
    return 6.0


def _failed_generation(exc: BadRequestError) -> str | None:
    """Groq echoes the offending model output on a 400, when it has one."""
    body = getattr(exc, "body", None)
    if not isinstance(body, dict):
        return None
    return body.get("error", {}).get("failed_generation")


def ask(schema: type[BaseModel], system: str, user: str, model: str = SMART) -> BaseModel:
    """One Groq call constrained to `schema`.

    Retries on malformed bodies, on Groq's own JSON-validation 400s, and on
    free-tier 429s.
    """
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    last_error: Exception | None = None
    temperature = 0.0

    for _ in range(4):
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=temperature,
            )
        except RateLimitError as exc:
            last_error = exc
            time.sleep(_retry_after(exc))
            continue
        except BadRequestError as exc:  # json_validate_failed / tool_use_failed
            last_error = exc
            # gpt-oss occasionally answers with a tool call despite json_object
            # and tool_choice=none. At temperature 0 an identical resend just
            # reproduces it, so the retry has to change the sampling: raise the
            # temperature, show the model its own bad output, and state plainly
            # that no tools exist.
            temperature = max(temperature, 0.4)
            failed = _failed_generation(exc)
            if failed:
                messages.append({"role": "assistant", "content": failed})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "No tools are available to you and none may be called. "
                        f"Reply with a single {schema.__name__} JSON object, "
                        "and nothing else."
                    ),
                },
            )
            continue

        raw = completion.choices[0].message.content
        try:
            return schema.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            messages += [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"Invalid: {exc}. Reply with valid JSON only."},
            ]

    raise RuntimeError(f"Model did not return valid {schema.__name__} JSON: {last_error}")


# --------------------------------------------------------------------------- #
# Structured output schemas
# --------------------------------------------------------------------------- #

DisasterType = Literal[
    "FLOOD", "FIRE", "EARTHQUAKE", "BUILDING_COLLAPSE", "ROAD_ACCIDENT",
    "LANDSLIDE", "CYCLONE", "OTHER",
]
Need = Literal["medical", "rescue", "food", "water", "shelter", "evacuation"]


class Analysis(BaseModel):
    summary: str = Field(description="One factual sentence describing the incident")
    is_emergency: bool = Field(description="True only if this is a real, actionable incident")


class Classification(BaseModel):
    disaster_type: DisasterType


class Entities(BaseModel):
    location: str = Field(description="Place name, or 'Unknown'")
    people_affected: int | None = Field(
        description="Number of people affected or trapped, when the report gives a "
        "number; null when it does not; 0 only if the report explicitly says nobody was"
    )
    people_reported: bool = Field(
        description="True if the report mentions affected or trapped people at all, "
        "even without giving a number (e.g. 'several people may be trapped')"
    )
    injured: int | None = Field(
        description="Number of injured people, when the report gives a number; null "
        "when it does not; 0 only if the report explicitly says nobody was injured"
    )
    injuries_reported: bool = Field(
        description="True if the report mentions injuries at all, even without giving "
        "a number (e.g. 'multiple students are injured')"
    )
    killed: int | None = Field(
        description="Number of people killed or fatalities, when the report gives a number; null "
        "when it does not; 0 only if explicitly said nobody was killed"
    )
    fatalities_reported: bool = Field(
        description="True if the report mentions deaths or fatalities at all, even without giving "
        "a number (e.g. 'several people have died')"
    )
    needs: list[Need] = Field(description="Assistance required, from the allowed values only")


class SeverityAssessment(BaseModel):
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    reasoning: str = Field(description="One short sentence")


class ActionPlan(BaseModel):
    actions: list[str] = Field(description="3-6 short recommended steps, most urgent first")


# --------------------------------------------------------------------------- #
# Shared state
# --------------------------------------------------------------------------- #

class State(TypedDict):
    report: str
    summary: str
    is_emergency: bool
    disaster_type: str
    location: str
    lat: float | None
    lon: float | None
    location_context: str  # district/state/country from reverse geocode
    people_affected: int | None    # None = not reported; 0 = explicitly nobody
    people_reported: bool          # mentioned at all, number or not
    injured: int | None
    injuries_reported: bool
    killed: int | None
    fatalities_reported: bool
    needs: list[str]
    severity: str
    severity_reasoning: str
    priority: str
    resources: Annotated[list[dict], operator.add]  # parallel branches append here
    plan: list[str]
    response: str


def _count(value: int | None, reported: bool) -> str:
    """Render a count without ever collapsing 'unknown' into 'zero'."""
    if value is not None:
        return str(value)
    return "reported, count unknown" if reported else "not reported"


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #

def analyze(state: State) -> dict:
    result = ask(
        Analysis,
        "You are the intake analyst for a disaster-response system. "
        "Read the report and return JSON with `summary` (one factual sentence) "
        "and `is_emergency` (true only if it describes a real, actionable incident).",
        state["report"],
        model=SMART,
    )
    print(f"[analyze]  {result.summary}")
    return {"summary": result.summary, "is_emergency": result.is_emergency}


def route_is_emergency(state: State) -> str:
    """Conditional edge — the graph itself decides whether this is worth triaging."""
    return "classify" if state["is_emergency"] else "not_emergency"


def not_emergency(state: State) -> dict:
    """Short-circuit: not an actionable incident, so nothing gets dispatched."""
    print("[route]    not an actionable emergency — stopping here")
    response = "\n".join(
        [
            "ℹ️  No Emergency Detected",
            "",
            f"Report: {state['summary']}",
            "",
            "Navjeevan triages flood, fire, earthquake, building collapse, road "
            "accident, landslide and cyclone incidents. This report does not "
            "describe an actionable emergency, so no resources were dispatched.",
            "",
            "Status: No action taken.",
        ]
    )
    return {"response": response}


def classify(state: State) -> dict:
    result = ask(
        Classification,
        "Classify the disaster report into exactly one category, judging by what "
        "actually happened in the incident, not by which words are most familiar.\n"
        "- BUILDING_COLLAPSE: a structure has failed or given way — building, "
        "under-construction block, wall, roof, bridge, or people trapped in rubble. "
        "A collapsed or pancaked building is BUILDING_COLLAPSE even if it is not "
        "named among the more common categories.\n"
        "- ROAD_ACCIDENT: vehicle collisions, pile-ups, a vehicle into a crowd.\n"
        "- FLOOD: inundation, waterlogging, river overflow, dam release.\n"
        "Choose the specific category whenever the report clearly matches one. "
        "Use OTHER only when no listed category fits at all — never as a default "
        f"for an incident you were not sure how to place. "
        f"Return JSON: {{\"disaster_type\": \"<{'|'.join(DisasterType.__args__)}>\"}}.",
        state["report"],
        model=FAST,
    )
    print(f"[classify] {result.disaster_type}")
    return {"disaster_type": result.disaster_type}


def extract(state: State) -> dict:
    result = ask(
        Entities,
        "Extract structured facts from the disaster report. Return JSON with "
        "`location` (string), `people_affected` (integer or null), "
        "`people_reported` (bool), `injured` (integer or null), "
        "`injuries_reported` (bool), `killed` (integer or null), "
        "`fatalities_reported` (bool) and `needs` (array from: medical, rescue, "
        "food, water, shelter, evacuation).\n"
        "COUNTING RULES — a missing number is never zero:\n"
        "- an exact number is stated -> that number\n"
        "- the report says nobody was hurt or affected -> 0\n"
        "- no number is given -> null, and never 0\n"
        "- 'multiple students are injured' -> injuries_reported true, injured null\n"
        "- 'several people may be trapped' -> people_reported true, "
        "people_affected null\n"
        "The `*_reported` flags mean people were hurt or trapped but no number was "
        "given. Set a flag false whenever a number is stated, including a stated "
        "zero — 'nobody was injured' is injured 0 with injuries_reported false. "
        "Use 'Unknown' for an absent location. Only list needs the report actually "
        "states or clearly implies.",
        state["report"],
        model=SMART,
    )
    # Geocode once here so both parallel branches share the coordinates.
    point = geo.geocode(result.location)
    where = (
        f"{point['lat']:.4f}, {point['lon']:.4f} — {point['label'][:60]}"
        if point
        else "not found — map lookup disabled"
    )

    # Reverse geocode for district/state context
    location_context = ""
    if point:
        rev = geo.reverse_geocode(point["lat"], point["lon"])
        if rev:
            parts = [p for p in [rev.get("district"), rev.get("state")] if p]
            location_context = " · ".join(parts)

    print(
        f"[extract]  location={result.location} "
        f"people={_count(result.people_affected, result.people_reported)} "
        f"injured={_count(result.injured, result.injuries_reported)} "
        f"needs={result.needs}"
    )
    print(f"[locate]   {where}")
    if location_context:
        print(f"[locate]   context: {location_context}")

    return {
        "location": result.location,
        "lat": point["lat"] if point else None,
        "lon": point["lon"] if point else None,
        "location_context": location_context,
        "people_affected": result.people_affected,
        "people_reported": result.people_reported,
        "injured": result.injured,
        "injuries_reported": result.injuries_reported,
        "killed": result.killed,
        "fatalities_reported": result.fatalities_reported,
        "needs": list(result.needs),
    }


SEVERITY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def severity(state: State) -> dict:
    """Groq proposes a severity; rules escalate it using the extracted counts."""
    people_known = state["people_affected"] is not None
    injured_known = state["injured"] is not None
    killed_known = state["killed"] is not None

    result = ask(
        SeverityAssessment,
        "You are a disaster severity assessor. Judge how urgent this incident is. "
        "Return JSON with `severity` (LOW, MEDIUM, HIGH or CRITICAL) and `reasoning`. "
        "Reserve CRITICAL for mass-casualty events: 1+ fatalities, 10+ injured, 200+ affected, "
        "or an unfolding hazard threatening a whole district. A count that is "
        "unknown is not reassurance — if injuries or trapped people are reported "
        "without numbers, treat the incident as serious rather than mild.",
        f"Report: {state['report']}\n"
        f"Extracted: {_count(state['people_affected'], state['people_reported'])} affected, "
        f"{_count(state['injured'], state['injuries_reported'])} injured, "
        f"{_count(state['killed'], state['fatalities_reported'])} killed, "
        f"at {state['location']}.",
        model=FAST,
    )

    level = result.severity
    # Rule layer. Severity = incident magnitude, so the rules own the top of the
    # scale; the model's read is the floor and hard signals push it up.
    mass_casualty = (injured_known and state["injured"] >= 10) or (
        people_known and state["people_affected"] >= 200
    ) or (killed_known and state["killed"] >= 1)
    ceiling = "CRITICAL" if mass_casualty else "HIGH"
    if SEVERITY_RANK[level] > SEVERITY_RANK[ceiling]:
        level = ceiling

    # An unnumbered report still counts: injuries described without a figure are
    # injuries, and people reported trapped without a figure are at risk. The
    # flags are consulted only when the count is missing, so a stated zero — or a
    # stray flag — can never escalate an incident on its own.
    injuries = (injured_known and state["injured"] > 0) or (
        state["injuries_reported"] and not injured_known
    )
    fatalities = (killed_known and state["killed"] > 0) or (
        state["fatalities_reported"] and not killed_known
    )
    crowd = (people_known and state["people_affected"] >= 50) or (
        state["people_reported"] and not people_known
    )
    at_risk = (people_known and state["people_affected"] >= 20) or (
        state["people_reported"] and not people_known
    )

    if fatalities or injuries or crowd:
        level = max(level, "HIGH", key=SEVERITY_RANK.__getitem__)

    # Priority is a separate scale: how fast we must respond, not how big it is.
    urgent = injuries or at_risk
    if level in ("HIGH", "CRITICAL") and urgent:
        priority = "CRITICAL"
    elif level in ("HIGH", "CRITICAL"):
        priority = "HIGH"
    else:
        priority = level

    # The model's rationale is written before the rules run, so if a rule moved
    # the level, say so — otherwise the reasoning contradicts the verdict.
    if level == result.severity:
        reasoning = result.reasoning
        origin = "model"
    else:
        signals = []
        if fatalities:
            signals.append(
                f"{state['killed']} killed" if killed_known
                else "fatalities reported without a count"
            )
        if injuries:
            signals.append(
                f"{state['injured']} injured" if injured_known
                else "injuries reported without a count"
            )
        if crowd:
            signals.append(
                f"{state['people_affected']} affected" if people_known
                else "affected/trapped people reported without a count"
            )
        if mass_casualty:
            signals.append("mass-casualty threshold reached")
        reasoning = (
            f"{result.reasoning} Escalated from {result.severity} to {level} "
            f"by rule: {', '.join(signals)}."
        )
        origin = f"model said {result.severity}, rule override"

    print(f"[severity] {level} (priority {priority}) — {origin}")
    return {"severity": level, "severity_reasoning": reasoning, "priority": priority}


# --------------------------------------------------------------------------- #
# Resource lookup — live web search, grounded so the LLM cannot invent a facility.
# --------------------------------------------------------------------------- #

class FoundResource(BaseModel):
    name: str = Field(description="Facility or unit name, exactly as it appears in the results")
    detail: str = Field(description="What it offers, in at most 20 words — only if the result states it")
    phone: str = Field(
        default="",
        description="Phone number exactly as a result states it, or empty if none does",
    )
    source: str = Field(description="The URL this came from")


class ResourceFindings(BaseModel):
    resources: list[FoundResource]
    note: str = Field(description="One line on coverage, or why nothing usable was found")


GROUNDING_SYSTEM = (
    "You extract real, verifiable emergency resources from web search results. "
    "STRICT RULES:\n"
    "1. Report a resource only if it is explicitly named in the search results below.\n"
    "2. Never invent a facility, phone number, bed count, team size or distance. "
    "Put a figure in `detail` only if a result actually states it.\n"
    "3. `source` is the URL you took it from. If the same facility appears in "
    "several results, prefer the most authoritative one — government, hospital, "
    "or disaster-authority domain.\n"
    "4. Never cite social media or video platforms as a source.\n"
    "5. News articles are usable when they name a specific deployable unit, "
    "control room or facility — include it and cite the article. Skip news that "
    "names no concrete, contactable resource.\n"
    "6. A facility named on a directory or listing page is still real — include it, "
    "but do not claim amenities the page does not state.\n"
    "7. Copy no placeholder or scraped junk into `detail` (e.g. 'dial #'). Keep "
    "`detail` under 20 words — summarise, never paste a paragraph. If the result "
    "says nothing beyond the name, leave `detail` empty.\n"
    "8. A result about a different region is not usable here. Do NOT take a unit "
    "named in another state and re-label it as this location's.\n"
    "9. Never append the incident's location to a unit's name unless the source "
    "itself names it that way.\n"
    "10. Prefer resources in or nearest to the stated location.\n"
    "11. If nothing usable is present, return an empty list and say so in `note`.\n"
    "12. If a result states a phone number for a resource, copy it into `phone` "
    "exactly as written. Never invent, guess, complete or reformat a number, and "
    "leave `phone` empty when no result states one — a wrong number is worse than "
    "none.\n"
    "Return JSON."
)

CATEGORY_LABEL = {
    "medical": "Nearby medical resources",
    "rescue": "Rescue teams",
}
CATEGORY_ORDER = ["medical", "rescue"]

EMERGENCY_HELPLINES = [
    {"name": "National Emergency", "number": "112", "icon": "🆘", "scope": "All emergencies"},
    {"name": "Ambulance", "number": "108", "icon": "🚑", "scope": "Medical emergency"},
    {"name": "Fire Brigade", "number": "101", "icon": "🚒", "scope": "Fire & rescue"},
    {"name": "Police", "number": "100", "icon": "🚔", "scope": "Law enforcement"},
    {"name": "Disaster Mgmt (NDMA)", "number": "1078", "icon": "⚠️", "scope": "Disaster response"},
    {"name": "Women Helpline", "number": "1091", "icon": "👩", "scope": "Women safety"},
]

# How far around the incident to look for mapped facilities.
# Medical uses a wider radius (10 km) because hospitals are sparser.
RADIUS_M: dict[str, int] = {
    "medical": 10_000,   # 10 km — cast a wider net for hospitals/pharmacies
    "rescue": 5_000,
}

# How many resources to show per category. The list is already ranked most
# capable first, so the cap keeps the nearest useful few rather than everything
# that happens to sit inside the radius.
TOP_N = 7

# "fallback" = map first, web only if the map came up empty.
# "always"   = the map cannot hold this category (teams, NGOs, helplines),
#              so web search runs regardless.
WEB_MODE = {
    "medical": "fallback",
    "rescue": "always",
}

# Queries are composed from the report's own location, region and disaster type.
# Rescue assets are dispatched regionally, so that query targets the region
# rather than the neighbourhood; the other two are genuinely local.
SEARCH_QUERY = {
    "medical": "hospitals trauma centre emergency ambulance blood bank near {loc}",
    "rescue": "{disaster} rescue NDRF SDRF control room helpline {region} DDMA district disaster management authority",
}

# If the first query returns nothing that actually names the region, try this
# broader phrasing before giving up.
FALLBACK_QUERY = {
    "medical": "hospital emergency ambulance pharmacy blood bank {loc}",
    "rescue": "{disaster} fire brigade police control room emergency helpline {region}",
}


# Social/video platforms are never a usable source for a live resource.
BLOCKED_DOMAINS = (
    "instagram.com", "facebook.com", "x.com", "twitter.com",
    "youtube.com", "tiktok.com", "pinterest.com", "quora.com",
)


def _usable(hit: dict) -> bool:
    url = hit.get("url", "").lower()
    return not any(domain in url for domain in BLOCKED_DOMAINS)


def _mentions_region(hit: dict, region: str) -> bool:
    blob = f"{hit.get('title', '')} {hit.get('content', '')}".lower()
    return region.lower() in blob


def find_resources(category: str, state: State) -> tuple[list[dict], str]:
    """Search the web for real resources, then ground an LLM extraction on the hits."""
    location = state["location"]
    if location in ("", "Unknown"):
        location = "India"
    # "Saket, Delhi" -> region "Delhi"; a bare "Delhi" stays "Delhi".
    region = location.split(",")[-1].strip() or location

    # "OTHER" is a bucket, not a search term — putting the literal in a query
    # only dilutes it, so drop it and let location and region carry the search.
    disaster = "" if state["disaster_type"] == "OTHER" else state["disaster_type"].lower()
    fields = {"loc": location, "region": region, "disaster": disaster}
    queries = [
        " ".join(SEARCH_QUERY[category].format(**fields).split()),
        " ".join(FALLBACK_QUERY[category].format(**fields).split()),
    ]

    hits: list[dict] = []
    for query in queries:
        print(f"[{category}]  searching: {query}")
        try:
            raw = search_client.search(query, max_results=5, search_depth="basic")["results"]
        except Exception as exc:
            print(f"[{category}]  search failed: {type(exc).__name__}")
            return [], f"Search unavailable ({type(exc).__name__}) — verify manually."

        # Only trust results that actually name the region: search engines
        # happily return a Nashik fire officer for a fire in Kolkata.
        hits = [h for h in raw if _usable(h) and _mentions_region(h, region)]
        if hits:
            break

    if not hits:
        print(f"[{category}]  nothing verifiable for {region!r}")
        return [], f"No result mentions {region} — cannot verify locality, check manually."

    evidence = "\n\n".join(
        f"TITLE: {h['title']}\nURL: {h['url']}\nCONTENT: {h.get('content', '')[:350]}"
        for h in hits
    )

    try:
        findings = ask(
            ResourceFindings,
            GROUNDING_SYSTEM,
            f"Incident: {state['disaster_type']} at {location}, severity {state['severity']}.\n"
            f"Looking for: {CATEGORY_LABEL[category]}.\n\n"
            f"Search results:\n{evidence}",
            model=FAST,
        )
        items = [r.model_dump() for r in findings.resources]
        detail = f" — {findings.note}" if findings.note else ""
        print(f"[{category}]  {len(items)} verified{detail}")
        return items, findings.note
    except Exception as exc:
        print(f"[{category}]  LLM extraction failed: {type(exc).__name__}: {exc}")
        return [], f"LLM extraction failed — using map results only"


def _dedupe(items: list[dict]) -> list[dict]:
    """Map and web results often name the same facility — keep the first."""
    seen: set[str] = set()
    kept = []
    for item in items:
        key = "".join(ch for ch in item["name"].lower() if ch.isalnum())[:18]
        if not key or key in seen:
            continue
        seen.add(key)
        kept.append(item)
    return kept


def _resource_node(category: str, state: State) -> dict:
    return {"resources": [_resource_entry(category, state)]}


def _resource_entry(category: str, state: State) -> dict:
    """Mapped facilities from geo.py, plus directory hits from web search.

    Where the map has the facility type (hospitals, fire stations, pharmacies)
    it wins, because it returns real coordinates and distances. Where it
    doesn't — rescue teams, NGOs, control-room helplines — web search carries
    the load.
    """
    items: list[dict] = []
    notes: list[str] = []

    radius = RADIUS_M.get(category, 5_000)

    if state.get("lat") is not None and geo.POI_TYPES.get(category):
        mapped = geo.nearby(state["lat"], state["lon"], geo.POI_TYPES[category], radius_m=radius)
        items += mapped
        notes.append(
            f"{len(mapped)} mapped within {radius // 1000} km ({geo.provider_name()})"
            if mapped
            else f"none mapped within {radius // 1000} km"
        )
        print(f"[{category}]  {notes[-1]}")

    # "always" = the map cannot answer this category on its own.
    if WEB_MODE[category] == "always" or not items:
        web_items, web_note = find_resources(category, state)
        items += web_items
        if web_note:
            notes.append(web_note)

    items = _dedupe(items)[:TOP_N]
    return {"category": category, "items": items, "note": "; ".join(notes)}


def medical_resources(state: State) -> dict:
    return _resource_node("medical", state)


def rescue_resources(state: State) -> dict:
    return _resource_node("rescue", state)


def general_resources(state: State) -> dict:
    """Fallback when no need could be pinned down — search everything."""
    print("[resources] no specific need detected — searching all categories")
    return {"resources": [_resource_entry(c, state) for c in CATEGORY_ORDER]}


NEED_TO_BRANCH = {
    "medical": "medical_resources",
    "rescue": "rescue_resources",
    "evacuation": "rescue_resources",
}
RESOURCE_NODES = ["medical_resources", "rescue_resources", "general_resources"]


def route_needs(state: State) -> list[str]:
    """Conditional edge — fan out to resource branches (in parallel).

    Always search ALL categories so the dashboard shows a complete
    picture. Even if the report only mentions "medical", nearby fire
    stations are still useful context for the controller.
    """
    return ["medical_resources", "rescue_resources"]


# --------------------------------------------------------------------------- #
# Planning + response
# --------------------------------------------------------------------------- #

def plan(state: State) -> dict:
    rows = []
    for entry in state["resources"]:
        for item in entry["items"]:
            away = f" [{item['distance_km']} km]" if item.get("distance_km") is not None else ""
            # Mark the absence explicitly, so a missing number is never filled in
            # from memory.
            phone = f" · phone {item['phone']}" if item.get("phone") else " · no phone listed"
            rows.append(
                f"- {CATEGORY_LABEL[entry['category']]}: {item['name']}{away} — "
                f"{item['detail']}{phone}"
            )
    found = "\n".join(rows) or "- none found — plan must rely on standard protocol, not named resources"

    result = ask(
        ActionPlan,
        "You are an emergency action planner advising a human controller in a "
        "disaster-response cell. Return JSON with `actions`: 3-6 short steps, most "
        "urgent first.\n"
        "These are RECOMMENDATIONS. This system has contacted nobody and dispatched "
        "nothing. Begin every step with one of these verbs, and no other: Contact, "
        "Request, Recommend, Confirm, Coordinate, Verify, Prepare, Establish.\n"
        "Never use a dispatch word in ANY grammatical form — verb, noun or "
        "participle. That rules out contact/contacted, alert, "
        "notify/notification, dispatch, deploy/deployment, "
        "mobilise/mobilisation, activate/activation, arrange, reserve, task, "
        "send and ready. 'Notify the NDRF to mobilise teams', 'Activate the "
        "helpline' and 'request immediate deployment of the fire stations' are "
        "all forbidden; write 'Contact the NDRF control room to request "
        "search-and-rescue support' instead. Present a resource as found or "
        "verified, never as engaged or on its way.\n"
        "NEVER invent an operational fact. No counts of ambulances or rescue teams, "
        "no number, condition or criticality of patients, no hospital or ambulance "
        "availability, no bed capacity, no named officials, no unit or team name "
        "beyond the verified list, and no claim that anyone was notified.\n"
        "You have exactly three admissible sources: (1) facts stated in the incident "
        "report, (2) entries in the verified resource list, (3) safe recommendations "
        "built from those two. Where a step needs something you do not have — how "
        "many people are trapped, whether a facility can accept patients — say it is "
        "unknown and make the step confirm it instead of guessing.\n"
        "Name a specific facility ONLY if it appears in the verified resource list. "
        "If a category is empty, write the step as a capability to request through "
        "the district control room — never fill the gap with an organisation you "
        "happen to know of.\n"
        "Match the resource to the job. A hospital handles casualties; a clinic, "
        "dispensary or wellness centre does not, so never send trauma cases to one — "
        "if the nearest entry is a clinic, recommend it only for what a clinic can "
        "do and say its capability must be confirmed.\n"
        "Where the verified list gives a phone number, quote it exactly in the step "
        "so the controller can dial it. Where it says no phone is listed, do not "
        "supply one — recommend looking the number up instead.",
        f"Incident: {state['summary']}\n"
        f"Type: {state['disaster_type']}, Severity: {state['severity']}, "
        f"Priority: {state['priority']}\n"
        f"Location: {state['location']}\n"
        f"People affected: {_count(state['people_affected'], state['people_reported'])}\n"
        f"Injured: {_count(state['injured'], state['injuries_reported'])}\n"
        f"Reported needs: {', '.join(state['needs']) or 'unspecified'}\n"
        f"Verified resources — located by search, NOT contacted:\n{found}",
        model=SMART,
    )
    print(f"[plan]     {len(result.actions)} actions drafted")
    return {"plan": list(result.actions)}


ASSISTANCE_LABEL = {
    "medical": "🚑 Medical",
    "rescue": "🚒 Rescue",
    "food": "🍱 Food",
    "water": "💧 Drinking Water",
    "shelter": "🏠 Shelter",
    "evacuation": "🚶 Evacuation",
}
NEED_ORDER = list(ASSISTANCE_LABEL)


def respond(state: State) -> dict:
    """Assemble the final report — deterministic layout, LLM-authored actions."""
    lines = [
        "🚨 Disaster Incident Analysis",
        "",
        f"Disaster Type: {state['disaster_type'].title()}",
        f"Location: {state['location']}",
        f"People Affected: {_count(state['people_affected'], state['people_reported'])}",
        f"Injured: {_count(state['injured'], state['injuries_reported'])}",
        f"Severity: {state['severity']}",
        "",
        "Required Assistance:",
    ]

    needs = sorted(set(state["needs"]), key=NEED_ORDER.index)
    for need in needs:
        lines.append(f"→ {ASSISTANCE_LABEL[need]}")

    resources = sorted(state["resources"], key=lambda r: CATEGORY_ORDER.index(r["category"]))
    lines += [
        "",
        f"Resource Search ({geo.provider_name()} + live web search) — located, "
        "not contacted:",
    ]
    for entry in resources:
        lines.append(f"→ {CATEGORY_LABEL[entry['category']]}")
        if not entry["items"]:
            lines.append(f"   ⚠️  nothing verified — {entry['note']}")
            continue
        for item in entry["items"]:
            away = f"  [{item['distance_km']} km]" if item.get("distance_km") is not None else ""
            detail = f" — {item['detail']}" if item["detail"] else ""
            phone = f"  ☎ {item['phone']}" if item.get("phone") else ""
            lines.append(f"   • {item['name']}{away}{detail}{phone}")
            if item["source"]:
                lines.append(f"     {item['source']}")

    lines += ["", f"Priority: {state['priority']}", "", "Recommended Action:"]
    lines += [f"{i}. {action}" for i, action in enumerate(state["plan"], 1)]
    lines += [
        "",
        "Note: the resources above were located by live search. None of them has "
        "been contacted, alerted or dispatched, and no availability has been "
        "confirmed — contact them directly to verify.",
    ]

    status = (
        "Emergency response required."
        if state["priority"] in ("HIGH", "CRITICAL")
        else "Monitoring advised — no immediate deployment."
    )
    lines += ["", f"Status: {status}"]

    response = "\n".join(lines)
    return {"response": response}


# --------------------------------------------------------------------------- #
# Graph
# --------------------------------------------------------------------------- #

builder = StateGraph(State)

builder.add_node("analyze", analyze)
builder.add_node("not_emergency", not_emergency)
builder.add_node("classify", classify)
builder.add_node("extract", extract)
builder.add_node("severity", severity)
for node in RESOURCE_NODES:
    builder.add_node(node, globals()[node])
builder.add_node("plan", plan)
builder.add_node("respond", respond)

builder.add_edge(START, "analyze")
builder.add_conditional_edges("analyze", route_is_emergency, ["classify", "not_emergency"])
builder.add_edge("not_emergency", END)
builder.add_edge("classify", "extract")
builder.add_edge("extract", "severity")

builder.add_conditional_edges("severity", route_needs, RESOURCE_NODES)

for node in RESOURCE_NODES:
    builder.add_edge(node, "plan")

builder.add_edge("plan", "respond")
builder.add_edge("respond", END)

graph = builder.compile()


# --------------------------------------------------------------------------- #

BANNER = """
╭──────────────────────────────────────────────────────────────────────╮
│                      NAV JEEVAN ALERT SYSTEM                         │
╰──────────────────────────────────────────────────────────────────────╯
"""


def run_pipeline(report: str) -> str:
    """Run one report through the graph and print the result."""
    print("-" * 70)
    result = graph.invoke({"report": report, "resources": []})
    print("-" * 70)
    print(result["response"])
    return result["response"]


def main() -> None:
    argv = sys.argv[1:]

    if "--graph" in argv:
        print(graph.get_graph().draw_mermaid())
        return

    words = [a for a in argv if not a.startswith("-")]
    if words:  # one-shot: python navjeevan.py "flood in Delhi"
        run_pipeline(" ".join(words))
        return

    print(BANNER)
    while True:
        try:
            query = input(" REPORT -› ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not query:
            continue
        if query.lower() in {"quit", "exit", "q"}:
            print("Bye.")
            break

        try:
            run_pipeline(query)
        except Exception as exc:  # one bad report shouldn't kill the session
            print(f"\n⚠️  Pipeline error: {type(exc).__name__}: {exc}")
            print("   Try rephrasing the report.")


if __name__ == "__main__":
    main()
