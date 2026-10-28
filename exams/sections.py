"""Paper sections. Questions are grouped by type into lettered sections (A, B, C ...) in a fixed order.
Only sections that have questions get a letter, so a paper with MCQ and matching only is A and B."""

SECTION_ORDER = [
    ("mcq_single", "Multiple choice (one answer)", "Choose the one correct answer."),
    ("mcq_multi", "Multiple choice (several answers)", "Choose every correct answer."),
    ("true_false", "True or false", "Say whether each statement is true or false."),
    ("matching", "Matching", "Match each item on the left with the correct item on the right."),
    ("fill_blank", "Fill in the blank", "Write the missing answer."),
    ("ordering", "Ordering", "Put the items in the correct order."),
]
RANK = {k: i for i, (k, _, _) in enumerate(SECTION_ORDER)}


def qtype_rank(qtype):
    return RANK.get(qtype, len(SECTION_ORDER))


def letters(qtypes):
    """{qtype: 'A'} for the types present, in section order."""
    have = set(qtypes)
    present = [k for k, _, _ in SECTION_ORDER if k in have]
    return {k: chr(ord("A") + i) for i, k in enumerate(present)}
