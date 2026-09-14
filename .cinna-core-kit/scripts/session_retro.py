#!/usr/bin/env python3
"""Session retro: measure where a Claude Code session spent turns, tokens and wall-clock.

Transcripts live under ~/.claude/projects/<cwd-slug>/. A session is <id>.jsonl; its in-process
subagents are <id>/subagents/agent-*.jsonl. Agents launched with run_in_background (e.g. a manager)
are separate top-level <id>.jsonl files whose first timestamp falls inside the parent's run, so
`find` also lists sessions that overlap the window.

Subcommands
  find   [--days N] [--min-mb M] [--session ID]  list candidate transcripts (biggest first, or the
                                                  session + everything overlapping it)
  stats  FILE...                                  per-transcript turns, tokens, tools, max context,
                                                  duplicate identical calls, biggest tool results
  gaps   FILE...                                  slowest tool calls per transcript (where wall-clock went)
  narrative FILE [--max-text N] [--skip-reads]    timeline: prompts, texts, tool calls, result sizes
  reads  FILE...                                  files read repeatedly across agents + edit churn
  totals FILE...                                  token totals by model
"""
import argparse, collections, datetime, glob, json, os, sys

ROOT = os.path.expanduser("~/.claude/projects")


def slug_for_cwd(cwd: str) -> str:
    return cwd.replace("/", "-")


def project_dir() -> str:
    d = os.path.join(ROOT, slug_for_cwd(os.getcwd()))
    return d if os.path.isdir(d) else ROOT


def rows(path):
    out = []
    with open(path) as fh:
        for line in fh:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def ts(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


def span(path):
    first = last = None
    for d in rows(path):
        t = d.get("timestamp")
        if t and d.get("type") in ("assistant", "user"):
            first = first or t
            last = t
    return (ts(first), ts(last)) if first else (None, None)


def rel(p):
    return os.path.relpath(p, project_dir())


# ---------------------------------------------------------------- find
def cmd_find(a):
    pd = project_dir()
    files = glob.glob(os.path.join(pd, "*.jsonl"))
    cutoff = datetime.datetime.now().timestamp() - a.days * 86400
    files = [f for f in files if os.path.getmtime(f) >= cutoff]
    if a.session:
        main = os.path.join(pd, a.session + ".jsonl")
        f0, l0 = span(main)
        print(f"# session {a.session}: {f0} .. {l0}")
        picked = [main]
        for f in files:
            if f == main:
                continue
            f1, l1 = span(f)
            if f1 and f1 >= f0 and f1 <= l0:
                picked.append(f)
        files = picked
    else:
        files = [f for f in files if os.path.getsize(f) >= a.min_mb * 1e6]
    files.sort(key=lambda f: -os.path.getsize(f))
    for f in files:
        subs = sorted(glob.glob(f[:-6] + "/subagents/agent-*.jsonl"))
        f1, l1 = span(f)
        print(f"{os.path.getsize(f)/1e6:6.1f}MB  {f1:%Y-%m-%d %H:%M} .. {l1:%H:%M}  {rel(f)}  subagents={len(subs)}")
        for s in subs:
            print(f"        {os.path.getsize(s)/1e6:6.1f}MB  {rel(s)}")


# ---------------------------------------------------------------- stats
def analyze(path):
    tools = collections.Counter(); models = collections.Counter(); dup = collections.Counter()
    out = cr = cw = inp = n = maxctx = 0
    first = last = None; res = []; agents = []; tool_names = {}
    for d in rows(path):
        t = d.get("timestamp")
        if t and d.get("type") in ("assistant", "user"):
            first = first or t; last = t
        if d.get("type") == "assistant":
            m = d["message"]; n += 1; models[m.get("model")] += 1
            u = m.get("usage") or {}
            out += u.get("output_tokens", 0); cr += u.get("cache_read_input_tokens", 0)
            cw += u.get("cache_creation_input_tokens", 0); inp += u.get("input_tokens", 0)
            maxctx = max(maxctx, u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0))
            for c in m.get("content", []):
                if c.get("type") == "tool_use":
                    tools[c["name"]] += 1; tool_names[c["id"]] = c["name"]
                    dup[(c["name"], json.dumps(c["input"], sort_keys=True))] += 1
                    if c["name"] in ("Agent", "Task"):
                        i = c["input"]
                        agents.append((t[11:19], i.get("subagent_type"), i.get("model"), i.get("run_in_background"), i.get("description"), len(i.get("prompt", ""))))
        elif d.get("type") == "user":
            cont = d.get("message", {}).get("content")
            if isinstance(cont, list):
                for c in cont:
                    if c.get("type") == "tool_result":
                        res.append((len(json.dumps(c.get("content"))), tool_names.get(c.get("tool_use_id"), "?")))
    res.sort(reverse=True)
    dups = sorted([(v, k[0], k[1][:100]) for k, v in dup.items() if v > 1], reverse=True)
    dur = (ts(last) - ts(first)) if first else None
    return dict(turns=n, models=dict(models), dur=str(dur).split(".")[0], first=first, last=last, out=out, cache_read=cr,
                cache_write=cw, inp=inp, maxctx=maxctx, tools=dict(tools), agents=agents, dups=dups[:10],
                big=res[:6], total_result_chars=sum(r[0] for r in res))


def cmd_stats(a):
    for f in a.files:
        r = analyze(f)
        print("=" * 90); print(rel(f))
        print(f"  turns={r['turns']} models={r['models']} dur={r['dur']} ({(r['first'] or '')[11:19]}..{(r['last'] or '')[11:19]})")
        print(f"  out={r['out']:,} cache_read={r['cache_read']:,} cache_write={r['cache_write']:,} maxctx={r['maxctx']//1000}k result_chars={r['total_result_chars']:,}")
        print(f"  tools={r['tools']}")
        for ag in r["agents"]:
            print(f"  spawn {ag}")
        for dcount, name, inp in r["dups"]:
            print(f"  dup x{dcount} {name}: {inp}")
        print(f"  biggest results: {r['big']}")


# ---------------------------------------------------------------- gaps
def cmd_gaps(a):
    for f in a.files:
        pending = {}; ev = []
        for d in rows(f):
            t = d.get("timestamp")
            if not t:
                continue
            if d.get("type") == "assistant":
                for c in d["message"].get("content", []):
                    if c.get("type") == "tool_use":
                        i = c["input"]
                        desc = i.get("command") or i.get("file_path") or i.get("description") or json.dumps(i)
                        pending[c["id"]] = (ts(t), c["name"], desc[:150].replace("\n", "⏎"))
            elif d.get("type") == "user":
                cont = d.get("message", {}).get("content")
                if isinstance(cont, list):
                    for c in cont:
                        if c.get("type") == "tool_result" and c.get("tool_use_id") in pending:
                            t0, name, desc = pending.pop(c["tool_use_id"])
                            ev.append(((ts(t) - t0).total_seconds(), t0.strftime("%H:%M:%S"), name, desc))
        ev.sort(reverse=True)
        print("=" * 90); print(f"{rel(f)}  tool-wait total={sum(e[0] for e in ev)/60:.1f}min over {len(ev)} calls")
        for e in ev[: a.top]:
            print(f"  {e[0]:6.0f}s {e[1]} {e[2]}: {e[3]}")


# ---------------------------------------------------------------- narrative
def cmd_narrative(a):
    names = {}
    for d in rows(a.file):
        t = d.get("type"); tm = (d.get("timestamp") or "")[11:19]
        if t == "assistant":
            m = d["message"]; u = m.get("usage") or {}
            ctx = (u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)) // 1000
            for c in m.get("content", []):
                if c.get("type") == "tool_use":
                    i = c["input"]; names[c["id"]] = c["name"]
                    if c["name"] == "Bash":
                        s = i.get("command", "")[:200].replace("\n", "⏎")
                    elif c["name"] == "Read":
                        if a.skip_reads:
                            continue
                        s = i.get("file_path", "") + (f" off={i.get('offset')} lim={i.get('limit')}" if i.get("offset") or i.get("limit") else " (whole)")
                    elif c["name"] in ("Edit", "Write"):
                        s = i.get("file_path", "")
                    elif c["name"] == "Agent":
                        s = f"{i.get('subagent_type')} model={i.get('model')} bg={i.get('run_in_background')} desc={i.get('description')} promptlen={len(i.get('prompt', ''))}"
                    else:
                        s = json.dumps(i)[:160]
                    print(f"{tm} ctx={ctx}k A {c['name']}: {s}")
                elif c.get("type") == "text" and c["text"].strip():
                    print(f"{tm} ctx={ctx}k A text: {c['text'][: a.max_text]!r}")
        elif t == "user":
            cont = d.get("message", {}).get("content")
            if isinstance(cont, str):
                print(f"{tm} U: {cont[: a.max_text]!r}")
            elif isinstance(cont, list):
                for c in cont:
                    if c.get("type") == "text":
                        print(f"{tm} U: {c['text'][: a.max_text]!r}")
                    elif c.get("type") == "tool_result":
                        name = names.get(c.get("tool_use_id"), "?")
                        if a.skip_reads and name == "Read":
                            continue
                        s = json.dumps(c.get("content"))
                        print(f"{tm}   R {name}{' ERROR' if c.get('is_error') else ''} len={len(s)}: {s[:100]!r}")


# ---------------------------------------------------------------- reads / totals
def cmd_reads(a):
    reads = collections.defaultdict(lambda: [0, 0, set()]); edits = collections.defaultdict(collections.Counter)
    for f in a.files:
        ag = os.path.basename(f)[:14]; ids = {}
        for d in rows(f):
            if d.get("type") == "assistant":
                for c in d["message"].get("content", []):
                    if c.get("type") == "tool_use":
                        if c["name"] == "Read":
                            ids[c["id"]] = c["input"].get("file_path")
                        if c["name"] in ("Edit", "Write"):
                            edits[c["input"].get("file_path")][ag] += 1
            elif d.get("type") == "user":
                cont = d.get("message", {}).get("content")
                if isinstance(cont, list):
                    for c in cont:
                        if c.get("type") == "tool_result" and c.get("tool_use_id") in ids:
                            r = reads[ids[c["tool_use_id"]]]; r[0] += 1; r[1] += len(json.dumps(c.get("content"))); r[2].add(ag)
    cwd = os.getcwd() + "/"
    print("TOP READ FILES  (reads, chars, distinct agents)")
    for p, (n, ch, ags) in sorted(reads.items(), key=lambda x: -x[1][1])[: a.top]:
        print(f"  {n:3d} {ch/1000:7.0f}k {len(ags):2d}  {(p or '').replace(cwd, '')}")
    print(f"  total read chars: {sum(v[1] for v in reads.values())/1e6:.2f}M")
    print("EDIT CHURN  (edits, file, per agent)")
    for p, c in sorted(edits.items(), key=lambda x: -sum(x[1].values()))[: a.top]:
        print(f"  {sum(c.values()):3d} {(p or '').replace(cwd, '')}  {dict(c)}")


def cmd_totals(a):
    by = collections.defaultdict(collections.Counter)
    for f in a.files:
        for d in rows(f):
            if d.get("type") == "assistant":
                u = d["message"].get("usage") or {}
                for k in ("output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "input_tokens"):
                    by[d["message"].get("model")][k] += u.get(k, 0)
    for m, c in by.items():
        print(m, {k: f"{v:,}" for k, v in c.items()})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("find"); p.add_argument("--days", type=int, default=7); p.add_argument("--min-mb", type=float, default=1.0); p.add_argument("--session"); p.set_defaults(fn=cmd_find)
    p = sp.add_parser("stats"); p.add_argument("files", nargs="+"); p.set_defaults(fn=cmd_stats)
    p = sp.add_parser("gaps"); p.add_argument("files", nargs="+"); p.add_argument("--top", type=int, default=6); p.set_defaults(fn=cmd_gaps)
    p = sp.add_parser("narrative"); p.add_argument("file"); p.add_argument("--max-text", type=int, default=300); p.add_argument("--skip-reads", action="store_true"); p.set_defaults(fn=cmd_narrative)
    p = sp.add_parser("reads"); p.add_argument("files", nargs="+"); p.add_argument("--top", type=int, default=20); p.set_defaults(fn=cmd_reads)
    p = sp.add_parser("totals"); p.add_argument("files", nargs="+"); p.set_defaults(fn=cmd_totals)
    a = ap.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
