"""Load-based sizing in 10 tiers. Everything here is a RULE OF THUMB, not a measurement, and the report says so.
The user's traffic answer is turned into a peak request rate (assumptions are printed), the rate picks one of 10 tiers,
and each tier is priced with the same price engine as the rest of the report.

Assumptions (all printed in the report):
- one monthly active user makes about 20 requests per day (600 per month); one daily active user about 20 per day
- busiest hour vs average: from the user's answer (1-2x -> 2, 3-5x -> 5, 10x or more -> 10, unknown -> 5)
- one vCPU of a typical web/API service handles about 100 requests per second at 70% CPU
- every service is sized as if it sees the full request rate (upper bound: backends usually see less)
- pods stay at the repo's own size up to 4 copies; beyond that the smallest of 0.25 / 0.5 / 1 / 2 vCPU that needs 4 or fewer copies (memory = 1 GiB per vCPU, never below the repo's own)
"""
import math
import re

REQ_PER_USER_DAY = 20
RPS_PER_VCPU = 100
SMALL_POD_MAX_COPIES = 4          # scale out at the repo's own pod size up to this many copies, then use bigger pods
MAX_REPLICAS = 100

# (tier number, short name, highest peak requests/second that still belongs to the tier, representative rate used for pricing)
TIERS = [
    (1, "Tiny", 0.5, 0.5), (2, "Small", 2, 2), (3, "Light", 5, 5), (4, "Moderate", 15, 15), (5, "Busy", 40, 40),
    (6, "High", 100, 100), (7, "Heavy", 250, 250), (8, "Very heavy", 600, 600), (9, "Large", 1500, 1500), (10, "Very large", float("inf"), 3000),
]
_NUM = re.compile(r"(\d[\d,._]*)\s*(k|m|million|thousand)?(?![a-z])", re.I)
_PER = {"second": 2592000, "sec": 2592000, "s": 2592000, "minute": 43200, "min": 43200, "hour": 720, "hr": 720, "day": 30, "week": 30 / 7, "month": 1, "year": 1 / 12}


def _num(txt, suf):
    try:
        v = float(txt.replace(",", "").replace("_", ""))
    except ValueError:
        return None
    return v * {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6}.get((suf or "").lower(), 1)


def _ans(answers, needle):
    for q, a in (answers or {}).items():
        if needle in str(q).lower() and str(a).strip():
            return str(a).strip()
    return ""


def peak_multiplier(answers):
    a = _ans(answers, "busier is your busiest").lower()
    if "10x" in a or "spiky" in a:
        return 10, "10 (you said spiky, 10x or more)"
    if "3-5" in a or "busy hours" in a:
        return 5, "5 (you said busy hours, 3-5x)"
    if "1-2" in a or "about the same" in a:
        return 2, "2 (you said about the same, 1-2x)"
    return 5, "5 (assumed: you gave no usable answer)"


def monthly_growth(answers):
    a = _ans(answers, "growth per month").lower()
    if not a:
        return None
    if "flat" in a:
        return 0.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", a)
    return float(m.group(1)) / 100 if m else None


def _one(low, n, rest):
    """(per_month, how) for one number and the words after it, or None."""
    unit = next((u for u in sorted(_PER, key=len, reverse=True) if re.search(r"(?:/|\bper\b|\ba\b|\beach\b|\bevery\b)\s*" + u + r"\b", rest)), None)
    if re.search(r"^\s*(?:rps|req/s)\b", rest):
        return n * 2592000, f"{n:g} requests per second as stated", "request"
    if re.match(r"\s*(?:\w+\s+){0,2}?(?:requests?|reqs?|calls?|hits?|page ?views?)\b", rest):
        if not unit:
            return None
        return n * _PER[unit], f"{n:,.0f} requests per {unit} as stated", "request"
    if re.match(r"\s*(?:\w+\s+){0,1}?(?:daily active|dau)\b", rest):
        return n * REQ_PER_USER_DAY * 30, f"{n:,.0f} daily active users x {REQ_PER_USER_DAY} requests per day (assumption)", "user"
    if re.match(r"\s*(?:\w+\s+){0,2}?(?:users?|mau|customers?|visitors?|sessions?)\b", rest):
        if unit == "day":
            return n * REQ_PER_USER_DAY * 30, f"{n:,.0f} users per day x {REQ_PER_USER_DAY} requests per day (assumption)", "user"
        return n * REQ_PER_USER_DAY * 30, f"{n:,.0f} monthly users x {REQ_PER_USER_DAY * 30} requests per month (assumption: {REQ_PER_USER_DAY} per day)", "user"
    return None


def parse_load(answers):
    """Returns dict(text, per_month, how) or None when no usable number is in the traffic answer.
    When the answer holds both a request figure and a user figure ("3000 users and 10000 requests per month"), the request figure wins."""
    text = _ans(answers, "include the unit") or _ans(answers, "real traffic")
    low = text.lower()
    if not text or "don't know" in low:
        return None
    found = []
    for m in _NUM.finditer(low):
        n = _num(m.group(1), m.group(2))
        if not n or n <= 0:
            continue
        r = _one(low, n, low[m.end():m.end() + 60])
        if r:
            found.append(r)
    if not found:
        return None
    best = next((f for f in found if f[2] == "request"), found[0])
    return {"text": text, "per_month": best[0], "how": best[1]}


def rate_text(rps):
    if rps < 0.1:
        return f"{rps * 86400:,.0f} requests/day"
    return f"{rps:.1f} requests/second" if rps < 10 else f"{rps:.0f} requests/second"


def tier_of(peak_rps):
    for t in TIERS:
        if peak_rps <= t[2]:
            return t
    return TIERS[-1]


def _pods(w, rps, min_rep):
    """(cpu, mem, replicas) for one stateless service at a request rate."""
    need_small = math.ceil(rps / (RPS_PER_VCPU * max(w["cpu_cores"], 0.05)))
    if need_small <= max(min_rep, SMALL_POD_MAX_COPIES):
        return w["cpu_cores"], w["memory_gib"], max(min_rep, need_small)
    for cpu in (0.25, 0.5, 1.0, 2.0):             # smallest bigger pod that keeps the number of copies at 4 or fewer
        if cpu > w["cpu_cores"] and math.ceil(rps / (RPS_PER_VCPU * cpu)) <= SMALL_POD_MAX_COPIES:
            return cpu, max(w["memory_gib"], cpu), max(min_rep, math.ceil(rps / (RPS_PER_VCPU * cpu)))
    cpu = 2.0
    return cpu, max(w["memory_gib"], cpu), min(MAX_REPLICAS, max(min_rep, math.ceil(rps / (RPS_PER_VCPU * cpu))))


def price_tier(rps, plan, workloads, ce):
    """Total EUR/month for one tier on the platform of the chosen plan, plus pods per service. Uses the planner's own totals for fixed parts."""
    o = plan["chosen"]
    fn = ce._autopilot if o["platform"] == "gke_autopilot" else ce._cloud_run_always_on
    stateful = set(o.get("stateful_kept_single") or [])
    pods, usd, shown = {}, 0.0, []
    for n in o["service_names"]:
        w = workloads.get(n)
        if not w:
            continue
        if n in stateful:
            usd += fn(dict(w, replicas=1))
            continue
        cpu, mem, r = _pods(w, rps, o["replicas"])
        usd += fn(dict(w, cpu_cores=cpu, memory_gib=mem, replicas=r))
        pods[n] = (cpu, mem, r)
        shown.append(r)
    base_compute = ce._eur(sum(fn(dict(workloads[n], replicas=1)) * (1 if n in stateful else o["replicas"]) for n in o["service_names"] if n in workloads))
    other = plan["total"] - base_compute               # cluster fee + load balancer + database/Redis extras, exactly as the plan priced them
    return round(ce._eur(usd) + other, 2), pods, (min(shown) if shown else 0, max(shown) if shown else 0)


def section(answers, plan, scan_result, ce):
    """Markdown block, or '' when there is nothing to size. Raises nothing the caller cannot survive."""
    if not plan:
        return ""
    ld = parse_load(answers)
    if not ld:
        return ""
    workloads = ce._workloads(scan_result)[0]
    mult, mult_txt = peak_multiplier(answers)
    avg = ld["per_month"] / 2592000
    peak = avg * mult
    g = monthly_growth(answers)
    peak12 = peak * (1 + g) ** 12 if g is not None else None
    t_now = tier_of(peak)
    t12 = tier_of(peak12) if peak12 is not None else None

    rows, priced, capped = [], {}, False
    for num, name, hi, rep in TIERS:
        total, pods, (lo_r, hi_r) = price_tier(rep, plan, workloads, ce)
        priced[num] = total
        marks = []
        if num == t_now[0]:
            marks.append("your load at launch")
        if t12 and num == t12[0] and t12[0] != t_now[0]:
            marks.append("your load after 12 months")
        up = f"up to {hi:g}" if hi != float("inf") else "above 1,500"
        copies = f"{lo_r}" if lo_r == hi_r else f"{lo_r}-{hi_r}"
        capped = capped or hi_r >= MAX_REPLICAS
        if hi_r >= MAX_REPLICAS:
            copies += "+"
        cpus = [v[0] for v in pods.values()]
        size = (f"{min(cpus):g}" if min(cpus) == max(cpus) else f"{min(cpus):g}-{max(cpus):g}") + " vCPU" if cpus else "-"
        rows.append(f"| {num} | {name} | {up} | {copies} | {size} | {total:.2f}{'+' if hi_r >= MAX_REPLICAS else ''} | {' / '.join(marks)} |")
    L = ["## Load-based sizing (rule of thumb, not measured)", "",
         f"You said: \"{ld['text'][:100]}\". Converted: {ld['how']} = about {rate_text(avg)} on average; busiest hour x{mult_txt} = about **{rate_text(peak)} at peak** = **tier {t_now[0]} of 10 ({t_now[1]})**."]
    if t12 and peak12 > peak * 1.01:
        L.append(f"With the growth you gave, the peak after 12 months is about {rate_text(peak12)} = tier {t12[0]} ({t12[1]}).")
    L += ["", "| Tier | Name | Peak requests/second | Copies per service | Pod size | EUR/month at the top of the tier | |", "|---|---|---|---|---|---|---|"] + rows + [""]
    tot = price_tier(max(peak, 0.01), plan, workloads, ce)[0]
    tot12 = price_tier(peak12, plan, workloads, ce)[0] if peak12 is not None else None
    L.append(f"For your load at launch the {'managed-platform option' if plan.get('small_server') else 'plan'} is **{tot:.2f} EUR/month** ({plan['chosen']['label'].split(',')[0]}, same fixed parts and database/Redis choices as section 4). Section 4 prices the repo's own pod sizes; this section adjusts them to your load.")
    if plan.get("budget") is not None and not plan.get("small_server"):
        d = plan["budget"] - tot
        L.append(f"Against your budget of {plan['budget']:.0f}: " + (f"{d:.2f} under budget." if d >= 0 else f"{-d:.2f} OVER budget. Reduce scope, accept less headroom, or raise the budget."))
    if tot12 is not None and tot12 != tot:
        L.append(f"After 12 months at that growth the same setup would cost about {tot12:.2f} EUR/month.")
    if t_now[0] >= 7 or (t12 and t12[0] >= 7):
        L.append("At this load a managed database larger than the priced sizes may be needed; that is NOT included (no verified price).")
    if capped:
        L.append(f"A \"+\" means the model hit its limit of {MAX_REPLICAS} copies per service: the real need is higher, so the price is a lower bound. Load-test before trusting that tier.")
    L += ["", "How these figures were made (assumptions, not measurements): " + f"one monthly user = {REQ_PER_USER_DAY} requests/day; "
          f"one vCPU handles about {RPS_PER_VCPU} requests/second at 70% CPU; every service is sized as if it sees the full rate (an upper bound, backends usually see less); "
          f"pods keep the repo's own size up to {SMALL_POD_MAX_COPIES} copies, then the smallest of 0.25 / 0.5 / 1 / 2 vCPU that needs 4 or fewer copies (memory 1 GiB per vCPU, never below the repo's own); at most {MAX_REPLICAS} copies. "
          "A load test of your real services replaces these assumptions."]
    return "\n".join(L)
