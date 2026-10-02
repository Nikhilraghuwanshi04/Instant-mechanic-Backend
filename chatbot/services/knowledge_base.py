"""Automotive knowledge base — saara car ka DATA yahan, logic nahi.

Is file mein sirf teen cheezein hain:
1. SYMPTOM_CATEGORIES — har common problem (brakes, overheating, ...) ke liye:
   - patterns: keywords jinse ye problem detect hoti hai (label + regex)
   - explain: senior technician style explanation
   - questions: 2 follow-up sawaal (ek-ek karke poochhe jayenge)
   - diagnosis info: likely_issue, can_drive, next_step, recommended_service
2. SAFETY_RULES — critical cheezein (smoke, fire, brake failure) jo turant
   warning deserve karti hain, chahe koi bhi category ho.
3. Chhote helpers — text check karne ke liye (greeting? thanks? car ka zikr?).

Rule engine (chat reply) aur diagnosis engine (structured diagnosis) DONO
isi file ka data use karte hain. Knowledge ek jagah — update karo, dono
jagah apply ho jata hai.

NOTE: SYMPTOM_CATEGORIES ka ORDER = PRIORITY. Jo upar hai wo pehle
match hota hai (brakes sabse pehle kyunki safety sabse important).
"""

import re


def _compile(pattern_dict):
    """Dict {label: regex} ko [(label, compiled_regex), ...] bana deta hai.

    Regex ko pehle se compile kar lete hain (module load pe ek baar),
    taaki baar-baar match karne pe fast rahe.
    """
    return [
        (label, re.compile(pattern, re.IGNORECASE))
        for label, pattern in pattern_dict.items()
    ]


SYMPTOM_CATEGORIES = [
    {
        'id': 'brakes',
        'label': 'Brake system',
        'patterns': _compile({
            'brakes': r'brak',
            'squealing': r'squeal',
            'grinding': r'grind',
            'brake pedal': r'\bpedal\b',
            'spongy pedal': r'spong|mushy',
            'discs/rotors': r'\brotor|\bdisc\b',
            'brake pads': r'\bpads?\b',
        }),
        'explain': (
            "Brakes are your number one safety system, so let's take this "
            "seriously. Squealing usually points to worn pads, while grinding "
            "often means the pads are fully worn and metal is touching metal."
        ),
        'questions': [
            (
                'When do you notice it — every time you brake, or only when '
                'braking hard or downhill? And does the pedal feel firm or soft?'
            ),
            (
                'Roughly how long has this been happening, and has the noise '
                'or pedal feel gotten worse recently?'
            ),
        ],
        'can_drive': False,
        'likely_issue': 'Worn brake pads or a brake system fault',
        'reasoning': (
            'Brake noise and pedal changes typically come from worn pads, '
            'warped discs, or low brake fluid.'
        ),
        'next_step': (
            'Avoid long drives until a mechanic inspects the brakes — '
            'pads, discs and fluid check first.'
        ),
        'recommended_service': 'Brake inspection (pads, discs, fluid)',
    },
    {
        'id': 'overheating',
        'label': 'Engine overheating',
        'patterns': _compile({
            'overheating': r'overheat',
            'temperature': r'temperature|\btemp\b|gauge',
            'coolant': r'coolant',
            'radiator': r'radiator',
            'steam': r'steam',
            'thermostat': r'thermostat',
            'running hot': r'\bhot\b',
            'boiling': r'boil',
        }),
        'explain': (
            "Overheating can warp the engine or blow a head gasket if it's "
            "ignored, so good that you flagged it. The usual suspects are low "
            "coolant, a stuck thermostat, or a radiator fan that's not kicking in."
        ),
        'questions': [
            (
                'Does the temperature climb especially in traffic or at high '
                'speed, and do you see any steam or coolant spots under the car?'
            ),
            (
                'Is the coolant level in the reservoir low, and when did you '
                'first notice it running hot?'
            ),
        ],
        'can_drive': False,
        'likely_issue': 'Cooling system problem causing overheating',
        'reasoning': (
            'Overheating usually traces back to low coolant, a stuck '
            'thermostat, a clogged radiator, or a weak radiator fan.'
        ),
        'next_step': (
            'If the gauge climbs into the red, stop safely and let the engine '
            'cool. Never open the radiator cap while hot — get the cooling '
            'system inspected.'
        ),
        'recommended_service': 'Cooling system inspection (coolant, radiator, thermostat, fan)',
    },
    {
        'id': 'steering_suspension',
        'label': 'Steering and suspension',
        'patterns': _compile({
            'steering': r'steering',
            'wobble': r'wobbl|shimmy',
            'pulling to one side': r'pull(s|ing)? (to|toward)',
            'suspension': r'suspension',
            'shock absorbers': r'\bshock',
            'struts': r'\bstrut',
            'bushings': r'bush',
            'clunking': r'clunk',
            'alignment': r'alignment',
            'uneven tyre wear': r'uneven.*(tyre|tire)|(tyre|tire).*uneven',
        }),
        'explain': (
            "Steering and suspension issues affect how the car holds the "
            "road, so they're worth checking before they worsen. It's often "
            "alignment, worn bushes, or tired shock absorbers."
        ),
        'questions': [
            (
                'Does the car pull to one side or vibrate at a certain speed, '
                'and does the steering feel loose or heavy?'
            ),
            (
                'Any clunking over bumps, and when were the tyres and '
                'alignment last checked?'
            ),
        ],
        'can_drive': True,
        'likely_issue': 'Steering or suspension wear',
        'reasoning': (
            'Pulling, wobbling and clunking usually come from misalignment, '
            'worn suspension bushes, or tired shock absorbers.'
        ),
        'next_step': (
            'Get it checked soon and avoid high speeds for now. A wheel '
            'alignment and suspension inspection will pinpoint it.'
        ),
        'recommended_service': 'Steering and suspension inspection + wheel alignment',
    },
    {
        'id': 'battery_electrical',
        'label': 'Battery and electrical',
        'patterns': _compile({
            "won't start": r"won'?t start|doesn'?t start|no start|not start",
            'battery': r'battery',
            'clicking': r'click',
            'dead': r'\bdead\b',
            'dim lights': r'\bdim\b',
            'alternator': r'alternator',
            'starter motor': r'starter',
            'electrical': r'electric',
            'flickering lights': r'flicker',
        }),
        'explain': (
            "A no-start or a clicking sound usually points to the battery, "
            "alternator, or starter motor — and the good news is these are "
            "quick to test."
        ),
        'questions': [
            (
                'When you turn the key or press the start button, do you hear '
                'a single click, rapid clicking, or just silence?'
            ),
            (
                'Do the headlights look dim, and when was the battery last '
                'replaced?'
            ),
        ],
        'can_drive': True,
        'likely_issue': 'Battery or charging system issue',
        'reasoning': (
            'No-start, clicking and dim lights are classic signs of a weak '
            'battery, a failing alternator, or a tired starter motor.'
        ),
        'next_step': (
            'A jump start can get you moving temporarily — get the battery '
            'and charging system tested before you rely on the car.'
        ),
        'recommended_service': 'Battery and charging system test (battery, alternator, starter)',
    },
    {
        'id': 'transmission',
        'label': 'Transmission and clutch',
        'patterns': _compile({
            'transmission': r'transmission',
            'gearbox': r'gearbox',
            'gears': r'\bgear',
            'clutch': r'clutch',
            'shifting': r'shift',
            'slipping': r'slip',
            'jerking': r'\bjerk',
        }),
        'explain': (
            "Gear slip, hard shifts or a jerky drive usually trace back to "
            "the transmission fluid, the clutch, or the gearbox itself — "
            "the details matter here."
        ),
        'questions': [
            (
                'Does it slip or jerk when shifting, and is it worse when the '
                "car is cold or once it's warmed up?"
            ),
            (
                'Have you noticed any red fluid spots under the middle of the '
                'car, or a burning smell while driving?'
            ),
        ],
        'can_drive': True,
        'likely_issue': 'Transmission or clutch issue',
        'reasoning': (
            'Slipping and jerking between gears typically mean low or burnt '
            'transmission fluid, a worn clutch, or internal gearbox wear.'
        ),
        'next_step': (
            'Keep drives short and gentle until a mechanic checks the '
            'transmission fluid and clutch.'
        ),
        'recommended_service': 'Transmission and clutch inspection (fluid, linkage)',
    },
    {
        'id': 'warning_light',
        'label': 'Dashboard warning light',
        'patterns': _compile({
            'check engine light': r'check engine',
            'engine light': r'engine light',
            'warning light': r'warning light|warning lamp',
            'dashboard light': r'(dashboard|dash).{0,15}light|light.{0,15}(dashboard|dash)',
        }),
        'explain': (
            "A warning light means the car's computer has logged a fault "
            "code — it's the car telling you something needs attention, not "
            "automatically something catastrophic. Amber lights (like check "
            "engine) can usually wait for a scan; red lights (oil pressure, "
            "temperature, battery) need attention now."
        ),
        'questions': [
            (
                'Is the light steady or flashing — and does the car drive '
                'normally otherwise (any rough idle, power loss, or smells)?'
            ),
            (
                'How long has it been on, and did anything happen around the '
                'same time — a refuel, a service, or a dead battery?'
            ),
        ],
        'can_drive': True,
        'likely_issue': 'Dashboard warning light — fault code logged',
        'reasoning': (
            'A warning light means the engine control unit logged a fault '
            'code. A steady amber light usually allows a gentle drive to a '
            'workshop; a flashing light or a red light means stop sooner.'
        ),
        'next_step': (
            'Note which light it is and whether it flashes. Get an OBD '
            'fault-code scan at a workshop — promptly if it is flashing or '
            'the car drives poorly.'
        ),
        'recommended_service': 'Computer diagnostics (OBD fault-code scan)',
    },
    {
        'id': 'engine_noise',
        'label': 'Engine noise and performance',
        'patterns': _compile({
            # 'check engine light' / 'engine light' ko warning_light category
            # handle karti hai (upar hai), aur 'engine temperature' bhi noise
            # nahi hai. Lookaround yahan ye teeno phrases exclude karta hai —
            # warna engine noise bhi unpe match kar jata.
            'engine': r'(?<!check )\bengine\b(?!\s*(light|temp))',
            'knocking': r'knock',
            'ticking': r'tick',
            'rattling': r'rattle',
            'rough idle': r'rough idle|\bidle\b',
            'vibration': r'vibrat|shak',
            'misfire': r'misfire',
            'oil': r'\boil\b',
            'loss of power': r'losing power|loss of power|sluggish',
            'stalling': r'stall',
        }),
        'explain': (
            "Engine noises and vibration can range from harmless to serious — "
            "the pattern (when it happens, where it comes from) tells the "
            "story. It could be as simple as old oil or a loose heat shield, "
            "or as serious as a misfire."
        ),
        'questions': [
            (
                'Where and when do you hear it — at idle, while accelerating, '
                'or only on cold starts? Does it change with speed?'
            ),
            (
                'Is the check engine light on, and has the car had its oil '
                'changes on time?'
            ),
        ],
        'can_drive': True,
        'likely_issue': 'Engine noise or performance issue',
        'reasoning': (
            'Engine noise, vibration or power loss often relate to old oil, '
            'ignition misfires, worn mounts, or loose components.'
        ),
        'next_step': (
            'Avoid heavy acceleration and get an engine diagnostic scan — '
            'especially if the check engine light is on.'
        ),
        'recommended_service': 'Engine diagnostics and oil service',
    },
    {
        'id': 'ac',
        'label': 'Air conditioning',
        'patterns': _compile({
            'AC': r'\bac\b|\ba/c\b',
            'air conditioning': r'air ?con',
            'not cooling': r'not cool|no cool|weak cool|isn.?t cool|poor cool',
            'blower/fan': r'blower|\bvent',
            'musty smell': r'musty|moldy|mouldy',
            'cabin filter': r'cabin filter',
        }),
        'explain': (
            "Weak or smelly AC is usually one of three things: low "
            "refrigerant, a clogged cabin filter, or the compressor. All of "
            "them are fixable."
        ),
        'questions': [
            (
                'Is it not cooling at all, or just weak — and does it smell '
                'musty or chemical when you switch it on?'
            ),
            (
                'Does the fan blow air properly at every speed setting, and '
                'when was the cabin filter last changed?'
            ),
        ],
        'can_drive': True,
        'likely_issue': 'AC system not cooling properly',
        'reasoning': (
            'AC cooling problems typically come from low refrigerant, a '
            'clogged cabin filter, or a compressor fault.'
        ),
        'next_step': (
            'Comfort issue, not safety — but get the refrigerant and cabin '
            'filter checked when convenient.'
        ),
        'recommended_service': 'AC system service (refrigerant, cabin filter, compressor check)',
    },
]

SAFETY_RULES = [
    (
        re.compile(r'\bfire\b|flames?', re.IGNORECASE),
        "Stop driving now. Fire or flames mean get everyone away from the "
        "car, switch off the engine and call for help. Do not continue driving.",
    ),
    (
        re.compile(r'\bsmok', re.IGNORECASE),
        "Smoke is a red flag — it can mean an oil or coolant leak hitting hot "
        "parts, or an electrical problem. Pull over safely, switch off, and "
        "get it inspected before driving again.",
    ),
    (
        re.compile(r'steam', re.IGNORECASE),
        "Steam from the bonnet means it's overheating badly. Pull over safely "
        "and let it cool down — never open the radiator cap while it's hot.",
    ),
    (
        re.compile(r'burn(ing|t)? smell|smell.{0,20}burn', re.IGNORECASE),
        "A burning smell can be electrical or a dragging brake/clutch issue. "
        "Park somewhere safe, switch off, and get it checked before your "
        "next drive.",
    ),
    (
        re.compile(
            r'no brakes|brakes? (have )?(failed|failure|gone)|'
            r'brake.{0,30}floor|floor.{0,10}brake',
            re.IGNORECASE,
        ),
        "If the brakes have failed or the pedal sinks to the floor, do not "
        "drive the car. Have it towed or inspected on-site — this is a "
        "critical safety issue.",
    ),
    (
        re.compile(
            r'(petrol|diesel|fuel|gas).{0,15}(smell|leak)|'
            r'(smell|leak).{0,15}(petrol|diesel|fuel|gas)',
            re.IGNORECASE,
        ),
        "A fuel smell or leak is a fire risk. Don't start or drive the car — "
        "get it inspected immediately.",
    ),
    (
        re.compile(
            r'steering.{0,15}(lock|stuck|fail|very hard|can.?t turn|cannot turn)',
            re.IGNORECASE,
        ),
        "If the steering locks up or becomes very hard to turn, stop driving "
        "— steering failure is dangerous at any speed. Get it towed.",
    ),
]

GREETING_RE = re.compile(
    r'^\s*(hi|hello|hey|yo|namaste|hola|good (morning|afternoon|evening))\b',
    re.IGNORECASE,
)
THANKS_RE = re.compile(r'\b(thanks|thank you|thank u|thankyou|thx)\b', re.IGNORECASE)
HELP_RE = re.compile(r'what can you do|how (can|do) you help|what do you do', re.IGNORECASE)
VAGUE_RE = re.compile(
    r'\bnoise\b|\bsound\b|\bsmell\b|strange|weird|something wrong|problem',
    re.IGNORECASE,
)
CAR_TERMS_RE = re.compile(
    r'\bcar\b|\bvehicle\b|\bsuv\b|\bsedan\b|\bhatchback\b|\bmileage\b|\bmilage\b|'
    r'\bdashboard\b|warning light|\bmechanic\b|\bgarage\b|\bdriv',
    re.IGNORECASE,
)

GREETING_REPLY = (
    "Hello! I'm your AI car mechanic. Tell me what's going on with your car "
    "— any noises, warning lights, smells, or changes in how it drives?"
)
THANKS_REPLY = (
    "You're welcome! Drive safe — and if anything else comes up with the "
    "car, just tell me."
)
HELP_REPLY = (
    "I'm your AI car mechanic. Describe the problem in your own words — "
    "noises, warning lights, smells, performance changes — or upload a "
    "photo, audio clip or video of the issue, and I'll help you narrow it "
    "down. Once we've talked it through, you can get a full diagnosis and "
    "book a mechanic."
)
VAGUE_REPLY = (
    "Got it — let's narrow it down. What does it sound/smell/feel like, "
    "where is it coming from (engine, brakes, steering...), and when does "
    "it happen?"
)
CAR_UNCLEAR_REPLY = (
    "Thanks. Can you describe what the car is actually doing — any noise, "
    "warning light, smell, vibration, or change in performance? The more "
    "specific you are, the better I can help."
)
OFF_TOPIC_REPLY = (
    "I'm your car mechanic assistant, so I can only help with car-related "
    "problems. Tell me what your car is doing — any noises, warning lights, "
    "smells, or performance issues — and I'll take it from there."
)
READY_FOR_DIAGNOSIS = (
    "I have a good picture of the problem now. Whenever you're ready, hit "
    "'Get Diagnosis' and I'll prepare a full assessment — likely issue, "
    "confidence level, and whether it's safe to drive."
)


def find_symptoms(text):
    """Text mein kaunsi categories match hoti hain, woh dhoondho.

    Returns: [(category_dict, [matched_labels]), ...] — KB ke order mein
    (yaani priority order mein). Kuch nahi mila to empty list.
    """
    results = []
    for category in SYMPTOM_CATEGORIES:
        matched = [
            label
            for label, regex in category['patterns']
            if regex.search(text)
        ]
        if matched:
            results.append((category, matched))
    return results


def find_safety_hit(text):
    """Pehla safety rule jo match kare uska message return karta hai, warna None."""
    for pattern, message in SAFETY_RULES:
        if pattern.search(text):
            return message
    return None


def get_category(category_id):
    """Category id (jaise 'brakes') se poora category dict dhoondho."""
    for category in SYMPTOM_CATEGORIES:
        if category['id'] == category_id:
            return category
    return None


def is_greeting(text):
    return bool(GREETING_RE.search(text))


def is_thanks(text):
    return bool(THANKS_RE.search(text))


def is_help_question(text):
    return bool(HELP_RE.search(text))


def is_vague(text):
    return bool(VAGUE_RE.search(text))


def mentions_car(text):
    return bool(CAR_TERMS_RE.search(text))
