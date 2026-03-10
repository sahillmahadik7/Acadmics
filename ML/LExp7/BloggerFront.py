from __future__ import annotations

import json
import re
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import pandas as pd
import streamlit as st

from BloggerBack import app

st.set_page_config(
    page_title="Scribe",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.8rem !important; }
</style>
""", unsafe_allow_html=True)


def safe_slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9 _-]+", "", title.strip().lower())
    return re.sub(r"\s+", "_", s).strip("_") or "blog"

def extract_title(md: str, fallback: str = "article") -> str:
    for line in md.splitlines():
        if line.startswith("# "):
            return line[2:].strip() or fallback
    return fallback

def word_count(md: str) -> int:
    text = re.sub(r"```[\s\S]*?```", "", md)
    return len(re.sub(r"[#*`>\[\]!_~]", "", text).split())

def reading_time(wc: int) -> str:
    return f"{max(1, round(wc / 238))} min"

def list_past_blogs() -> List[Path]:
    return sorted(Path(".").glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)

def bundle_zip(md_text: str, md_filename: str, images_dir: Path) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(md_filename, md_text.encode())
        if images_dir.exists():
            for p in images_dir.rglob("*"):
                if p.is_file():
                    z.write(p, arcname=str(p))
    return buf.getvalue()

def images_zip_bytes(images_dir: Path) -> Optional[bytes]:
    if not images_dir.exists():
        return None
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in images_dir.rglob("*"):
            if p.is_file():
                z.write(p, arcname=str(p))
    return buf.getvalue()


_IMG_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)]+)\)")
_CAP_RE = re.compile(r"^\*(?P<cap>.+)\*$")

def render_article(md: str):
    matches = list(_IMG_RE.finditer(md))
    if not matches:
        st.markdown(md)
        return
    parts: List[Tuple[str, str]] = []
    last = 0
    for m in matches:
        if md[last:m.start()]:
            parts.append(("md", md[last:m.start()]))
        parts.append(("img", f"{m.group('alt')}|||{m.group('src')}"))
        last = m.end()
    if md[last:]:
        parts.append(("md", md[last:]))
    i = 0
    while i < len(parts):
        kind, payload = parts[i]
        if kind == "md":
            st.markdown(payload)
            i += 1
            continue
        alt, src = payload.split("|||", 1)
        caption = None
        if i + 1 < len(parts) and parts[i+1][0] == "md":
            nxt = parts[i+1][1].lstrip()
            fl  = nxt.splitlines()[0].strip() if nxt.strip() else ""
            mc  = _CAP_RE.match(fl)
            if mc:
                caption = mc.group("cap").strip()
                parts[i+1] = ("md", "\n".join(nxt.splitlines()[1:]))
        if src.startswith("http"):
            st.image(src, caption=caption or alt or None, use_container_width=True)
        else:
            p = Path(src.strip().lstrip("./")).resolve()
            if p.exists():
                st.image(str(p), caption=caption or alt or None, use_container_width=True)
            else:
                st.warning(f"Image not found: `{src}`")
        i += 1


def try_stream(graph_app, inputs: Dict) -> Iterator[Tuple[str, Any]]:
    try:
        for step in graph_app.stream(inputs, stream_mode="updates"):
            yield ("update", step)
        yield ("final", graph_app.invoke(inputs))
        return
    except Exception:
        pass
    yield ("final", graph_app.invoke(inputs))

def merge_state(current: Dict, payload: Any) -> Dict:
    if isinstance(payload, dict):
        if len(payload) == 1 and isinstance(next(iter(payload.values())), dict):
            current.update(next(iter(payload.values())))
        else:
            current.update(payload)
    return current


if "last_out" not in st.session_state: st.session_state["last_out"] = None
if "run_logs" not in st.session_state: st.session_state["run_logs"] = []

with st.sidebar:
    st.markdown("## Scribe")
    st.caption("AI blog generator · Gemini + LangGraph")
    st.divider()

    topic   = st.text_area("Topic", placeholder="e.g. How transformers work", height=100)
    as_of   = st.date_input("As-of date", value=date.today())
    run_btn = st.button("Generate", type="primary", use_container_width=True)

    st.divider()
    st.markdown("**Past articles**")
    past = list(list_past_blogs())
    if not past:
        st.caption("None saved yet.")
        selected_file = None
    else:
        opts: Dict[str, Path] = {}
        for p in past[:30]:
            try:
                txt   = p.read_text(encoding="utf-8", errors="replace")
                label = extract_title(txt, p.stem)
            except Exception:
                label = p.stem
            opts[label[:40]] = p
        chosen        = st.radio("", list(opts.keys()), label_visibility="collapsed")
        selected_file = opts.get(chosen)
        if st.button("Load", use_container_width=True):
            if selected_file:
                md = selected_file.read_text(encoding="utf-8", errors="replace")
                st.session_state["last_out"] = {
                    "plan": None, "evidence": [], "image_specs": [], "final": md
                }

st.markdown("# Scribe")
st.caption("Enter a topic, click Generate, and get a full technical blog post.")

tab_article, tab_plan, tab_sources, tab_images, tab_logs = st.tabs([
    "Article", "Plan", "Sources", "Images", "Logs"
])

logs: List[str] = []

if run_btn:
    if not topic.strip():
        st.warning("Please enter a topic.")
        st.stop()

    inputs = {
        "topic": topic.strip(), "mode": "", "needs_research": False,
        "queries": [], "evidence": [], "plan": None,
        "as_of": as_of.isoformat(), "recency_days": 7,
        "sections": [], "merged_md": "", "md_with_placeholders": "",
        "image_specs": [], "final": "",
    }

    NODE_LABEL = {
        "router":       "Routing…",
        "research":     "Researching…",
        "orchestrator": "Planning…",
        "worker":       "Writing section…",
        "reducer":      "Assembling…",
    }

    with st.status("Generating…", expanded=True) as status:
        current: Dict = {}
        last_node = None

        for kind, payload in try_stream(app, inputs):
            if kind == "update":
                node = next(iter(payload)) if isinstance(payload, dict) and len(payload) == 1 else None
                if node and node != last_node:
                    st.write(NODE_LABEL.get(node, node))
                    last_node = node
                current = merge_state(current, payload)
                logs.append(json.dumps(payload, default=str)[:600])
            elif kind == "final":
                st.session_state["last_out"]  = payload
                st.session_state["run_logs"].extend(logs)
                status.update(label="Done", state="complete", expanded=False)

out = st.session_state.get("last_out")

if out:
    final_md    = out.get("final") or ""
    plan_obj    = out.get("plan")
    evidence    = out.get("evidence") or []
    image_specs = out.get("image_specs") or []

    with tab_article:
        if not final_md:
            st.info("No article yet.")
        else:
            wc   = word_count(final_md)
            nsec = final_md.count("\n## ")
            nim  = len(re.findall(r"!\[", final_md))
            st.caption(f"{wc:,} words · {reading_time(wc)} read · {nsec} sections · {nim} images")
            st.divider()
            render_article(final_md)
            st.divider()
            blog_title  = extract_title(final_md)
            md_filename = f"{safe_slug(blog_title)}.md"
            c1, c2 = st.columns(2)
            c1.download_button("Download .md", data=final_md.encode(),
                               file_name=md_filename, mime="text/markdown", use_container_width=True)
            c2.download_button("Download bundle (.zip)",
                               data=bundle_zip(final_md, md_filename, Path("images")),
                               file_name=f"{safe_slug(blog_title)}_bundle.zip",
                               mime="application/zip", use_container_width=True)

    with tab_plan:
        plan_dict = None
        if hasattr(plan_obj, "model_dump"):
            plan_dict = plan_obj.model_dump()
        elif isinstance(plan_obj, dict):
            plan_dict = plan_obj

        if not plan_dict:
            st.info("No plan available. Generate an article first.")
        else:
            st.markdown(f"### {plan_dict.get('blog_title', '—')}")
            st.caption(
                f"Audience: {plan_dict.get('audience', '—')}  ·  "
                f"Tone: {plan_dict.get('tone', '—')}  ·  "
                f"Mode: {out.get('mode') or '—'}  ·  "
                f"Kind: {plan_dict.get('blog_kind', '—')}"
            )
            st.divider()
            for t in sorted(plan_dict.get("tasks", []), key=lambda x: x.get("id", 0)):
                with st.expander(f"#{t.get('id')}  {t.get('title', '')}  —  ~{t.get('target_words', '?')} words"):
                    st.write(f"**Goal:** {t.get('goal', '')}")
                    for b in t.get("bullets", []):
                        st.write(f"- {b}")
                    flags = [k for k in ("requires_code", "requires_research", "requires_citations") if t.get(k)]
                    if flags:
                        st.caption("Requires: " + ", ".join(f.replace("requires_", "") for f in flags))

    with tab_sources:
        if not evidence:
            st.info("No sources — research is disabled or topic was classified as evergreen.")
        else:
            st.caption(f"{len(evidence)} sources")
            rows = []
            for e in evidence:
                if hasattr(e, "model_dump"):
                    e = e.model_dump()
                rows.append({
                    "Title":     e.get("title", ""),
                    "Published": e.get("published_at") or "—",
                    "Source":    e.get("source") or "—",
                    "URL":       e.get("url", ""),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with tab_images:
        images_dir = Path("images")
        if not image_specs and not images_dir.exists():
            st.info("No images generated for this article.")
        else:
            if image_specs:
                st.caption(f"{len(image_specs)} image(s) planned")
                for spec in image_specs:
                    with st.expander(f"{spec.get('placeholder', '')}  {spec.get('filename', '')}"):
                        st.write(f"**Caption:** {spec.get('caption', '')}")
                        st.code(spec.get("prompt", ""), language=None)
            if images_dir.exists():
                files = [p for p in images_dir.iterdir() if p.is_file()]
                cols  = st.columns(min(3, len(files))) if files else []
                for i, p in enumerate(sorted(files)):
                    cols[i % 3].image(str(p), caption=p.name, use_container_width=True)
                z = images_zip_bytes(images_dir)
                if z:
                    st.download_button("Download images (.zip)", data=z,
                                       file_name="images.zip", mime="application/zip")

    with tab_logs:
        all_logs = st.session_state.get("run_logs", [])
        if all_logs:
            st.caption(f"{len(all_logs)} events")
            st.text_area("", value="\n\n".join(all_logs[-80:]), height=480, label_visibility="collapsed")
            if st.button("Clear"):
                st.session_state["run_logs"] = []
                st.rerun()
        else:
            st.info("No logs yet.")

else:
    with tab_article:
        st.info("Enter a topic in the sidebar and click **Generate**.")
