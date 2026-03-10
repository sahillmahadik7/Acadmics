from __future__ import annotations

import operator
import os
import re
from datetime import date, timedelta
from pathlib import Path
from typing import TypedDict, List, Optional, Literal, Annotated

from pydantic import BaseModel, Field

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "AIzaSyDANec9dC00iJXYJKBK2LKRXXBXW2PNzXk")
TEXT_MODEL     = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.1-flash-lite-preview")
IMAGE_MODEL    = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image-preview")


class Task(BaseModel):
    id: int
    title: str
    goal: str = Field(..., description="One sentence: what the reader can do/understand after this section.")
    bullets: List[str] = Field(..., min_length=2, max_length=4)
    target_words: int = Field(..., description="Target word count (80–250).")
    tags: List[str] = Field(default_factory=list)
    requires_research: bool = False
    requires_citations: bool = False
    requires_code: bool = False


class Plan(BaseModel):
    blog_title: str
    audience: str
    tone: str
    blog_kind: Literal["explainer", "tutorial", "news_roundup", "comparison", "system_design"] = "explainer"
    constraints: List[str] = Field(default_factory=list)
    tasks: List[Task]


class EvidenceItem(BaseModel):
    title: str
    url: str
    published_at: Optional[str] = None
    snippet: Optional[str] = None
    source: Optional[str] = None


class RouterDecision(BaseModel):
    needs_research: bool
    mode: Literal["closed_book", "hybrid", "open_book"]
    reason: str
    queries: List[str] = Field(default_factory=list)
    max_results_per_query: int = Field(5)


class EvidencePack(BaseModel):
    evidence: List[EvidenceItem] = Field(default_factory=list)


class ImageSpec(BaseModel):
    placeholder: str = Field(..., description="e.g. [[IMAGE_1]]")
    filename:    str = Field(..., description="Save under images/, e.g. architecture.png")
    alt:     str
    caption: str
    prompt:  str = Field(..., description="Image generation prompt.")
    size:    Literal["1024x1024", "1024x1536", "1536x1024"] = "1024x1024"
    quality: Literal["low", "medium", "high"] = "medium"


class GlobalImagePlan(BaseModel):
    md_with_placeholders: str
    images: List[ImageSpec] = Field(default_factory=list)


class State(TypedDict):
    topic: str
    mode: str
    needs_research: bool
    queries: List[str]
    evidence: List[EvidenceItem]
    plan: Optional[Plan]
    as_of: str
    recency_days: int
    sections: Annotated[List[tuple[int, str]], operator.add]
    merged_md: str
    md_with_placeholders: str
    image_specs: List[dict]
    final: str


llm = ChatGoogleGenerativeAI(model=TEXT_MODEL, google_api_key=GOOGLE_API_KEY)


def _text(response) -> str:
    content = response.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        ).strip()
    return str(content).strip()


ROUTER_SYSTEM = """\
You are a routing module for a technical blog planner.

Decide whether web research is needed BEFORE planning.

Modes:
- closed_book  (needs_research=false): evergreen concepts, pure fundamentals.
- hybrid       (needs_research=true) : mostly evergreen but needs current examples/tools.
- open_book    (needs_research=true) : volatile — weekly roundups, "latest", pricing, policy.

If needs_research=true, output 3–10 high-signal, scoped queries.
Open_book queries must reflect the last 7 days.
"""


def router_node(state: State) -> dict:
    decision = llm.with_structured_output(RouterDecision).invoke([
        SystemMessage(content=ROUTER_SYSTEM),
        HumanMessage(content=f"Topic: {state['topic']}\nAs-of date: {state['as_of']}"),
    ])
    recency = {"open_book": 7, "hybrid": 45}.get(decision.mode, 3650)
    return {
        "needs_research": decision.needs_research,
        "mode":           decision.mode,
        "queries":        decision.queries,
        "recency_days":   recency,
    }


def route_next(state: State) -> str:
    return "research" if state["needs_research"] else "orchestrator"


def _tavily_search(query: str, max_results: int = 5) -> List[dict]:
    return []


def _iso_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except Exception:
        return None


RESEARCH_SYSTEM = """\
You are a research synthesizer for technical writing.

Given raw web search results, return deduplicated EvidenceItem objects.
Rules:
- Only include items with a non-empty url.
- Prefer authoritative sources (docs, official blogs, reputable outlets).
- If published_at is reliably inferrable, set it as YYYY-MM-DD; otherwise null.
- Keep snippets concise. Deduplicate by URL.
"""


def research_node(state: State) -> dict:
    queries = (state.get("queries") or [])[:10]
    raw: List[dict] = []
    for q in queries:
        raw.extend(_tavily_search(q, max_results=6))

    if not raw:
        return {"evidence": []}

    pack = llm.with_structured_output(EvidencePack).invoke([
        SystemMessage(content=RESEARCH_SYSTEM),
        HumanMessage(content=(
            f"As-of date: {state['as_of']}\n"
            f"Recency days: {state['recency_days']}\n\n"
            f"Raw results:\n{raw}"
        )),
    ])

    dedup    = {e.url: e for e in pack.evidence if e.url}
    evidence = list(dedup.values())

    if state.get("mode") == "open_book":
        as_of   = date.fromisoformat(state["as_of"])
        cutoff  = as_of - timedelta(days=int(state["recency_days"]))
        evidence = [e for e in evidence if (d := _iso_date(e.published_at)) and d >= cutoff]

    return {"evidence": evidence}


ORCH_SYSTEM = """\
You are a senior technical writer and developer advocate.
Produce a concise, actionable outline for a technical blog post.

Requirements:
- 3–5 tasks only. Keep the plan tight.
- Each task: goal (1 sentence) + 2–4 concrete bullets + target_words (80–250).
- Tags are freeform; do not force any taxonomy.
- At least 1 task must address a real engineering concern (code, edge cases, or debugging).

Grounding rules:
- closed_book : evergreen; do not cite evidence.
- hybrid      : use evidence for up-to-date examples; mark those tasks requires_research=True + requires_citations=True.
- open_book   : set blog_kind="news_roundup"; focus on events + implications; no tutorials unless explicitly requested.

Output must strictly match the Plan schema.
"""


def orchestrator_node(state: State) -> dict:
    mode     = state.get("mode", "closed_book")
    evidence = state.get("evidence", [])

    plan = llm.with_structured_output(Plan).invoke([
        SystemMessage(content=ORCH_SYSTEM),
        HumanMessage(content=(
            f"Topic : {state['topic']}\n"
            f"Mode  : {mode}\n"
            f"As-of : {state['as_of']}  (recency_days={state['recency_days']})\n"
            f"{'→ Force blog_kind=news_roundup' if mode == 'open_book' else ''}\n\n"
            f"Evidence:\n{[e.model_dump() for e in evidence][:16]}"
        )),
    ])
    if mode == "open_book":
        plan.blog_kind = "news_roundup"
    return {"plan": plan}


def fanout(state: State):
    assert state["plan"] is not None
    return [
        Send("worker", {
            "task":         task.model_dump(),
            "topic":        state["topic"],
            "mode":         state["mode"],
            "as_of":        state["as_of"],
            "recency_days": state["recency_days"],
            "plan":         state["plan"].model_dump(),
            "evidence":     [e.model_dump() for e in state.get("evidence", [])],
        })
        for task in state["plan"].tasks
    ]


WORKER_SYSTEM = """\
You are a technical writer. Write ONE concise section of a blog post in Markdown.

Hard constraints:
- Cover ALL bullets in order.
- Stay within Target words ±15%. Keep it tight — do not pad.
- Start with "## <Section Title>".
- Output ONLY the section Markdown — no H1, no extra commentary.

Scope guard:
- If blog_kind=="news_roundup": do NOT drift into tutorials or how-tos.
  Focus on events and their implications.

Grounding:
- mode=="open_book": do not introduce any claim about events/companies/models unless
  it is supported by the provided Evidence URLs. Cite as ([Source](URL)). If unsupported, say so.
- requires_citations==true (hybrid): cite Evidence URLs for external factual claims.

Code:
- If requires_code==true, include at least one minimal, correct code snippet.

Style:
- Short paragraphs, bullets where helpful, code fences for code.
- Precise and implementation-oriented. No fluff, no marketing language.
"""


def worker_node(payload: dict) -> dict:
    task     = Task(**payload["task"])
    plan     = Plan(**payload["plan"])
    evidence = [EvidenceItem(**e) for e in payload.get("evidence", [])]

    bullets_text  = "\n- " + "\n- ".join(task.bullets)
    evidence_text = "\n".join(
        f"- {e.title} | {e.url} | {e.published_at or 'date:unknown'}"
        for e in evidence[:20]
    )

    section_md = _text(llm.invoke([
        SystemMessage(content=WORKER_SYSTEM),
        HumanMessage(content=(
            f"Blog title : {plan.blog_title}\n"
            f"Audience   : {plan.audience}\n"
            f"Tone       : {plan.tone}\n"
            f"Blog kind  : {plan.blog_kind}\n"
            f"Constraints: {plan.constraints}\n"
            f"Topic      : {payload['topic']}\n"
            f"Mode       : {payload.get('mode')}\n"
            f"As-of      : {payload.get('as_of')}  (recency_days={payload.get('recency_days')})\n\n"
            f"Section title     : {task.title}\n"
            f"Goal              : {task.goal}\n"
            f"Target words      : {task.target_words}\n"
            f"Tags              : {task.tags}\n"
            f"requires_research : {task.requires_research}\n"
            f"requires_citations: {task.requires_citations}\n"
            f"requires_code     : {task.requires_code}\n"
            f"Bullets:{bullets_text}\n\n"
            f"Evidence (ONLY cite these URLs):\n{evidence_text}\n"
        )),
    ]))

    return {"sections": [(task.id, section_md)]}


def merge_content(state: State) -> dict:
    plan = state["plan"]
    if plan is None:
        raise ValueError("merge_content called without a plan.")
    ordered = [md for _, md in sorted(state["sections"], key=lambda x: x[0])]
    body    = "\n\n".join(ordered).strip()
    return {"merged_md": f"# {plan.blog_title}\n\n{body}\n"}


DECIDE_IMAGES_SYSTEM = """\
You are an expert technical editor.
Decide which images/diagrams would materially improve this blog.

Rules:
- Max 3 images total.
- Only include images that genuinely aid understanding (architecture diagrams, flows, comparisons).
- Insert placeholders exactly: [[IMAGE_1]], [[IMAGE_2]], [[IMAGE_3]].
- If no images are needed, return the markdown unchanged and images=[].
- Avoid decorative or generic images.
Return a GlobalImagePlan.
"""


def decide_images(state: State) -> dict:
    plan = state["plan"]
    assert plan is not None

    image_plan = llm.with_structured_output(GlobalImagePlan).invoke([
        SystemMessage(content=DECIDE_IMAGES_SYSTEM),
        HumanMessage(content=(
            f"Blog kind: {plan.blog_kind}\n"
            f"Topic: {state['topic']}\n\n"
            f"Insert placeholders and propose generation prompts.\n\n"
            f"{state['merged_md']}"
        )),
    ])
    return {
        "md_with_placeholders": image_plan.md_with_placeholders,
        "image_specs":          [img.model_dump() for img in image_plan.images],
    }


def _generate_image_bytes(prompt: str) -> bytes:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GOOGLE_API_KEY)
    resp   = client.models.generate_content(
        model=IMAGE_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
        ),
    )

    parts = getattr(resp, "parts", None)
    if not parts and getattr(resp, "candidates", None):
        try:
            parts = resp.candidates[0].content.parts
        except Exception:
            parts = None

    if not parts:
        raise RuntimeError("No image parts returned (quota/safety/model mismatch).")

    for part in parts:
        inline = getattr(part, "inline_data", None)
        if inline and getattr(inline, "data", None):
            return inline.data

    raise RuntimeError("No inline image bytes found in response.")


def _safe_slug(title: str) -> str:
    s = title.strip().lower()
    s = re.sub(r"[^a-z0-9 _-]+", "", s)
    s = re.sub(r"\s+", "_", s).strip("_")
    return s or "blog"


def generate_and_place_images(state: State) -> dict:
    plan = state["plan"]
    assert plan is not None

    md          = state.get("md_with_placeholders") or state["merged_md"]
    image_specs = state.get("image_specs") or []

    if not image_specs:
        filename = f"{_safe_slug(plan.blog_title)}.md"
        Path(filename).write_text(md, encoding="utf-8")
        return {"final": md}

    images_dir = Path("images")
    images_dir.mkdir(exist_ok=True)

    for spec in image_specs:
        placeholder = spec["placeholder"]
        out_path    = images_dir / spec["filename"]

        if not out_path.exists():
            try:
                out_path.write_bytes(_generate_image_bytes(spec["prompt"]))
            except Exception as e:
                fallback = (
                    f"> **[Image generation failed]** {spec.get('caption', '')}\n>\n"
                    f"> **Prompt:** {spec.get('prompt', '')}\n>\n"
                    f"> **Error:** {e}\n"
                )
                md = md.replace(placeholder, fallback)
                continue

        img_md = f"![{spec['alt']}](images/{spec['filename']})\n*{spec['caption']}*"
        md     = md.replace(placeholder, img_md)

    filename = f"{_safe_slug(plan.blog_title)}.md"
    Path(filename).write_text(md, encoding="utf-8")
    return {"final": md}


_reducer = StateGraph(State)
_reducer.add_node("merge_content",             merge_content)
_reducer.add_node("decide_images",             decide_images)
_reducer.add_node("generate_and_place_images", generate_and_place_images)
_reducer.add_edge(START,            "merge_content")
_reducer.add_edge("merge_content",  "decide_images")
_reducer.add_edge("decide_images",  "generate_and_place_images")
_reducer.add_edge("generate_and_place_images", END)
reducer_subgraph = _reducer.compile()


g = StateGraph(State)
g.add_node("router",       router_node)
g.add_node("research",     research_node)
g.add_node("orchestrator", orchestrator_node)
g.add_node("worker",       worker_node)
g.add_node("reducer",      reducer_subgraph)

g.add_edge(START, "router")
g.add_conditional_edges("router", route_next, {"research": "research", "orchestrator": "orchestrator"})
g.add_edge("research",    "orchestrator")
g.add_conditional_edges("orchestrator", fanout, ["worker"])
g.add_edge("worker",  "reducer")
g.add_edge("reducer", END)

app = g.compile()
