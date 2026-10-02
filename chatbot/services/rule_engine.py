"""Chat ka dimaag — 100% traditional logic, koi AI call nahi.

Yahan decide hota hai ki user ke message ka bot reply kya hoga:

1. SAFETY PEHLE   — smoke/fire/brake failure jaise critical words ho to
                    turant warning, baaki kuch nahi (safety > sab).
2. SYMPTOM MATCH  — knowledge base ke patterns se pata karo kaunsi category
                    (brakes, overheating, ...) hai, phir explanation +
                    agla follow-up sawaal do.
3. FOLLOW-UP      — agar user bina keywords ke jawab de raha hai (context
                    pehle se hai), to agla sawaal poochho ya batao ki
                    diagnosis ke liye ready hain.
4. TOPIC GATE     — greeting / thanks / vague / car-related / off-topic
                    ko alag-alag handle karo. Car se bahar ki baat ho to
                    politely reject karo.

Ye file sirf REPLY ka text decide karti hai (dict return karti hai).
Message ko DB mein save karna view ka kaam hai — separation of concerns.
"""

from ..models import Message
from . import knowledge_base as kb


def generate_reply(conversation, user_message):
    """User ke message ka bot reply decide karta hai.

    user_message = abhi DB mein save hua Message object (view ise pehle
    save karta hai, phir ye function call karta hai). Isse hum current
    message ko history se alag rakh paate hain.

    Returns dict: {'content': <reply text>, 'generated_by': 'rule_engine'}
    """
    text = user_message.content.strip().lower()

    # History se context nikalo — current message ko chhod kar.
    context_ids = _context_category_ids(conversation, exclude_id=user_message.pk)
    asked_text = _assistant_text(conversation)

    # 1) Safety sabse pehle — kuch bhi critical ho to normal flow skip.
    safety_message = kb.find_safety_hit(text)
    if safety_message:
        return _reply(_with_greeting(text, safety_message))

    # 2) Symptom keywords dhoondho.
    matches = kb.find_symptoms(text)
    if matches:
        return _reply(_with_greeting(text, _symptom_reply(context_ids, asked_text, matches)))

    # 3) Simple topic replies (symptom nahi hai is message mein).
    if kb.is_greeting(text):
        return _reply(kb.GREETING_REPLY)
    if kb.is_thanks(text):
        return _reply(kb.THANKS_REPLY)

    # 4) Agar conversation pehle se kisi symptom ke baare mein hai, to
    #    ye message usi ka follow-up answer hai (bina keywords ke bhi).
    if context_ids:
        return _reply(_with_greeting(text, _followup_reply(asked_text, context_ids)))

    if kb.is_help_question(text):
        return _reply(kb.HELP_REPLY)
    if kb.is_vague(text):
        return _reply(kb.VAGUE_REPLY)
    if kb.mentions_car(text):
        # Car ki baat ho rahi hai lekin humein samajh nahi aaya — yehi ek
        # jagah hai jahan rules haath khade karte hain. needs_nlu=True ka
        # matlab: view Gemini ko ek chance de (fail ho to yehi reply chalta hai).
        return _reply(kb.CAR_UNCLEAR_REPLY, needs_nlu=True)
    return _reply(kb.OFF_TOPIC_REPLY)


def _reply(content, needs_nlu=False):
    """Final reply dict banao — default hamesha rule_engine se generate hua.

    needs_nlu=True sirf tab hota hai jab rule engine ko message samajh nahi
    aaya (fuzzy car description). View ise dekh kar Gemini ko try karta hai;
    Gemini na chale to yahi reply user tak jata hai — kabhi khali haath nahi.
    """
    return {
        'content': content,
        'generated_by': Message.GeneratedBy.RULE_ENGINE,
        'needs_nlu': needs_nlu,
    }


def _with_greeting(text, content):
    """Agar message 'hello' se shuru hua tha to reply ke aage 'Hello!' laga do."""
    if kb.is_greeting(text):
        return 'Hello! ' + content
    return content


def _symptom_reply(context_ids, asked_text, matches):
    """Symptom wale message ka reply: explanation + agla unasked sawaal.

    - Naya symptom: poora explanation + pehla sawaal.
    - Dobara wahi symptom: chhota 'Got it — noted.' + agla sawaal.
    - Saare sawaal poochh liye: READY_FOR_DIAGNOSIS message.
    - Ek reply mein zyada se zyada 2 categories handle karte hain.
    """
    blocks = []
    question = None
    for category, _found_terms in matches[:2]:
        if category['id'] in context_ids:
            blocks.append('Got it — noted.')
        else:
            blocks.append(category['explain'])
        if question is None:
            question = _next_question(category, asked_text)

    # Do same blocks ho sakte hain (jaise do baar 'Got it — noted.')
    # — dict.fromkeys se order banaye rakhte hue duplicates hata do.
    blocks = list(dict.fromkeys(blocks))

    reply = '\n\n'.join(blocks)
    if question:
        return reply + '\n\n' + question
    return reply + '\n\n' + kb.READY_FOR_DIAGNOSIS


def _followup_reply(asked_text, context_ids):
    """User ka aisa message jisme symptom keywords nahi hain, lekin
    conversation pehle se ek category ke baare mein hai — matlab user
    kisi sawaal ka jawab de raha hai. Agla sawaal poochho, ya agar saare
    poochh liye to batao ki diagnosis ready hai.
    """
    category = kb.get_category(context_ids[-1])
    if category is None:
        return kb.CAR_UNCLEAR_REPLY

    question = _next_question(category, asked_text)

    prefix = 'Noted, thanks — that helps.'
    if question:
        return prefix + '\n\n' + question
    return prefix + '\n\n' + kb.READY_FOR_DIAGNOSIS


def _context_category_ids(conversation, exclude_id=None):
    """Purane user messages mein kaunsi categories aayi thi — order mein.

    exclude_id se current message ko history se bahar rakhte hain
    (warna woh khud ko 'pehle dekha hua' count kar lega).

    List ka aakhri item = sabse recently introduce hui category,
    wahi 'current focus' maana jata hai.
    """
    ids = []
    user_messages = conversation.messages.filter(
        role=Message.Role.USER
    ).exclude(pk=exclude_id).order_by('created_at')
    for message in user_messages:
        for category, _found_terms in kb.find_symptoms(message.content.lower()):
            if category['id'] not in ids:
                ids.append(category['id'])
    return ids


def _assistant_text(conversation):
    """Assistant ke saare purane replies ka ek bada lowercase text.

    Isse hum check karte hain ki koi sawaal pehle poochha ja chuka hai kya —
    sawaal ka text hi hamara memory hai, koi extra DB field nahi chahiye.
    """
    replies = conversation.messages.filter(
        role=Message.Role.ASSISTANT
    ).order_by('created_at')
    return ' '.join(message.content.lower() for message in replies)


def _next_question(category, asked_text):
    """Category ka pehla aisa sawaal jo abhi tak poochha nahi gaya.

    Saare poochh liye gaye to None return karta hai.
    """
    for question in category['questions']:
        if question.lower() not in asked_text:
            return question
    return None
