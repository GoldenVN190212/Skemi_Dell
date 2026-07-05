"""
Skemi Idea Lab — a virtual experimentation environment. Turns an idea or
hypothesis (often born from a Search knowledge-map gap) into a structured
"experiment report": feasibility score, what-if scenarios, knowledge gaps,
risks, concrete next steps and resources — so users can stress-test and iterate
ideas, even seemingly impossible ones, until they work.

LLM via ChatBackend when reachable; gracefully SIMULATES a sensible report
offline so the lab is fully usable without a model.
"""

from __future__ import annotations

import json
import os
import random
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body

router = APIRouter(prefix="/api/lab", tags=["lab"])

BASE_DIR = Path(__file__).resolve().parent
LAB_MODEL = os.getenv("SKEMI_LAB_MODEL", "") or "devstral-2:123b-cloud"


def _est_tokens(text: str) -> int:
    return max(1, int(len(str(text or "")) / 3.5))


async def _llm(prompt: str, timeout: float = 50.0, num_predict: int = 1500) -> Optional[str]:
    try:
        import ChatBackend as backend
        if hasattr(backend, "_generate_text_once"):
            out = await backend._generate_text_once(LAB_MODEL, prompt, timeout=timeout, num_predict=num_predict)
            if out and str(out).strip():
                return str(out).strip()
    except Exception:
        pass
    return None


def _extract_json(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return None
    blob = m.group(0)
    # LLMs routinely emit code with LITERAL newlines/tabs inside JSON string values
    # (e.g. a multi-line `function solve(){...}`). strict=False tolerates those control
    # chars; the trailing-comma sub handles the other common malformation. We also try a
    # brace-balanced truncation in case num_predict cut the response mid-object.
    candidates = [blob, re.sub(r",\s*([}\]])", r"\1", blob)]
    depth, last_balanced = 0, -1
    for i, ch in enumerate(blob):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                last_balanced = i
    if last_balanced > 0:
        candidates.append(blob[: last_balanced + 1])
    for cand in candidates:
        for strict in (True, False):
            try:
                return json.loads(cand, strict=strict)
            except Exception:
                continue
    return None


def _simulate(idea: str) -> Dict[str, Any]:
    """A reasonable structured report when no LLM is available — keeps the lab
    fully demoable offline and never blocks the user's experimentation."""
    feas = random.randint(38, 86)
    verdict = "Đột phá" if feas < 50 else ("Thách thức" if feas < 70 else "Khả thi")
    short = (idea[:90] + "…") if len(idea) > 90 else idea
    return {
        "feasibility": feas,
        "verdict": verdict,
        "summary": f"[mô phỏng] Ý tưởng “{short}” có tiềm năng nhưng cần kiểm chứng thêm. "
                   f"Mức khả thi ước tính {feas}% dựa trên độ mới, độ phức tạp và nguồn lực cần thiết.",
        "scenarios": [
            {"name": "Kịch bản lạc quan", "outcome": "Đạt mục tiêu nếu kiểm soát tốt biến số then chốt.", "probability": min(95, feas + 18)},
            {"name": "Kịch bản cơ sở", "outcome": "Kết quả một phần, cần lặp lại nhiều vòng thử nghiệm.", "probability": feas},
            {"name": "Kịch bản rủi ro", "outcome": "Gặp rào cản kỹ thuật/nguồn lực chưa lường trước.", "probability": max(8, 100 - feas - 20)},
        ],
        "gaps": [
            "Thiếu dữ liệu thực nghiệm trực tiếp về giả thuyết cốt lõi.",
            "Chưa có tiêu chí đo lường “thành công” rõ ràng.",
            "Mối liên hệ nhân-quả giữa các yếu tố chưa được kiểm chứng.",
        ],
        "risks": [
            "Chi phí/thời gian vượt dự kiến khi quy mô hóa.",
            "Phụ thuộc giả định chưa được xác nhận.",
        ],
        "next_steps": [
            "Thu hẹp giả thuyết thành 1 câu kiểm chứng được.",
            "Thiết kế thí nghiệm tối thiểu (MVP/PoC) đo 1 biến số.",
            "Mô phỏng nhanh kịch bản cơ sở rồi đối chiếu kết quả.",
            "Lặp lại: điều chỉnh tham số → đo → học.",
        ],
        "resources": [
            "Bộ dữ liệu mở liên quan chủ đề.",
            "Công cụ mô phỏng/whiteboard ngay trong Lab.",
            "Tra cứu sâu (Search) để lấp lỗ hổng kiến thức.",
        ],
        # First-principles: break the problem down to its underlying structure so we
        # can attack it from the root, not from what papers already say.
        "first_principles": [
            "Mổ xẻ vấn đề về cấu trúc gốc: đâu là ràng buộc vật lý/toán học THẬT, đâu chỉ là quy ước.",
            "Định vị điểm nghẽn cốt lõi (bottleneck) — nơi mọi giải pháp hiện tại đều vấp.",
            "Hỏi ngược: 'vì sao bắt buộc phải làm thế này?' — tìm giả định có thể phá bỏ.",
        ],
        # Breakthrough paths: the feasible 1% — alternative angles to TRY, not reasons to quit.
        "breakthrough_paths": [
            {"path": "Ghép mảnh kỹ thuật mới chưa ai kết hợp", "why": "Lời giải thường nằm ở giao của 2-3 kỹ thuật vừa xuất hiện.", "feasible": True},
            {"path": "Đổi cấu trúc dữ liệu/biểu diễn vấn đề", "why": "Cùng bài toán, biểu diễn khác có thể bỏ qua hẳn điểm nghẽn.", "feasible": True},
        ],
        "simulated": True,
    }


_FACTOR_WEIGHTS = {"technical": 0.32, "evidence": 0.24, "resources": 0.18, "value": 0.14, "novelty": 0.12}


def _coerce(report: Dict[str, Any], idea: str) -> Dict[str, Any]:
    """Normalize an LLM report into the shape the UI expects. The headline
    feasibility is DERIVED from the per-factor scores (weighted), so it reflects a
    real multi-factor judgement instead of an arbitrary number the model emitted."""
    base = _simulate(idea)
    if not isinstance(report, dict):
        return base

    factors = report.get("factors") if isinstance(report.get("factors"), list) else []
    clean_factors = []
    total, wsum = 0.0, 0.0
    for f in factors:
        if not isinstance(f, dict):
            continue
        key = str(f.get("key", "")).strip().lower()
        try:
            score = max(0, min(100, int(round(float(f.get("score"))))))
        except Exception:
            continue
        clean_factors.append({"key": key, "score": score, "note": str(f.get("note") or "").strip()})
        w = _FACTOR_WEIGHTS.get(key, 0.0)
        if w > 0:
            total += score * w
            wsum += w

    if wsum > 0:
        feasibility = int(round(total / wsum))          # grounded in the factors
    else:
        feasibility = int(report.get("feasibility", base["feasibility"]) or base["feasibility"])
    feasibility = max(0, min(100, feasibility))

    verdict = str(report.get("verdict") or "").strip()
    if not verdict:
        verdict = "Đột phá" if feasibility < 50 else ("Thách thức" if feasibility < 70 else "Khả thi")

    out = {
        "factors": clean_factors,
        "feasibility": feasibility,
        "verdict": verdict,
        "summary": str(report.get("summary") or base["summary"]),
        "scenarios": report.get("scenarios") if isinstance(report.get("scenarios"), list) else base["scenarios"],
        "gaps": report.get("gaps") if isinstance(report.get("gaps"), list) else base["gaps"],
        "risks": report.get("risks") if isinstance(report.get("risks"), list) else base["risks"],
        "next_steps": report.get("next_steps") if isinstance(report.get("next_steps"), list) else base["next_steps"],
        "resources": report.get("resources") if isinstance(report.get("resources"), list) else base["resources"],
        "first_principles": report.get("first_principles") if isinstance(report.get("first_principles"), list) else base["first_principles"],
        "breakthrough_paths": report.get("breakthrough_paths") if isinstance(report.get("breakthrough_paths"), list) else base["breakthrough_paths"],
        "simulated": False,
    }
    return out


@router.post("/analyze")
async def analyze(payload: Dict[str, Any] = Body(...)):
    idea = str(payload.get("idea", "")).strip()
    if not idea:
        return {"success": False, "error": "Hãy nhập ý tưởng hoặc giả thuyết."}
    lang = str(payload.get("language", "vi")).strip() or "vi"
    prompt = (
        "Bạn là CỘNG SỰ R&D trung thành, liều lĩnh và thực chiến — KHÔNG phải kẻ bàn lùi. Người dùng ném vào một "
        "ý tưởng có thể 'điên rồ', chưa ai làm, hoặc bị coi là bất khả thi hiện nay. NHIỆM VỤ của bạn: TƯ DUY TỪ "
        "NGUYÊN BẢN (first-principles) để tìm ra 1% khả thi còn sót lại và con đường biến nó thành thật — KHÔNG "
        "làm người dùng nhụt chí, KHÔNG bẻ lái sang ý tưởng khác. Nhưng cũng TUYỆT ĐỐI không phán đại/nói dối: "
        "phần cứng và định luật vật lý là trọng tài tối cao.\n\n"
        "Đừng chỉ tổng hợp lại bài báo có sẵn. Hãy MỔ XẺ cấu trúc/kiến trúc gốc của vấn đề, tìm ĐIỂM NGHẼN thật, "
        "và đề xuất giải pháp THAY THẾ khả thi (ghép các mảnh kỹ thuật mới, đổi cách biểu diễn, bỏ một giả định "
        "mà ai cũng tưởng là bắt buộc).\n\n"
        "Chấm điểm 0-100 cho TỪNG yếu tố, kèm 1 câu lý do ngắn dựa trên hiểu biết thực tế:\n"
        " 1. technical  — khả thi về kỹ thuật/khoa học khi tư duy nguyên bản (không chỉ theo cách phổ biến).\n"
        " 2. resources  — mức nguồn lực (tiền, thời gian, dữ liệu) cần — điểm CAO = cần ÍT.\n"
        " 3. novelty    — độ mới: ý tưởng chưa ai làm? (điểm cao = mới/độc đáo).\n"
        " 4. value      — nếu làm được thì tác động lớn cỡ nào (đột phá thì điểm cao).\n"
        " 5. evidence   — có mảnh ghép/tiền lệ/khoa học nào ỦNG HỘ con đường khả thi (điểm cao = có cơ sở).\n\n"
        "QUAN TRỌNG: ý tưởng CHƯA TỪNG CÓ nhưng có con đường kỹ thuật khả thi và giá trị lớn = 'Đột phá' và "
        "feasibility VẪN có thể cao. Đừng hạ điểm chỉ vì nó mới hay vì 'thế giới bảo khó'. Chỉ hạ điểm khi vi "
        "phạm định luật vật lý hoặc không tìm ra bất kỳ con đường nào.\n\n"
        f"Ý TƯỞNG:\n{idea}\n\n"
        "feasibility tổng = trung bình có trọng số: technical 0.32, evidence 0.24, resources 0.18, value 0.14, novelty 0.12 "
        "(làm tròn số nguyên). verdict: <50 'Đột phá' (mới & rủi ro cao nhưng ĐÁNG theo đuổi), 50-69 'Thách thức', >=70 'Khả thi'.\n\n"
        "Trả về DUY NHẤT một JSON:\n"
        '{"factors":[{"key":"technical","score":<0-100>,"note":"..."},{"key":"resources","score":<0-100>,"note":"..."},'
        '{"key":"novelty","score":<0-100>,"note":"..."},{"key":"value","score":<0-100>,"note":"..."},'
        '{"key":"evidence","score":<0-100>,"note":"..."}],'
        '"feasibility":<0-100>,"verdict":"<Khả thi|Thách thức|Đột phá>","summary":"<2-3 câu: tin tưởng nhưng thực tế, nêu con đường khả thi nhất>",'
        '"first_principles":["<mổ xẻ cấu trúc gốc & điểm nghẽn thật, 3-4 ý>"],'
        '"breakthrough_paths":[{"path":"<một hướng đột phá cụ thể để THỬ>","why":"<vì sao nó có thể phá được giới hạn>","feasible":<true|false>}],'
        '"scenarios":[{"name":"...","outcome":"...","probability":<0-100>}],'
        '"gaps":["<lỗ hổng/vết nứt công nghệ có thể khai thác>"],"risks":["..."],"next_steps":["<bước thực nghiệm cụ thể, đo được bằng code/phần cứng>"],"resources":["..."]}'
    )
    # Generous timeout so a cold-start of the big cloud model doesn't fall back to
    # the heuristic estimate (which the user rightly dislikes as "phán đại").
    raw = await _llm(prompt, timeout=110.0)
    report = _coerce(_extract_json(raw), idea) if raw else _simulate(idea)
    return {"success": True, "id": uuid.uuid4().hex[:10], "idea": idea, "report": report, "ts": int(time.time())}


@router.post("/simulate")
async def simulate_step(payload: Dict[str, Any] = Body(...)):
    """Run one quick what-if iteration on a hypothesis with an adjusted variable."""
    hypo = str(payload.get("hypothesis", "")).strip()
    change = str(payload.get("change", "")).strip()
    if not hypo:
        return {"success": False, "error": "Thiếu giả thuyết."}
    prompt = (
        "Mô phỏng nhanh kết quả của một thí nghiệm tư duy. "
        f"Giả thuyết: {hypo}\nThay đổi/điều chỉnh: {change or 'không'}\n"
        "Trả về JSON {\"result\":\"...\",\"confidence\":<0-100>,\"insight\":\"...\"}."
    )
    raw = await _llm(prompt, timeout=40.0)
    data = _extract_json(raw) if raw else None
    if not isinstance(data, dict):
        data = {
            "result": f"[mô phỏng] Với điều chỉnh “{change or 'mặc định'}”, kết quả nghiêng về hướng tích cực một phần.",
            "confidence": random.randint(45, 82),
            "insight": "Biến số vừa đổi ảnh hưởng rõ tới đầu ra — đáng để thử nghiệm thực tế ở quy mô nhỏ.",
        }
    return {"success": True, "data": data}


@router.post("/prototype")
async def prototype(payload: Dict[str, Any] = Body(...)):
    """Ask the model to turn an idea into a SELF-CONTAINED, RUNNABLE JavaScript
    prototype + concrete test cases. The frontend then actually EXECUTES it in a
    sandboxed Web Worker, so success/failure is real (the code runs against the
    tests), not the model's opinion."""
    idea = str(payload.get("idea", "")).strip()
    if not idea:
        return {"success": False, "error": "Thiếu ý tưởng."}
    prompt = (
        "Bạn là kỹ sư. Hãy biến Ý TƯỞNG dưới đây thành một NGUYÊN MẪU JAVASCRIPT CHẠY ĐƯỢC để kiểm chứng "
        "phần lõi có thể tính toán/kiểm thử được. Viết MỘT hàm thuần `function solve(input){...}` (không phụ thuộc "
        "thư viện ngoài, không I/O, không async), và 3-6 ca kiểm thử cụ thể với input và expected RÕ RÀNG để có "
        "thể so khớp tự động. Nếu ý tưởng trừu tượng, hãy mô hình hoá phần định lượng được của nó (vd: thuật toán, "
        "công thức, logic ra quyết định).\n\n"
        f"Ý TƯỞNG:\n{idea}\n\n"
        "Trả về DUY NHẤT JSON:\n"
        '{"language":"js","explanation":"<1-2 câu giải thích nguyên mẫu mô hình hoá điều gì>",'
        '"code":"function solve(input){ /* ... */ return ...; }",'
        '"tests":[{"name":"...","input":<JSON bất kỳ>,"expected":<JSON>}]}'
        "\nLƯU Ý: code phải là chuỗi JSON hợp lệ (escape xuống dòng \\n). input/expected là giá trị JSON thật."
    )
    raw = await _llm(prompt, timeout=110.0)
    data = _extract_json(raw) if raw else None
    if not isinstance(data, dict) or not str(data.get("code") or "").strip():
        return {"success": False, "error": "Model chưa tạo được nguyên mẫu chạy được. Thử lại hoặc đổi cách diễn đạt ý tưởng."}
    tests = data.get("tests") if isinstance(data.get("tests"), list) else []
    clean_tests = []
    for t in tests:
        if isinstance(t, dict) and "expected" in t:
            clean_tests.append({"name": str(t.get("name") or f"Test {len(clean_tests)+1}"),
                                "input": t.get("input"), "expected": t.get("expected")})
    return {
        "success": True,
        "language": "js",
        "explanation": str(data.get("explanation") or ""),
        "code": str(data.get("code")),
        "tests": clean_tests,
        "id": uuid.uuid4().hex[:10],
    }


@router.post("/research")
async def research(payload: Dict[str, Any] = Body(...)):
    """Long-term R&D engine (token-economical). ONE batched LLM call decomposes the
    problem from first principles into 2-4 TESTABLE hypotheses, each carrying a
    self-contained `function solve(input){...}` + tests. The frontend then RUNS each
    prototype in a sandboxed Web Worker (0 tokens — pure code, hardware is the
    referee) and logs the outcome to the R&D Live Chronicle. A hypothesis whose tests
    all pass is a real breakthrough candidate; failures are honest dead-ends to iterate
    on — never the model's optimistic opinion."""
    idea = str(payload.get("idea", "")).strip()
    if not idea:
        return {"success": False, "error": "Thiếu vấn đề/ý tưởng nghiên cứu."}
    context = str(payload.get("context", "")).strip()      # knowledge-map / search context
    prior = str(payload.get("prior", "")).strip()          # what earlier rounds found
    prompt = (
        "Bạn là CỘNG SỰ R&D tư duy nguyên bản (first-principles), đồng hành cùng người dùng hiện thực hoá một ý "
        "tưởng có thể bị coi là bất khả thi. KHÔNG bàn lùi. Hãy MỔ XẺ vấn đề tới cấu trúc gốc rồi đề xuất ĐÚNG 2-3 "
        "GIẢ THUYẾT KHÁC NHAU, mỗi giả thuyết là một con đường có thể phá vỡ giới hạn — ưu tiên kiểm chứng được "
        "bằng CODE chạy thật (không nói suông). Giữ code NGẮN GỌN.\n\n"
        f"VẤN ĐỀ:\n{idea}\n"
        + (f"\nBỐI CẢNH TỪ BẢN ĐỒ TRI THỨC / SEARCH:\n{context[:1500]}\n" if context else "")
        + (f"\nVÒNG TRƯỚC ĐÃ TÌM RA:\n{prior[:1200]}\n" if prior else "")
        + "\nVới MỖI giả thuyết: nếu có phần ĐỊNH LƯỢNG ĐƯỢC (công thức, thuật toán, đánh đổi bộ nhớ/tốc độ, "
        "logic ra quyết định), hãy viết một hàm thuần `function solve(input){...}` (không thư viện ngoài, không "
        "async, không I/O) + 2-5 ca kiểm thử input/expected rõ ràng để MÁY TỰ CHẤM đúng/sai — đây là cách đẩy việc "
        "tính toán cho CODE THUẦN (0 token, phần cứng làm trọng tài). Nếu giả thuyết còn trừu tượng, để code rỗng "
        "\"\" nhưng PHẢI mô tả 'test_plan' = cách thí nghiệm thật để kiểm chứng. Ưu tiên có ÍT NHẤT 1 giả thuyết "
        "có code chạy được.\n\n"
        "Trả về DUY NHẤT JSON:\n"
        '{"first_principles":["<mổ xẻ cấu trúc gốc & điểm nghẽn, 2-4 ý>"],'
        '"hypotheses":[{"name":"<tên ngắn>","idea":"<giả thuyết này phá giới hạn bằng cách nào>",'
        '"code":"function solve(input){ /* ... */ return ...; }" hoặc "",'
        '"tests":[{"name":"...","input":<JSON>,"expected":<JSON>}],'
        '"test_plan":"<nếu không có code: cách thí nghiệm thật để kiểm chứng>"}],'
        '"verdict_hint":"<1 câu: hướng nào đáng dồn sức nhất>"}'
        "\nLƯU Ý: code là chuỗi JSON hợp lệ. Tối đa 3 giả thuyết, code ngắn — để JSON không bị cắt giữa chừng."
    )
    raw = await _llm(prompt, timeout=120.0, num_predict=2800)
    data = _extract_json(raw) if raw else None
    hyps_in = (data or {}).get("hypotheses") if isinstance(data, dict) else None
    hypotheses: List[Dict[str, Any]] = []
    if isinstance(hyps_in, list):
        for h in hyps_in[:4]:
            if not isinstance(h, dict):
                continue
            name = str(h.get("name") or "").strip()
            idea_txt = str(h.get("idea") or "").strip()
            code = str(h.get("code") or "").strip()
            if not (name or idea_txt) and not code:
                continue
            tests = []
            for t in (h.get("tests") if isinstance(h.get("tests"), list) else []):
                if isinstance(t, dict) and "expected" in t:
                    tests.append({"name": str(t.get("name") or f"Test {len(tests)+1}"),
                                  "input": t.get("input"), "expected": t.get("expected")})
            # A hypothesis is "code"-verifiable only if it carries runnable code AND
            # at least one test; otherwise it's a "concept" to design a real experiment for.
            kind = "code" if (code and tests) else "concept"
            hypotheses.append({
                "id": uuid.uuid4().hex[:8],
                "name": name or "Giả thuyết",
                "idea": idea_txt,
                "kind": kind,
                "code": code,
                "tests": tests,
                "test_plan": str(h.get("test_plan") or "").strip(),
            })
    if not hypotheses:
        return {"success": False, "error": "Chưa dựng được giả thuyết vòng này — thử diễn đạt vấn đề cụ thể hơn, hoặc bấm nghiên cứu thêm một vòng."}
    fp = (data or {}).get("first_principles")
    return {
        "success": True,
        "id": uuid.uuid4().hex[:10],
        "idea": idea,
        "first_principles": fp if isinstance(fp, list) else [],
        "hypotheses": hypotheses,
        "verdict_hint": str((data or {}).get("verdict_hint") or ""),
        "ts": int(time.time()),
    }
