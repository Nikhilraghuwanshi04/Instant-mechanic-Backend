"""Diagnosis engine: conversation ke history se structured diagnosis.

Yahan 100% traditional logic chalti hai — koi AI call nahi:
1. Conversation ke SAARE user messages ko knowledge_base ke symptom
   patterns se scan karo (multiple messages = zyada evidence).
2. Sabse pehle match hone wali category (KB priority order) = PRIMARY
   symptom; baaki sab = secondary symptoms.
3. Confidence = primary category ke kitne ALAG terms mile:
   1 term -> low, 2 terms -> medium, 3+ terms -> high.
4. can_drive sirf tab True jab HAR detected category safe ho AUR koi
   SAFETY_RULE hit na hua ho. Safety hit = turant can_drive False.
5. Kuch bhi match na ho -> needs_nlu True. Ye ek handoff signal hai:
   Phase 6 mein view is flag ko dekh kar Gemini se diagnosis karwayega.

Har diagnosis record `generated_by` field se batata hai ki answer kahan
se aaya — ye hamara audit trail hai.
"""

from ..models import Diagnosis, Message
from . import knowledge_base as kb


def generate_diagnosis(conversation):
    """Conversation ke saare user messages se structured diagnosis banao.

    Returns ek dict jisme Diagnosis model ke saare fields hote hain.
    View is dict ko pakad kar DB mein Diagnosis record banata hai.
    """
    user_messages = conversation.messages.filter(
        role=Message.Role.USER
    ).order_by('created_at')

    matched = _collect_matches(user_messages)
    safety_flags = _collect_safety_flags(user_messages)

    if not matched:
        return _needs_nlu_diagnosis(user_messages.count(), safety_flags)

    primary_category, primary_terms = matched[0]
    secondary = [
        {'id': category['id'], 'label': category['label']}
        for category, _terms in matched[1:]
    ]

    if safety_flags:
        next_step = safety_flags[0] + ' ' + primary_category['next_step']
    else:
        next_step = primary_category['next_step']

    return {
        'summary': {
            'user_messages_analyzed': user_messages.count(),
            'primary_symptom': {
                'id': primary_category['id'],
                'label': primary_category['label'],
            },
            'matched_terms': primary_terms,
            'secondary_symptoms': secondary,
            'safety_flags': safety_flags,
        },
        'likely_issue': primary_category['likely_issue'],
        'reasoning': _build_reasoning(primary_category, secondary, safety_flags),
        'confidence': _confidence_for(primary_terms),
        'can_drive': (
            not safety_flags
            and all(category['can_drive'] for category, _terms in matched)
        ),
        'next_step': next_step,
        'recommended_service': primary_category['recommended_service'],
        'generated_by': Diagnosis.GeneratedBy.RULE_ENGINE,
        'needs_nlu': False,
    }


def _collect_matches(user_messages):
    """Saare messages scan karke category-wise unique terms ikattha karo.

    Pehle har category ke liye ek entry banao (id -> category + terms),
    phir sabko KB priority order mein sort karo. Returns:
    [(category_dict, [unique_terms]), ...] — pehla item = primary symptom.
    """
    per_category = {}
    for message in user_messages:
        for category, found_terms in kb.find_symptoms(message.content.lower()):
            entry = per_category.setdefault(
                category['id'], {'category': category, 'terms': []}
            )
            for term in found_terms:
                if term not in entry['terms']:
                    entry['terms'].append(term)

    priority = {
        category['id']: index
        for index, category in enumerate(kb.SYMPTOM_CATEGORIES)
    }
    ordered = sorted(
        per_category.values(),
        key=lambda entry: priority[entry['category']['id']],
    )
    return [(entry['category'], entry['terms']) for entry in ordered]


def _collect_safety_flags(user_messages):
    """Har message pe safety check — unique safety warnings ki list."""
    flags = []
    for message in user_messages:
        hit = kb.find_safety_hit(message.content.lower())
        if hit and hit not in flags:
            flags.append(hit)
    return flags


def _confidence_for(terms):
    """Primary symptom ke distinct terms se confidence — transparent rule."""
    if len(terms) >= 3:
        return Diagnosis.Confidence.HIGH
    if len(terms) == 2:
        return Diagnosis.Confidence.MEDIUM
    return Diagnosis.Confidence.LOW


def _build_reasoning(primary_category, secondary, safety_flags):
    """Primary ki reasoning + secondary symptoms + safety note — jodkar bolo."""
    blocks = [primary_category['reasoning']]
    if secondary:
        labels = ', '.join(item['label'] for item in secondary)
        blocks.append(f'The conversation also mentions issues in: {labels}.')
    if safety_flags:
        blocks.append(
            'A safety-critical symptom was reported, so the advice is to be '
            'extra cautious.'
        )
    return ' '.join(blocks)


def _needs_nlu_diagnosis(message_count, safety_flags):
    """Kuch bhi match nahi hua — rule engine honestly bolta hai 'mujhe nahi pata'.

    needs_nlu=True ek handoff signal hai: Phase 6 mein view is flag ko dekh
    kar Gemini se diagnosis karwayega. Abhi conservative answer jata hai.
    """
    return {
        'summary': {
            'user_messages_analyzed': message_count,
            'primary_symptom': None,
            'matched_terms': [],
            'secondary_symptoms': [],
            'safety_flags': safety_flags,
        },
        'likely_issue': 'Insufficient information for a rule-based diagnosis',
        'reasoning': (
            'The conversation so far does not match any known symptom pattern. '
            'The rule engine is honest about this instead of guessing — a '
            'deeper language analysis is needed.'
        ),
        'confidence': Diagnosis.Confidence.LOW,
        'can_drive': False,
        'next_step': (
            'Not enough detail to say the car is safe to drive. Add more '
            'symptoms in the chat — when it happens, what it sounds, feels or '
            'smells like — or book a general inspection.'
        ),
        'recommended_service': 'General inspection',
        'generated_by': Diagnosis.GeneratedBy.RULE_ENGINE,
        'needs_nlu': True,
    }
