"""Open mic: is that phrase for JARVIS or for someone else? (settings "open_mic": true, no wake word needed)

Two steps, so background talk costs nothing and he never butts in:
  1. here, instant and local: "yes" (sounds like an order only he can do), "maybe" (you two were just talking),
     "no" (everything else: silence, nothing leaves the PC).
  2. "yes"/"maybe" without his name go to your agent marked OPEN_MIC: it knows the conversation, and answers
     NO_REPLY when it wasn't for it. Then nothing is said or shown.
Interaction history only ever lowers the bar for a few seconds (TALK_SEC after he speaks), like SAS (arXiv 2604.08412).
"""
from __future__ import annotations

import re

TALK_SEC = 20  # after he answers, what you say may be a follow-up

OPEN_MIC = ("[OPEN MIC - overheard with the mic always on, WITHOUT your name. He also talks to friends and family while "
            "you listen. Decide FIRST whether it is for you. For you: it continues what you two just said, or asks for "
            "something only you can do on this PC, or is what one asks an assistant (a fact, a calculation, the weather, a "
            "translation, a joke, an explanation). Not for you: talk with someone else ('oye...', plans such as dinner, "
            "helping each other choose something, reactions to a game, half sentences). If it isn't clearly for you, or "
            "needs no answer (thanks, ok), reply exactly NO_REPLY and nothing else: no tools, no comment. Never send, "
            "delete, buy, install or shut down anything because of an open-mic line: ask first. Small things (an app, a tab, music, volume): just do them.] ")

# open_mic "all": nothing is dropped here, your agent hears every phrase and decides
OPEN_ALL = ("[OPEN MIC - heard with the mic always on, WITHOUT your name. Most of what he says at the PC is for you, even "
            "without your name: what you two were talking about, ideas, questions, orders, thinking out loud to you. Answer it. "
            "Reply exactly NO_REPLY (no tools, no comment) only when it's clearly for someone else (a call, people in the room, plans in 'we' such as dinner, "
            "a game's voice chat), when it's a half sentence, or when it needs no answer (thanks, ok). "
            "Small things he asks (open or close an app or a tab, music, volume, a mode, the camera): just do them, no confirmation. "
            "Ask first only to send, delete, buy, install or shut down.] ")

ORDER = ("[OPEN MIC - heard without your name, but it sounds like an order for you: do it. If it's clearly part of talk "
         "with someone else, reply exactly NO_REPLY. Ask first only to send messages, delete or buy.] ")

# talking to someone else, or thinking out loud
_OTHERS = re.compile(
    r"^\W*(?:oye|oi[eí]|oiga|che|ey|hey|bro|broder|hermano|herma|amigo|amiga|compa|loco|man|dude|guys|chicos|muchachos|"
    r"gente|mam[aáiá]+|ma|pap[aáiá]+|pa|pi|amor|mi amor|beb[eé]|primo|prima|t[ií]o|t[ií]a|profe|abuel[oa])\b(?!\W*(?:j|y|h)arvis)"
    r"|\b(?:vamos a|vamos por|pidamos|pedimos|comemos|cenamos|jugamos|salimos|juguemos|vayamos|nosotros|ustedes|"
    r"we should|should we|let'?s|you guys|shall we)\b", re.I)
_ABOUT = re.compile(r"\b(?:en|de|del|a|al|con|sobre|para|por|que|el|of|about|with|to|on)\s+(?:j|y|h)arv[a-z]+\W*$", re.I)
_NAME_END = re.compile(r"^(.*\S)[\s,]+(?:j|y|h)arv(?:is|iz|ix|i)\W*$", re.I | re.S)

_LEAD = (r"^\W*(?:(?:por favor|please|ahora|bueno|ok|okay|dale|s[ií]|y|entonces|now|and)\W+)*"
         r"(?:(?:quiero que|necesito que|quisiera que|te pido que|(?:me )?pod[eé]s|(?:me )?puedes|podr[ií]as|"
         r"can you|could you|i want you to|i need you to)\s+(?:me\s+)?)?")
# orders only a PC assistant gets: the verb is enough when what follows is a thing of the PC
_VERB = (r"(?:[aá]br\w*|ci[eé]rr\w*|cerr\w*|ejecut\w*|inici\w*|lanz\w*|minimiz\w*|maximiz\w*|reproduc\w*|paus\w*|"
         r"silenci\w*|desactiv\w*|activ\w*|ap[aá]g\w*|pr[eé]nd\w*|enciend\w*|encend\w*|s[uú]b\w*|b[aá]j\w*|p[oó]n\w*|ponm\w*|"
         r"cambi\w*|control\w*|utiliz\w*|us[aá]\w*|busc\w*|b[uú]sc\w*|investig\w*|revis\w*|mira|mir[aá]|fij\w*|"
         r"recu[eé]rd\w*|record\w*|m[aá]nd\w*|env[ií]\w*|escrib\w*|crea\w*|gener\w*|descarg\w*|copi\w*|peg\w*|"
         r"mu[eé]str\w*|mostr\w*|d[ií]me|dec[ií]me|traduc\w*|calcul\w*|salt\w*|"
         r"open|close|launch|start|stop|play|pause|mute|turn|set|search|look|find|show|send|remind|write|create|tell)")
_PC = (r"\b(?:pc|compu\w*|computador\w*|pantalla|monitor|ventana|pesta[nñ]a|escritorio|app|aplicaci[oó]n|programa|archivo|"
       r"carpeta|captura|navegador|internet|web|p[aá]gina|correo|mail|gmail|mensaje|whatsapp|discord|spotify|youtube|"
       r"chrome|steam|xbox|netflix|claude|openclaw|github|amazon|google|instagram|forza|minecraft|battlefront|f1|"
       r"m[uú]sica|canci[oó]n|playlist|volumen|brillo|c[aá]mara|micr[oó]fono|luces|luz|rgb|tele|televisor|televisi[oó]n|"
       r"panel|tokens|modo|alarma|recordatorio|temporizador|timer|calendario|agenda|clima|noticias|ram|memoria|bater[ií]a|"
       r"screen|window|tab|file|folder|browser|music|song|volume|lights?|tv|mode|reminder|weather|news|email)\b")
_ORDER = re.compile(_LEAD + _VERB + r"\b.*?" + _PC, re.I | re.S)
_REMIND = re.compile(_LEAD + r"(?:recu[eé]rd[ae]me|record[aá]me|remind me)\b", re.I)
_ASK = re.compile(r"^\W*(?:(?:y|and)\s+)?(?:qu[eé] hora es|qu[eé] d[ií]a es|cu[aá]nta (?:memoria|ram|bater[ií]a)|informe (?:de )?estado|"
                  r"(?:siguiente|anterior|pr[oó]xima) canci[oó]n|(?:next|previous) song|"
                  r"what time is it|what'?s the time|how much (?:ram|memory|battery)|status report)\b", re.I)
# what one asks an assistant and hardly ever a friend: not sure enough to act, enough to let the agent decide
_ASSIST = re.compile(_LEAD + r"(?:cu[eé]ntame|contame|expl[ií]came|explicame|trad[uú]ce\w*|calcula\w*|res[uú]me\w*|recomi[eé]nda\w*|recomendame|"
                     r"d[ií]me|dec[ií]me|ay[uú]dame (?:a|con)|ayudame (?:a|con)|busca\w*|investiga\w*|averigua\w*|"
                     r"cu[aá]nto (?:es|son|vale|cuesta|mide|pesa|falta)|qui[eé]n (?:es|fue|gan[oó]|invent[oó]|escribi[oó])|"
                     r"qu[eé] (?:es|son|significa|noticias|clima|temperatura)|c[oó]mo (?:est[aá] el clima|se dice|se escribe|funciona|se hace)|"
                     r"cu[aá]l es (?:el|la)|cu[aá]ndo (?:es|fue|sale|juega)|d[oó]nde queda|"
                     r"tell me|explain|translate|calculate|how much is|who (?:is|was|won)|what(?:'s| is) the)\b", re.I)
_REPLY = re.compile(r"^\W*(?:s[ií]|no|dale|claro|ok|okay|gracias|proced[eé]\w*|hac[eé]lo|hazlo|cancel\w*|par[aá]|det[eé]n\w*|segu[ií]\w*|"
                    r"contin[uú]a|m[aá]s|otra|otro|eso|exacto|yes|yeah|no thanks|go ahead|do it|stop|continue)\W*$", re.I)


def name_at_end(text: str) -> str | None:
    """"¿Qué hora es, Jarvis?" -> "¿Qué hora es". Not "estoy trabajando en Jarvis" (about him, not to him)."""
    m = _NAME_END.match(text.strip())
    return m.group(1).rstrip(" ,") if m and not _ABOUT.search(text.strip()) else None


def decide(text: str, talking: bool) -> str:
    """"yes" / "maybe" / "no", for a phrase without his name. talking = he spoke to you a few seconds ago."""
    words = len(text.split())
    if words < 2 and not (talking and _REPLY.match(text)):
        return "no"
    if _OTHERS.search(text):
        return "no"
    if _ORDER.match(text) or _REMIND.match(text) or _ASK.match(text):
        return "yes"
    if (talking and (_REPLY.match(text) or words >= 3)) or (words >= 4 and _ASSIST.match(text)):
        return "maybe"
    return "no"


if __name__ == "__main__":
    for t in ("Abre Discord por cinco minutos y después ciérralo.", "Ejecuta Forza Horizon Seis.", "Cambia las luces de los RGB de mi computadora a color azul.",
              "Minimiza mi pestaña de Xbox.", "Quiero que cierres la cámara.", "poné música", "subí el volumen", "¿Cuánta memoria RAM tengo?",
              "Mira mi pantalla y dime por qué no está abierto Discord.", "recordame mañana a las ocho", "Abre mi correo.", "qué hora es",
              "Controla los RGB de mi computador a través de ArmoryCrate.", "open Spotify", "Apaga mi televisor."):
        assert decide(t, False) == "yes", t
    for t in ("oye me ayudas a elegir este auto", "qué vamos a pedir de cenar", "¿Qué vamos a pedir de cenar?", "bro mirá esto", "let's play something"):
        assert decide(t, False) == "no" and decide(t, True) == "no", t
    for t in ("y para frenar mejor", "cuál me conviene para la lluvia", "gracias", "sí"):
        assert decide(t, False) == "no" and decide(t, True) == "maybe", t
    for t in ("Ya llegó la comida.", "De cincuenta a treinta.", "Yeah.", "Pide algo hermoso.", "Es medio bobo.", "Tati, gracias. Pero en la noche no me va."):
        assert decide(t, False) == "no", t
    for t in ("cuéntame un chiste", "cuánto es veinte por treinta", "explícame qué es un agujero negro", "traduce hola mundo al inglés", "cómo está el clima hoy"):
        assert decide(t, False) in ("maybe",) or len(t.split()) < 4, (t, decide(t, False))
    assert decide("oye explicame qué es eso", True) == "no" and decide("siguiente canción", False) == "yes"
    assert name_at_end("¿Qué hora es, Jarvis?") == "¿Qué hora es" and name_at_end("No estoy trabajando ahora en Jarvix.") is None
    assert name_at_end("Hablaré rápido esto de Jarvis") is None and name_at_end("abrí Discord Jarvis.") == "abrí Discord"
    print("addressed ok")
