"""What a student's phone is allowed to see. Correct answers and explanations are NEVER
included here (EDAY-07, NFR-07)."""
import copy
import random


def _shuffled(lst, rnd, avoid=None):
    out = list(lst)
    for _ in range(5):
        rnd.shuffle(out)
        if avoid is None or [x["id"] for x in out] != avoid:
            break
    return out


def public_question(eq, seed, shuffle_options):
    p = eq.payload
    rnd = random.Random(f"{seed}:{eq.pk}")  # stable for the same student, different per student
    content = copy.deepcopy(p.get("content", {}))
    qtype = p["qtype"]
    if qtype in ("mcq_single", "mcq_multi") and shuffle_options:
        content["options"] = _shuffled(content["options"], rnd)
    if qtype == "matching":
        content["right"] = _shuffled(content["right"], rnd)
    if qtype == "ordering":  # must never arrive in the correct order
        content["items"] = _shuffled(content["items"], rnd, avoid=p["answer"]["order"])
    return {"id": eq.pk, "type": qtype, "prompt": p["prompt"], "marks": p["marks"], "content": content}
