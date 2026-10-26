"""Server-side validation of a question before it is saved (QB-08)."""
import re
import uuid

from rest_framework.exceptions import ValidationError

from core.sanitize import clean_html

TEXT_LIMIT = 2000


def _items(content, key, minimum, maximum=None):
    items = content.get(key)
    if not isinstance(items, list) or len(items) < minimum or (maximum and len(items) > maximum):
        rng = f"{minimum} to {maximum}" if maximum else f"at least {minimum}"
        raise ValidationError({"content": f"'{key}' needs {rng} entries."})
    out, ids = [], set()
    for it in items:
        text = clean_html(str(it.get("text", "")))[:TEXT_LIMIT]
        image = it.get("image") or None
        if not text and not image:
            raise ValidationError({"content": f"Every entry in '{key}' needs text or an image."})
        if image and not str(it.get("alt_text", "")).strip():
            raise ValidationError({"content": "Every image needs a short description (alt text)."})
        iid = str(it.get("id") or uuid.uuid4().hex[:8])
        if iid in ids:
            raise ValidationError({"content": f"Duplicate id '{iid}' in '{key}'."})
        ids.add(iid)
        out.append({"id": iid, "text": text, "image": image, "alt_text": it.get("alt_text", "")})
    return out


def validate_question(qtype, content, answer):
    """Return (clean_content, clean_answer) or raise ValidationError."""
    content, answer = content or {}, answer or {}

    if qtype in ("mcq_single", "mcq_multi"):
        opts = _items(content, "options", 2, 6)
        ids = {o["id"] for o in opts}
        if qtype == "mcq_single":
            c = answer.get("correct")
            if c not in ids:
                raise ValidationError({"answer": "Choose exactly one correct option."})
            return {"options": opts}, {"correct": c}
        c = answer.get("correct")
        if not isinstance(c, list) or not c or not set(c) <= ids:
            raise ValidationError({"answer": "Choose at least one correct option."})
        return {"options": opts}, {"correct": sorted(set(c))}

    if qtype == "true_false":
        if not isinstance(answer.get("correct"), bool):
            raise ValidationError({"answer": "Say whether the statement is true or false."})
        return {}, {"correct": answer["correct"]}

    if qtype == "matching":
        left, right = _items(content, "left", 2), _items(content, "right", 2)
        pairs = answer.get("pairs")
        lids, rids = {x["id"] for x in left}, {x["id"] for x in right}
        if not isinstance(pairs, dict) or set(pairs) != lids or not set(pairs.values()) <= rids:
            raise ValidationError({"answer": "Every item on the left must be matched to an item on the right."})
        return {"left": left, "right": right}, {"pairs": pairs}

    if qtype == "fill_blank":
        accepted = [str(a).strip() for a in (answer.get("accepted") or []) if str(a).strip()]
        numeric = answer.get("numeric")
        if numeric is not None:
            try:
                numeric = {"value": float(numeric["value"]), "tolerance": abs(float(numeric.get("tolerance", 0)))}
            except (KeyError, TypeError, ValueError):
                raise ValidationError({"answer": "Numeric answer needs a value and a tolerance."})
        if not accepted and numeric is None:
            raise ValidationError({"answer": "Give at least one accepted answer."})
        return {}, {"accepted": accepted, "numeric": numeric}

    if qtype == "ordering":
        items = _items(content, "items", 2, 10)  # authored in the correct order
        return {"items": items}, {"order": [i["id"] for i in items]}

    raise ValidationError({"qtype": "Unknown question type."})


def clean_prompt(prompt):
    prompt = clean_html(prompt)
    if not re.sub(r"<[^>]+>|\s", "", prompt):
        raise ValidationError({"prompt": "The question text is empty."})
    return prompt[:5000]
