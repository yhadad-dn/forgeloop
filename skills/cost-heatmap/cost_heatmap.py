#!/usr/bin/env python3
"""
cost_heatmap.py -- AI coding-agent token/cost heat map builder (stdlib only).

Reads local session transcripts from Claude Code (~/.claude/projects) and Codex
(~/.codex/sessions), plus any other tool via external_turns.csv, estimates cost at list
prices, and writes a self-contained interactive HTML heat map.

Commands:
  python3 cost_heatmap.py collect   # parse transcripts -> CSVs
  python3 cost_heatmap.py build     # CSVs -> dashboard HTML
  python3 cost_heatmap.py           # collect, then build (default)
  python3 cost_heatmap.py inspect   # show where transcripts are

Outputs (in --dir, default ~/.claude/forgeloop/cost-heatmap/):
  turns.csv           one row per assistant message
  sessions.csv        one row per session
  session_titles.csv  session_dir,title,first_prompt (auto-filled by collect)
  session_topics.csv  optional session_dir,topic (overrides keyword grouping)
  external_turns.csv  optional rows from other tools (see SKILL.md for columns)
  pricing.json        optional {"model-name": {"in":..,"out":..,"cr":..}} per-M-token overrides
  cost-heatmap.html   the dashboard

Privacy: only numeric usage, project folder names, and short session titles are
written; no conversation text beyond a 120-char first-prompt snippet.
"""
import os, sys, json, csv, glob, argparse, datetime, collections, base64, re, calendar

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(os.path.expanduser("~"), ".claude", "forgeloop", "cost-heatmap")
HTML   = os.path.join(OUTDIR, "cost-heatmap.html")
TEMPLATE = open(os.path.join(HERE, "dashboard.template.html"), encoding="utf-8").read()

# ---------- pricing (USD per MILLION tokens) ----------
# Verify against https://platform.claude.com/docs/en/about-claude/pricing (see SKILL.md).
PRICING = {"opus":{"in":5.0,"out":25.0}, "fable":{"in":10.0,"out":50.0},
           "sonnet":{"in":2.0,"out":10.0}, "haiku":{"in":1.0,"out":5.0},
           "synthetic":{"in":0.0,"out":0.0},
           # OpenAI/Codex: "cr" is the absolute cached-input rate; cache writes are not billed.
           # gpt-5.5 per OpenAI's pricing page (2026-10); older rows are list prices from memory.
           # Models not listed here (or in pricing.json) are costed at $0 and reported as unpriced.
           "gpt-5.5":{"in":5.0,"out":30.0,"cr":0.50,"cw":0.0},
           "gpt-4.1":{"in":2.0,"out":8.0,"cr":0.50,"cw":0.0},
           "gpt-4o":{"in":2.5,"out":10.0,"cr":1.25,"cw":0.0},
           "o3":{"in":2.0,"out":8.0,"cr":0.50,"cw":0.0},
           "o4-mini":{"in":1.1,"out":4.4,"cr":0.275,"cw":0.0},
           "gpt-4.5-preview":{"in":75.0,"out":150.0,"cr":37.5,"cw":0.0}}
UNPRICED=set()
CACHE_WRITE_MULT, CACHE_READ_MULT = 1.25, 0.10
# Optional monthly budget the dashboard compares run-rate against (0 = no budget KPI).
BUDGET_MONTHLY = 0
BUDGET_ENDS = ""
def tier(m):
    m=(m or "").lower()
    if "synthetic" in m: return "synthetic"
    for fam in ("fable","opus","sonnet","haiku"):
        if fam in m: return fam
    if "claude" in m or not m: return "opus"
    # non-Claude model: longest PRICING key that prefixes the name, else its own unpriced tier
    for k in sorted(PRICING,key=len,reverse=True):
        if m==k or m.startswith(k+"-") or m.startswith(k+"@"): return k
    return m
def rates(t):
    p=PRICING.get(t)
    if p is None:
        UNPRICED.add(t); return 0.0,0.0,0.0,0.0
    return p["in"],p["out"],p.get("cw",p["in"]*CACHE_WRITE_MULT),p.get("cr",p["in"]*CACHE_READ_MULT)
def cost_of(model,inp,cw,cr,out):
    ri,ro,rw,rr=rates(tier(model))
    return inp/1e6*ri+cw/1e6*rw+cr/1e6*rr+out/1e6*ro

# ---------- connector id -> friendly name (extend as needed) ----------
CONN={"(builtin)":"Built-in tools","(none)":"No tool (text/think)","":"No tool (text/think)"}
def conn_name(x): return CONN.get(x, x[:16] if x else "No tool (text/think)")

# ---------- locate logs ----------
def claude_root():
    cfg=os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"),".claude")
    p=os.path.join(cfg,"projects"); return p if os.path.isdir(p) else None
def codex_root():
    home=os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"),".codex")
    p=os.path.join(home,"sessions"); return p if os.path.isdir(p) else None
def find_jsonl(root):
    # os.walk (not glob) so we descend into hidden dirs like ~/.claude/projects
    out=[]
    for dp,dn,fn in os.walk(root):
        for f in fn:
            if f.endswith(".jsonl"): out.append(os.path.join(dp,f))
    return out

def primary_tool(content):
    if not isinstance(content,list): return "",""
    for blk in content:
        if isinstance(blk,dict) and blk.get("type")=="tool_use":
            name=blk.get("name","") or ""
            if name.startswith("mcp__"):
                parts=name.split("__"); return name,(parts[1] if len(parts)>1 else "mcp")
            return name,("(builtin)" if name else "")
    return "",""

def _cwd_project(cwd):
    return (cwd or "").replace("/","-").replace("\\","-")

def parse_codex(path,agg):
    """Codex rollout: token_count events carry cumulative totals; bill each positive delta."""
    try: _lines=open(path,encoding="utf-8",errors="ignore")
    except OSError: return
    sid=None; proj=""; model=""; sub=False; tool=""; prev={}; n=0; first_model=""; recs=[]
    for line in _lines:
        try: d=json.loads(line)
        except Exception: continue
        p=d.get("payload") or {}; ty=d.get("type")
        if ty=="session_meta":
            sid=p.get("id") or sid; proj=_cwd_project(p.get("cwd")); sub=bool(p.get("source") and isinstance(p.get("source"),dict))
        elif ty=="turn_context":
            model=p.get("model") or model; first_model=first_model or model
            proj=proj or _cwd_project(p.get("cwd"))
        elif ty=="response_item" and p.get("type")=="function_call":
            tool=p.get("name") or tool
        elif ty=="event_msg" and p.get("type")=="token_count":
            info=p.get("info") or {}; cur=info.get("total_token_usage") or {}
            if not cur: continue
            keys=("input_tokens","cached_input_tokens","cache_write_input_tokens","output_tokens")
            delta={k:(cur.get(k) or 0)-(prev.get(k) or 0) for k in keys}
            if any(v<0 for v in delta.values()): delta={k:(info.get("last_token_usage") or {}).get(k,0) or 0 for k in keys}
            prev=cur
            if not any(delta.values()): continue
            cached=delta["cached_input_tokens"]; cw=delta["cache_write_input_tokens"]
            n+=1; sid=sid or os.path.splitext(os.path.basename(path))[0]
            r=agg[(sid,"%s:%d"%(sid,n))]={"ts":d.get("timestamp") or "","session_id":sid,"model":model,
                "tool":"Codex","project":proj,"is_sidechain":sub,"tool_name":tool,"mcp_server":"(builtin)" if tool else "",
                "input":max(0,delta["input_tokens"]-cached-cw),"cw":cw,"cr":cached,"out":delta["output_tokens"],"ws":0,"wf":0}
            if not model: recs.append(r)
            tool=""
    for r in recs: r["model"]=first_model or "gpt-unknown"   # token_count seen before any turn_context

def codex_title(path):
    try: _lines=open(path,encoding="utf-8",errors="ignore")
    except OSError: return None,None
    sid=None
    for line in _lines:
        try: d=json.loads(line)
        except Exception: continue
        p=d.get("payload") or {}
        if d.get("type")=="session_meta": sid=p.get("id")
        elif d.get("type")=="response_item" and p.get("type")=="message" and p.get("role")=="user":
            for b in p.get("content") or []:
                v=_clean_prompt(b.get("text","")) if isinstance(b,dict) else ""
                if v and not v.startswith("# AGENTS.md") and "<INSTRUCTIONS>" not in v: return sid,v
    return sid,None

def _project(path):
    # ~/.claude/projects/<encoded-cwd>/<session>.jsonl (subagent logs sit deeper) -> encoded cwd
    parts=path.split(os.sep+"projects"+os.sep,1)
    return parts[1].split(os.sep)[0] if len(parts)==2 else ""

def parse_transcript(path,agg):
    try: _lines=open(path,encoding="utf-8",errors="ignore")
    except OSError: return   # unreadable log (permissions/locked) -> skip, don't crash collect
    for line in _lines:
        line=line.strip()
        if not line: continue
        try: d=json.loads(line)
        except Exception: continue
        if d.get("type")!="assistant": continue
        msg=d.get("message")
        if not isinstance(msg,dict): continue
        usage=msg.get("usage") or {}
        if not usage: continue
        sid=d.get("sessionId") or d.get("session_id") or os.path.splitext(os.path.basename(path))[0]
        mid=msg.get("id") or d.get("uuid")
        ts=d.get("timestamp") or ""
        stu=usage.get("server_tool_use") or {}
        tname,mserver=primary_tool(msg.get("content"))
        rec={"ts":ts,"session_id":sid,"model":msg.get("model",""),"tool":"Claude Code","project":_project(path),
             "is_sidechain":d.get("parent_tool_use_id") is not None or bool(d.get("isSidechain")),
             "tool_name":tname,"mcp_server":mserver,
             "input":usage.get("input_tokens",0) or 0,"cw":usage.get("cache_creation_input_tokens",0) or 0,
             "cr":usage.get("cache_read_input_tokens",0) or 0,"out":usage.get("output_tokens",0) or 0,
             "ws":stu.get("web_search_requests",0) or 0,"wf":stu.get("web_fetch_requests",0) or 0}
        cur=agg.get((sid,mid))
        if cur is None: agg[(sid,mid)]=rec
        else:
            for f in ("input","cw","cr","out","ws","wf"):
                if rec[f]>cur[f]: cur[f]=rec[f]
            if rec["ts"]>cur["ts"]: cur["ts"]=rec["ts"]
            if not cur["tool_name"] and rec["tool_name"]: cur["tool_name"]=rec["tool_name"]; cur["mcp_server"]=rec["mcp_server"]
            cur["is_sidechain"]=cur["is_sidechain"] or rec["is_sidechain"]

# ---------- title helpers (first-prompt cleanup) ----------
_WRAPPER=("your task prompt is saved in the file","carry out the task described in it")
_JUNK={"read and execute task from file","untitled","new session",""}
def _clean_prompt(t):
    t=(t or "").strip()
    if not t or t.startswith("<") or t.startswith("[Request interrupted"): return ""
    low=t.lower()
    if "command-name" in low or "local-command-stdout" in low: return ""
    if any(w in low for w in _WRAPPER): return ""
    return " ".join(t.split())[:120]
def _first_user_text(d):
    c=d.get("message",{}).get("content")
    if isinstance(c,str): return _clean_prompt(c)
    if isinstance(c,list):
        for b in c:
            if isinstance(b,dict) and b.get("type")=="text":
                v=_clean_prompt(b.get("text",""))
                if v: return v
    return ""

# ---------- collect ----------
def collect(root,codex_dir=None,tools=None):
    want=lambda t: tools is None or t in tools
    global codex_root
    if codex_dir: _cr=codex_dir; codex_root=lambda: _cr
    roots=[root] if root else ([claude_root()] if (claude_root() and want("claude")) else [])
    files=sorted(set(f for r in roots for f in find_jsonl(r)))
    cx=sorted(set(f for f in (find_jsonl(codex_root()) if (codex_root() and want("codex")) else [])
                  if os.path.basename(f).startswith("rollout-")))
    ext=os.path.join(OUTDIR,"external_turns.csv")
    if not files and not cx and not os.path.isfile(ext):
        print("ERROR: no transcripts found (Claude Code, Codex, external_turns.csv). Use 'inspect' or --root/--codex-root."); sys.exit(1)
    print("Scanning %d Claude Code + %d Codex transcripts..."%(len(files),len(cx)))
    agg={}
    for f in files: parse_transcript(f,agg)
    for f in cx: parse_codex(f,agg)

    titles={}; firstp={}
    tfile=os.path.join(OUTDIR,"session_titles.csv")
    if os.path.isfile(tfile):
        for row in csv.DictReader(open(tfile,encoding="utf-8-sig")):
            if row.get("session_dir"):
                titles[row["session_dir"]]=row.get("title","")
                if row.get("first_prompt"): firstp[row["session_dir"]]=row["first_prompt"]
    # Fill gaps from the transcripts: aiTitle when present, else the first user prompt.
    for f in files:
        sidcc=None; at=None; fp=None
        try: _lines=list(open(f,encoding="utf-8",errors="ignore"))
        except OSError: continue
        for line in _lines:
            try: d=json.loads(line)
            except Exception: continue
            sidcc=d.get("sessionId") or d.get("session_id") or sidcc
            if d.get("aiTitle"): at=d["aiTitle"]
            if not fp and d.get("type")=="user" and not d.get("isSidechain"): fp=_first_user_text(d) or fp
        if sidcc:
            cand = at if (at and at.strip().lower() not in _JUNK) else (fp or "")
            if cand and not titles.get(sidcc): titles[sidcc]=cand
            if fp and not firstp.get(sidcc): firstp[sidcc]=fp

    for f in cx:
        s2,v=codex_title(f)
        if s2 and v and not titles.get(s2): titles[s2]=v; firstp.setdefault(s2,v)
    if os.path.isfile(ext):   # other tools: ts,session_id,tool,model,project,input_tokens,cache_write_tokens,cache_read_tokens,output_tokens,title
        for i,row in enumerate(csv.DictReader(open(ext,encoding="utf-8-sig"))):
            sid=row.get("session_id") or "ext-%d"%i
            iv=lambda k: int(float(row.get(k) or 0))
            agg[(sid,"ext:%d"%i)]={"ts":row.get("ts",""),"session_id":sid,"model":row.get("model",""),
                "tool":row.get("tool") or "External","project":row.get("project",""),"is_sidechain":False,
                "tool_name":"","mcp_server":"","input":iv("input_tokens"),"cw":iv("cache_write_tokens"),
                "cr":iv("cache_read_tokens"),"out":iv("output_tokens"),"ws":0,"wf":0}
            if row.get("title") and not titles.get(sid): titles[sid]=row["title"]

    turns=[]
    for (sid,mid),r in agg.items():
        tot=r["input"]+r["cw"]+r["cr"]+r["out"]
        turns.append({"ts":r["ts"],"date":(r["ts"] or "")[:10],"session_id":sid,"message_id":mid,
            "tool":r.get("tool","Claude Code"),"project":r.get("project",""),
            "model":r["model"],"model_tier":tier(r["model"]),"is_sidechain":r["is_sidechain"],
            "tool_name":r["tool_name"],"mcp_server":r["mcp_server"],"input_tokens":r["input"],
            "cache_write_tokens":r["cw"],"cache_read_tokens":r["cr"],"output_tokens":r["out"],
            "total_tokens":tot,"web_search_reqs":r["ws"],"web_fetch_reqs":r["wf"],
            "cost_usd":round(cost_of(r["model"],r["input"],r["cw"],r["cr"],r["out"]),6)})
    turns.sort(key=lambda t:t["ts"])
    os.makedirs(OUTDIR,exist_ok=True)
    # Persist merged titles + first-prompt fallback so the build shows a
    # name for every session (and a recognizable prompt snippet for still-untitled ones).
    seen=sorted({t["session_id"] for t in turns} | set(titles))
    with open(tfile,"w",newline="",encoding="utf-8") as fh:
        w=csv.writer(fh); w.writerow(["session_dir","title","first_prompt"])
        for sid in seen: w.writerow([sid,titles.get(sid,""),firstp.get(sid,"")])
    tcols=["ts","date","session_id","message_id","tool","project","model","model_tier","is_sidechain","tool_name",
        "mcp_server","input_tokens","cache_write_tokens","cache_read_tokens","output_tokens",
        "total_tokens","web_search_reqs","web_fetch_reqs","cost_usd"]
    with open(os.path.join(OUTDIR,"turns.csv"),"w",newline="",encoding="utf-8") as fh:
        w=csv.DictWriter(fh,fieldnames=tcols); w.writeheader()
        for r in turns: w.writerow(r)
    S={}
    for r in turns:
        s=S.setdefault(r["session_id"],{"turns":0,"cost":0.0,"tot":0,"inp":0,"cw":0,"cr":0,"out":0,
            "first":r["ts"] or "9","last":r["ts"] or "","models":set()})
        s["turns"]+=1; s["cost"]+=r["cost_usd"]; s["tot"]+=r["total_tokens"]
        s["inp"]+=r["input_tokens"]; s["cw"]+=r["cache_write_tokens"]; s["cr"]+=r["cache_read_tokens"]; s["out"]+=r["output_tokens"]
        if r["ts"] and r["ts"]<s["first"]: s["first"]=r["ts"]
        if r["ts"] and r["ts"]>s["last"]: s["last"]=r["ts"]
        s["models"].add(r["model_tier"])
    scols=["session_id","title","first_ts","last_ts","turns","models","input_tokens",
        "cache_write_tokens","cache_read_tokens","output_tokens","total_tokens","cost_usd","topic"]
    with open(os.path.join(OUTDIR,"sessions.csv"),"w",newline="",encoding="utf-8") as fh:
        w=csv.DictWriter(fh,fieldnames=scols); w.writeheader()
        for sid,s in sorted(S.items(),key=lambda kv:-kv[1]["cost"]):
            w.writerow({"session_id":sid,"title":titles.get(sid,""),"first_ts":s["first"],"last_ts":s["last"],
                "turns":s["turns"],"models":"|".join(sorted(s["models"])),"input_tokens":s["inp"],
                "cache_write_tokens":s["cw"],"cache_read_tokens":s["cr"],"output_tokens":s["out"],
                "total_tokens":s["tot"],"cost_usd":round(s["cost"],4),"topic":""})
    tc=sum(r["cost_usd"] for r in turns); tt=sum(r["total_tokens"] for r in turns)
    cr=sum(r["cache_read_tokens"] for r in turns)
    print("  sessions:%d  messages:%d  titles:%d"%(len(S),len(turns),sum(1 for sid in S if titles.get(sid))))
    print("  tokens:%.1fM  cache-read:%d%%  est cost:$%s (list-price estimate, not a bill)"
          %(tt/1e6,(cr/tt*100) if tt else 0,format(tc,",.2f")))
    print("  wrote CSVs to",OUTDIR)

# ---------- topic grouping (first match wins; edit freely) ----------
# Fallback only: the skill has Claude write session_topics.csv tailored to the user's
# own work, which overrides these.
TOPIC_RULES=[
 ("Bug fixes & debugging",["bug","fix","error","fail","crash","debug","broken","regression","traceback"]),
 ("Tests & CI",["test","coverage","ci ","pipeline","lint"]),
 ("Planning & specs",["plan","spec","design","requirement","roadmap","architecture","adr"]),
 ("Review & refactor",["review","refactor","cleanup","clean up","simplif","rename"]),
 ("Docs & writing",["doc","readme","changelog","write","email","summary"]),
 ("Infra & cluster",["cluster","slurm","gpu","docker","deploy","install","config","setup","server"]),
 ("Features & implementation",["add ","implement","feature","build","create","support","migrate"]),
]
def classify(title):
    t=(title or "").lower()
    if not t: return "Misc"
    for n,ks in TOPIC_RULES:
        if any(k in t for k in ks): return n
    return "Misc"

def _proj_label(p):
    # "-home-dn-research-forgeloop" -> "forgeloop" (encoding is lossy; last segment is the best label)
    return (p.strip("-").split("-")[-1] if p else "") or "(unknown)"

# ---------- build ----------
def iso_week(dstr):
    d=datetime.date.fromisoformat(dstr); return (d-datetime.timedelta(days=d.weekday())).isoformat()

def build():
    tp=os.path.join(OUTDIR,"turns.csv")
    if not os.path.isfile(tp): print("ERROR: no turns.csv. Run 'collect' first."); sys.exit(1)
    # utf-8-sig everywhere below: PowerShell's Export-Csv -Encoding UTF8 writes a BOM
    # that plain utf-8 leaves attached to the first header, breaking lookups like
    # row["ts"] with a silent KeyError. utf-8-sig strips it if present, no-op otherwise.
    titles={}; firstp={}
    tf=os.path.join(OUTDIR,"session_titles.csv")
    if os.path.isfile(tf):
        for row in csv.DictReader(open(tf,encoding="utf-8-sig")):
            if row.get("session_dir"):
                titles[row["session_dir"]]=row.get("title","")
                if row.get("first_prompt"): firstp[row["session_dir"]]=row["first_prompt"]
    def label(sid,title):
        if title: return title[:48]
        if firstp.get(sid): return "~ "+firstp[sid][:44]
        return "(untitled) "+sid[:12]
    # Optional: Claude-assigned topics (session_dir,topic). Overrides keyword classify().
    topics_map={}
    tpf=os.path.join(OUTDIR,"session_topics.csv")
    if os.path.isfile(tpf):
        for row in csv.DictReader(open(tpf,encoding="utf-8-sig")):
            if row.get("session_dir") and row.get("topic"): topics_map[row["session_dir"]]=row["topic"]
    rows=list(csv.DictReader(open(tp,encoding="utf-8-sig")))
    for r in rows:
        for k in ("input_tokens","cache_write_tokens","cache_read_tokens","output_tokens","total_tokens"):
            r[k]=int(r[k] or 0)
        # recompute tier + cost from the model string so current pricing (incl. new
        # models like Fable, and $0 synthetic turns) always applies, even on old CSVs
        r["model_tier"]=tier(r.get("model",""))
        r["cost_usd"]=cost_of(r.get("model",""),r["input_tokens"],r["cache_write_tokens"],r["cache_read_tokens"],r["output_tokens"])
        r["date"]=(r["ts"] or "")[:10]
    dates=[r["date"] for r in rows if r["date"]]
    dmin,dmax=min(dates),max(dates)
    cut30=(datetime.date.fromisoformat(dmax)-datetime.timedelta(days=29)).isoformat()
    # per-(session, DAY): attribute cost to the day each turn actually occurred
    DAY=collections.defaultdict(lambda:{"cost":0,"tot":0,"inp":0,"out":0,"mc":collections.Counter(),"cc":collections.Counter(),"sub":0,"all":0,"project":"","tool":"Claude Code"})
    for r in rows:
        d=r["date"]
        if not d: continue
        x=DAY[(r["session_id"],d)]; x["cost"]+=r["cost_usd"]; x["tot"]+=r["total_tokens"]
        x["inp"]+=r["input_tokens"]; x["out"]+=r["output_tokens"]
        x["mc"][r["model_tier"]]+=r["cost_usd"]; x["cc"][conn_name(r["mcp_server"])]+=r["cost_usd"]
        x["all"]+=r["cost_usd"]; x["project"]=r.get("project") or ""; x["tool"]=r.get("tool") or "Claude Code"
        if r["is_sidechain"] in ("True","true","1"): x["sub"]+=r["cost_usd"]
    sess=[]
    for (sid,d),x in DAY.items():
        title=titles.get(sid,"")
        sess.append({"sid":sid,"id":label(sid,title),"title":title,"t":(topics_map.get(sid) or classify(title)),
            "proj":_proj_label(x["project"]),"tool":x["tool"],
            "wk":iso_week(d),"mo":d[:7],"dy":d,
            "mdl":(x["mc"].most_common(1)[0][0] if x["mc"] else "opus"),
            "conn":(x["cc"].most_common(1)[0][0] if x["cc"] else "No tool (text/think)"),
            "ag":("Subagent" if x["all"] and x["sub"]/x["all"]>0.5 else "Main"),
            "c":round(x["cost"],4),"tot":x["tot"],"wrk":x["inp"]+x["out"]})
    n_sessions=len(set(sid for (sid,d) in DAY)); n_titled=len(set(sid for (sid,d) in DAY if titles.get(sid)))
    tin=tcw=tcr=tout=0.0
    for r in rows:
        ri,ro,rw,rr=rates(r["model_tier"])
        tin+=r["input_tokens"]/1e6*ri; tcw+=r["cache_write_tokens"]/1e6*rw
        tcr+=r["cache_read_tokens"]/1e6*rr; tout+=r["output_tokens"]/1e6*ro
    total_cost=sum(r["cost_usd"] for r in rows); total_tok=sum(r["total_tokens"] for r in rows)
    cache_read=sum(r["cache_read_tokens"] for r in rows)
    model_cost=collections.Counter(); week_cost=collections.Counter(); topic_cost=collections.Counter()
    for r in rows:
        model_cost[r["model_tier"]]+=r["cost_usd"]
        if r["date"]: week_cost[iso_week(r["date"])]+=r["cost_usd"]
    for s in sess: topic_cost[s["t"]]+=s["c"]
    top=topic_cost.most_common(1)[0] if topic_cost else ("n/a",0)
    nweeks=len(week_cost)
    # ---- cost-reduction insights: LAST 7 DAYS vs prior ~30 days (progress is recent) ----
    _dmax=datetime.date.fromisoformat(dmax)
    REC=(_dmax-datetime.timedelta(days=6)).isoformat()
    BSTART=(_dmax-datetime.timedelta(days=36)).isoformat(); BEND=(_dmax-datetime.timedelta(days=7)).isoformat()
    def _m(v): return "$"+format(int(round(v)),",")
    def rec_cost(p): return sum(s["c"] for s in sess if s["dy"]>=REC and p(s))
    def base_wk(p): return sum(s["c"] for s in sess if BSTART<=s["dy"]<=BEND and p(s))/30.0*7
    def month(p): return rec_cost(p)/7.0*30
    def trend(p):
        r=rec_cost(p); b=base_wk(p)
        if b<=0.5: return "new this month"
        d=(r-b)/b*100
        return ("up %d%%"%round(d) if d>=0 else "down %d%%"%round(-d))+" vs the prior month's weekly pace"
    # Recurring automation is detected structurally (same title repeating across many
    # distinct sessions), NOT by matching a hardcoded topic label. Topic names are
    # generated per-user (see SKILL.md step 4), so "Knowledge base & recurring ops" is
    # only ever true for the user whose taxonomy happens to use that exact string --
    # for everyone else this lever silently computes $0. Title repetition is a durable,
    # per-user, language-agnostic signal for "this runs on a schedule."
    _title_norm={}
    for _sid in set(r["session_id"] for r in rows):
        _t=(titles.get(_sid) or "").strip().lower()
        if _t: _title_norm[_sid]=_t
    _title_freq=collections.Counter(_title_norm.values())
    RECUR_MIN=3  # a title seen on 3+ distinct sessions reads as a repeating/scheduled job
    _recurring_sids={sid for sid,t in _title_norm.items() if _title_freq[t]>=RECUR_MIN}
    _recur=lambda s: s["sid"] in _recurring_sids
    _opus=lambda s: s["mdl"]=="opus"; _fable=lambda s: s["mdl"]=="fable"
    _rc=0.0
    for r in rows:
        if r["date"]>=REC:
            _,_,rw,rr=rates(r["model_tier"])
            _rc+=r["cache_write_tokens"]/1e6*rw + r["cache_read_tokens"]/1e6*rr
    cache_mo=_rc/7.0*30
    _rrc=sum(r["cost_usd"] for r in rows if r["date"]>=REC)
    cache_share7=min(98,round(_rc/_rrc*100)) if _rrc else 0
    insights=[
     {"t":"Right-size recurring automation","tag":"Biggest lever","save":round(month(_recur)*0.6),
      "b":"Sessions that repeat on a schedule (the same title recurring "+str(RECUR_MIN)+"+ times, e.g. hourly/daily syncs and refreshes) ran "+_m(rec_cost(_recur))+" in the last 7 days ("+trend(_recur)+"). Premium models should not absorb routine work -- move these scheduled jobs to Sonnet-5 or Haiku."},
     {"t":"Default to Sonnet-5, reserve Opus","tag":"Model routing","save":round(month(_opus)*0.3),
      "b":"Opus was "+_m(rec_cost(_opus))+" of the last 7 days ("+trend(_opus)+"). Default to Sonnet-5, reserve Opus for genuinely hard design/coding, and send routine work to Sonnet-5 ($2/$10 vs $5/$25)."},
     {"t":"Trim context on long sessions","tag":"Efficiency","save":round(cache_mo*0.12),
      "b":str(cache_share7)+"% of the last 7 days was cache read/write (carrying context), not generation. Load fewer MCP servers/tools per session, keep prompts scoped, and split marathon sessions so history is not re-read every turn."},
     {"t":"Keep Fable 5 targeted","tag":"Guardrail","save":round(month(_fable)*0.3),
      "b":"Fable 5 ran "+_m(rec_cost(_fable))+" in the last 7 days ("+trend(_fable)+") at ~2x Opus per token. Use it only where evals justify it -- design/plan and verification -- not routine execution."},
    ]
    insights_note="Observations compare the last 7 days to the prior ~30 days. Savings are directional monthly estimates on list prices (levers overlap, so not simply additive)."
    # ---- monthly spend is the primary lens (trailing 7-day run-rate, not the period total) ----
    _calmo=dmax[:7]
    _day_cost=collections.Counter()
    for r in rows:
        if r["date"]: _day_cost[r["date"]]+=r["cost_usd"]
    mtd_cost=sum(v for d,v in _day_cost.items() if d[:7]==_calmo)
    days_elapsed=int(dmax[8:10])
    _y,_mo=int(_calmo[:4]),int(_calmo[5:7])
    days_in_month=calendar.monthrange(_y,_mo)[1]
    recent_monthly=round(month(lambda s: True))
    fee_delta=round(recent_monthly-BUDGET_MONTHLY)
    fee_multiple=round(recent_monthly/BUDGET_MONTHLY,1) if BUDGET_MONTHLY else 0
    total_potential_savings=sum(x["save"] for x in insights)
    projected_monthly=max(0,recent_monthly-total_potential_savings)
    projected_fee_multiple=round(projected_monthly/BUDGET_MONTHLY,1) if BUDGET_MONTHLY else 0
    # ---- unit economics: cost per AI CALL (one turns.csv row = one assistant message/response)
    # vs cost per TASK (one full Claude Code session, which may contain many calls) ----
    n_calls=len(rows)
    cost_per_call=round(total_cost/n_calls,4) if n_calls else 0
    cost_per_task=round(total_cost/n_sessions,2) if n_sessions else 0
    data={"generated":datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),"dmin":dmin,"dmax":dmax,
      "cut30":cut30,"nweeks":nweeks,"sessions":sess,"insights":insights,"insights_note":insights_note,
      "kpi":{"cost":round(total_cost),"tokens":total_tok,"nsess":n_sessions,"ncalls":n_calls,
        "cacheread":round(cache_read/total_tok*100) if total_tok else 0,
        "avg":cost_per_task,"perweek":round(total_cost/nweeks) if nweeks else 0,
        "toptopic":top[0],"toptopicpct":round(top[1]/total_cost*100) if total_cost else 0,
        "titled":n_titled,
        "flatfee":BUDGET_MONTHLY,"flatfeeends":BUDGET_ENDS,"recentmonthly":recent_monthly,
        "feedelta":fee_delta,"feemultiple":fee_multiple,
        "mtdcost":round(mtd_cost),"dayselapsed":days_elapsed,"daysinmonth":days_in_month,
        "totalsavings":total_potential_savings,"projectedmonthly":projected_monthly,
        "projectedfeemultiple":projected_fee_multiple,
        "costpercall":cost_per_call,"costpertask":cost_per_task},
      "tokentype":{"Fresh input":round(tin),"Cache write":round(tcw),"Cache read":round(tcr),"Output":round(tout)},
      "topiccost":{k:round(v) for k,v in topic_cost.most_common()},
      "modelcost":{k:round(v) for k,v in model_cost.most_common()},
      "weektrend":[[k,round(week_cost[k],1)] for k in sorted(week_cost)]}
    html=TEMPLATE.replace("/*__DATA__*/","const DATA="+json.dumps(data)+";")
    open(HTML,"w",encoding="utf-8").write(html)
    if UNPRICED: print("  WARNING: no price for %s (costed at $0). Add them to %s"%(", ".join(sorted(UNPRICED)),os.path.join(OUTDIR,"pricing.json")))
    print("Built dashboard: %s"%HTML)
    print("  %d sessions, %d weeks, est $%s, top topic: %s (%d%%)"
          %(n_sessions,nweeks,format(round(total_cost),","),top[0],data["kpi"]["toptopicpct"]))

# ---------- inspect ----------
def inspect(root,codex_dir=None):
    found=[("Claude Code",root or claude_root()),("Codex",codex_dir or codex_root())]
    for name,r in found:
        n=len(find_jsonl(r)) if r else 0
        print("%-12s %s  (%d .jsonl files)"%(name,r or "not found",n))
    print("Other tools: write rows to %s"%os.path.join(OUTDIR,"external_turns.csv"))

def main():
    global OUTDIR, HTML, BUDGET_MONTHLY, BUDGET_ENDS
    ap=argparse.ArgumentParser(description="Claude Code token/cost heat map")
    ap.add_argument("cmd",nargs="?",default="all",choices=["all","collect","build","inspect"])
    ap.add_argument("--root",default=None,help="Claude Code transcripts folder (default: ~/.claude/projects)")
    ap.add_argument("--codex-root",default=None,help="Codex sessions folder (default: ~/.codex/sessions)")
    ap.add_argument("--tools",default=None,help="comma list to scan: claude,codex (default: all found)")
    ap.add_argument("--dir",default=None,help="output folder (default: ~/.claude/forgeloop/cost-heatmap)")
    ap.add_argument("--budget",type=float,default=0,help="monthly budget in USD to compare run-rate against (0 = off)")
    ap.add_argument("--budget-ends",default="",help="YYYY-MM-DD the budget ends (optional)")
    a=ap.parse_args()
    if a.dir:
        OUTDIR=os.path.abspath(a.dir); HTML=os.path.join(OUTDIR,"cost-heatmap.html")
    BUDGET_MONTHLY=a.budget; BUDGET_ENDS=a.budget_ends
    tools=set(a.tools.split(",")) if a.tools else None
    pj=os.path.join(OUTDIR,"pricing.json")
    if os.path.isfile(pj):
        try: PRICING.update(json.load(open(pj,encoding="utf-8")))
        except (OSError,ValueError) as e: print("WARNING: ignoring pricing.json:",e)
    if a.cmd=="inspect": inspect(a.root,a.codex_root)
    elif a.cmd=="collect": collect(a.root,a.codex_root,tools)
    elif a.cmd=="build": build()
    else: collect(a.root,a.codex_root,tools); build()

if __name__=="__main__": main()
