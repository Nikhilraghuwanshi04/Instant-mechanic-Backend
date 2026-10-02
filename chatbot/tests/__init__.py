"""Chatbot app ka poora test suite.

Django yahan sab khud dhoond leta hai — `manage.py test` chalao aur saare
test files apne aap run ho jate hain:

Unit tests (services ki andar ki logic):
- test_rule_engine.py      → chat ka dimaag (reply logic, safety priority)
- test_diagnosis_engine.py → structured diagnosis (confidence, can_drive)
- test_media_validator.py  → upload security (magic bytes, size limits)

API integration tests (poore HTTP stack — URL → view → DB):
- test_api_chat.py         → POST /api/chat/ + Gemini chat fallback (mocked)
- test_api_upload.py       → POST /api/upload/ + file validation errors
- test_api_diagnosis.py    → POST /api/diagnosis/ + Gemini fallback (mocked)
- test_api_booking.py      → POST /api/booking/ + GET /api/booking/<id>/
- test_api_history.py      → health, conversation list, conversation detail

Note: helpers.py jaan-boojh kar `test_` se shuru nahi hota — wo tests nahi,
shared tools rakhti hai (base class + fixtures), isliye runner ise count
nahi karta.
"""
