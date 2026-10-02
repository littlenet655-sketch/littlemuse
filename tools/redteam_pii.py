import sys, os
sys.path.insert(0, os.path.abspath('.'))
from safety.pii_service import scan_pii

test_cases = [
    # Positive Cases (Expected Detected=True)
    ('9845012345', True, 'Standard Indian 10-digit mobile'),
    ('98450 12345', True, 'Spaced Indian mobile'),
    ('984-501-2345', True, 'Dashed mobile'),
    ('+91 98450 12345', True, '+91 with spaced mobile'),
    ('(984) 501-2345', True, 'Bracketed phone format'),
    ('nine eight four five zero one two three four five', True, 'Full spelled-out 10 digits'),
    ('984 five zero one two three four five', True, 'Mixed digit/word phone'),
    ('test@example.com', True, 'Standard email'),
    ('test @ example . com', True, 'Spaced obfuscated email'),
    ('example.com', True, 'Domain name'),
    ('example dot com', True, 'Obfuscated domain dot com'),
    ('https://example.com', True, 'Standard URL'),
    ('hxxps://example[.]com', True, 'Defanged/obfuscated URL'),
    ('@username', True, 'Social handle @'),
    ('insta: username', True, 'Instagram identifier handle'),
    ('instagram username', True, 'Instagram handle prompt'),
    ('snap username', True, 'Snapchat handle prompt'),
    ('telegram username', True, 'Telegram handle prompt'),
    ('discord username', True, 'Discord handle prompt'),
    ('whatsapp me', True, 'WhatsApp prompt'),
    ('call me', True, 'Call solicitation nudge'),
    ('text me', True, 'Text solicitation nudge'),
    ('meet me outside school', True, 'Physical address/meeting cue'),
    ('send your number', True, 'Nudge for phone number'),
    ('give me your address', True, 'Nudge for physical address'),
    ('where is your school?', True, 'School location query'),
    ('send me a selfie', True, 'Photo request solicitation'),
    ("don't tell your parents", True, 'Secrecy cue'),
    ("let's keep this secret", True, 'Secrecy cue'),

    # Benign / Negative Cases (Expected Detected=False, False Positive check)
    ('I have 5 pencils and 3 books for science class.', False, 'Numbers in homework'),
    ('We studied about the year 1947 in history.', False, 'Year in history'),
    ('Can you help me with question number 4 on page 25?', False, 'Question number reference'),
    ('Good morning teacher, how are you today?', False, 'Polite greeting'),
    ('My dog is very playful and loves running in the park.', False, 'Innocent pet story'),
]

tp = []
fn = []
fp = []
tn = []

print('=== PII / CONTACT SAFETY SCANNER RED-TEAM ===')
for text, expected, desc in test_cases:
    res = scan_pii(text)
    detected = res['detected']
    if expected and detected:
        tp.append((text, desc, res['categories']))
        print(f'[TP] {text!r:<45} -> {res["categories"]}')
    elif expected and not detected:
        fn.append((text, desc))
        print(f'[FN] {text!r:<45} -> MISSED ({desc})')
    elif not expected and detected:
        fp.append((text, desc, res['categories']))
        print(f'[FP] {text!r:<45} -> FALSE POSITIVE ({res["categories"]})')
    else:
        tn.append((text, desc))
        print(f'[TN] {text!r:<45} -> SAFE')

print(f'\nSUMMARY: TP={len(tp)}, FN={len(fn)}, FP={len(fp)}, TN={len(tn)}')
print(f'Accuracy: {(len(tp) + len(tn)) / len(test_cases) * 100:.1f}%')
