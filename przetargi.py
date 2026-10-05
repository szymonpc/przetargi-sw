#!/usr/bin/env python3
"""
Codzienny przegląd przetargów dla SW Sp. z o.o.

Źródła:
  1. BZP (e-Zamówienia) – wszystkie przetargi z ustawy Pzp w Polsce (publiczne API, bez klucza).
  2. TED (Dziennik UE) – duże przetargi unijne z Polski (publiczne API, bez klucza).
  3. Strony gmin, miast, powiatów, platform zakupowych – lista w pliku zrodla_strony.csv.
     Tu trafiają też zapytania ofertowe poniżej 130 tys. zł, których nie ma w BZP.

Wyniki: folder wyniki/ (najnowsze.md, aktywne.json, archiwum dzienne) + e-mail.
Ustawienia: sekcja KONFIGURACJA poniżej oraz plik zrodla_strony.csv.
"""

import csv
import hashlib
import html
import json
import os
import re
import smtplib
import sys
import time
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

# ============================ KONFIGURACJA ============================

WOJEWODZTWA = {          # kody TERYT (BZP)
    "PL28": "warmińsko-mazurskie",
    "PL04": "kujawsko-pomorskie",
    "PL14": "mazowieckie",
    "PL22": "pomorskie",
}
NUTS = {                 # kody NUTS (TED)
    "PL62": "warmińsko-mazurskie",
    "PL61": "kujawsko-pomorskie",
    "PL91": "mazowieckie",
    "PL92": "mazowieckie",
    "PL63": "pomorskie",
}

CPV_METAL = {
    "45340": "ogrodzenia, barierki, sprzęt ochronny",
    "45342": "wznoszenie ogrodzeń",
    "45233280": "bariery drogowe",
    "45262400": "wznoszenie konstrukcji stalowych",
    "452232": "roboty konstrukcyjne",
    "452231": "instalowanie konstrukcji metalowych",
    "45421": "stolarka i ślusarka budowlana",
    "4421": "konstrukcje i części konstrukcji",
    "44212": "wyroby konstrukcyjne (stal)",
    "44316": "wyroby ślusarskie",
    "44112": "konstrukcje budowlane różne (wiaty, zadaszenia)",
    "349281": "bariery drogowe (wyroby)",
    "349282": "ogrodzenia (wyroby)",
    "349284": "meble miejskie",
    "34928": "wyposażenie dróg",
    "39113": "siedziska / ławki",
    "37535": "urządzenia placów zabaw",
    "37440": "siłownie zewnętrzne / sprzęt fitness",
    "45112711": "kształtowanie parków (mała architektura)",
    "44611": "zbiorniki",
    "92522": "konserwacja zabytków / obiektów",
}

# Słowa MOCNE – szukane w tytule i w treści ogłoszenia (wprost wskazują Waszą branżę)
SLOWA_MOCNE_METAL = [
    # ogrodzenia, bramy, balustrady
    "ogrodzen", "płot", "parkan", "piłkochwyt", "pilkochwyt", "bram wjazd", "bramy wjazd",
    "brama wjazd", "brama przesuwn", "bramy przesuwn", "furtk", "balustrad", "barierk",
    "barier ochronn", "bariery ochronn", "barier energochłonn", "bariery energochłonn",
    "poręcz", "porecz", "pochwyt",
    # dostępność, schody, pomosty
    "pochyln", "platform przyschod", "platformy przyschod", "schody zewn", "schodów zewn",
    "schody ewakuac", "schodów ewakuac", "schody stalow", "schodów stalow", "schody metalow",
    "pomost", "podest stalow", "podestów stalow", "kładk", "kladk", "estakad", "antresol",
    # wiaty, zadaszenia
    "wiat", "zadaszen", "altan", "pergol", "carport", "stojak rower", "stojaków rower",
    "stojaki rower", "osłon śmietnik", "osłony śmietnik", "altan śmietnik", "altany śmietnik",
    # konstrukcje i materiały
    "konstrukcj stalow", "konstrukcji stalow", "konstrukcja stalowa", "konstrukcje stalowe",
    "konstrukcji metalow", "konstrukcja metalowa", "hala stalow", "hali stalow", "hala namiot",
    "hali namiot", "stal nierdzewn", "stali nierdzewn", "nierdzewn", "kwasoodporn", "inox",
    "ślusar", "slusar", "spawa", "ocynkowan", "malowanie proszkow", "malowane proszkow",
    "zbiornik stalow", "komin stalow", "rurociąg technolog", "krat okienn", "kraty okienn",
    "krat stalow", "kraty stalow",
    # mała architektura, rekreacja
    "mała architektur", "mala architektur", "małej architektur", "malej architektur",
    "siłowni zewn", "silowni zewn", "siłownia zewn", "street workout", "gablot", "witacz",
    "rzeźb", "rzezb", "molo", "pomost pływ", "pomostu pływ",
]

# Słowa SŁABE – tylko w tytule (w treści dawałyby za dużo fałszywych trafień)
SLOWA_SLABE_METAL = [
    "brama", "bramy", "bram", "szlaban", "przęsł", "przesl", "barier", "osłon", "oslon",
    "podjazd", "rampa", "rampy", "schod", "drabin", "trap", "galeri", "przystank", "rowerow",
    "boks", "śmietnik", "smietnik", "maszt", "stelaż", "stelaz", "regał", "regal", "kontener",
    "aluminiow", "stalow", "metalow", "blach", "kowal", "rurociąg", "rurociag", "zbiornik",
    "ławk", "lawk", "koszy", "kosze", "tablic", "plac zabaw", "placu zabaw", "placów zabaw",
    "siłowni", "silowni", "boisk", "trybun", "skatepark", "renowacj", "konserwacj", "pomnik",
    "okiennic", "drzwi stalow", "drzwi metalow", "most", "przepust", "slip", "przystań",
    "przystan", "dostępnoś", "dostepnos", "niepełnospraw", "niepelnospraw",
    "siatk", "daszek", "daszk", "zadaszenie", "hala", "hali", "magazyn",
]

# ---------------- NAWIERZCHNIE: kostka brukowa, chodniki, place, parkingi ----------------
SZUKAJ_NAWIERZCHNI = True   # False = wyłącza tę branżę

CPV_NAWIERZCHNIE = {
    "45233222": "układanie chodników",
    "45233161": "ścieżki piesze",
    "45233162": "ścieżki rowerowe",
    "45233260": "drogi dla pieszych",
    "45233253": "nawierzchnie dróg dla pieszych",
    "45233200": "różne nawierzchnie",
    "45233250": "nawierzchnie (poza drogami)",
    "45233252": "nawierzchnie ulic",
    "45223300": "parkingi",
    "45111291": "zagospodarowanie terenu",
}

SLOWA_MOCNE_NAWIERZCHNIE = [
    "kostk brukow", "kostki brukow", "kostką brukow", "kostka brukowa", "kostki betonow",
    "kostką betonow", "kostka betonowa", "kostki granitow", "kostka granitowa", "kostki kamienn",
    "płyt ażurow", "plyt azurow", "płyty ażurow", "płyt chodnikow", "płyty chodnikow",
    "nawierzchni z kostki", "nawierzchnia z kostki", "polbruk", "geokrat", "ekokrat", "eko-krat",
    "brukarsk",
]

SLOWA_SLABE_NAWIERZCHNIE = [
    "chodnik", "ciąg pieszy", "ciągu pieszego", "ciągów pieszych", "ciąg pieszo", "ciągu pieszo",
    "ścieżk", "sciezk", "parking", "miejsc postojow", "miejsca postojow", "miejsc parkingow",
    "plac manewr", "placu manewr", "plac postoj", "placu postoj", "plac przed", "placu przed",
    "plac targ", "placu targ", "plac skład", "placu skład", "plac apelow", "placu apelow",
    "dojazd", "dojść", "dojscia", "dojście", "dojścia", "zjazd", "nawierzchni", "utwardzen",
    "opasek", "opaski", "opaska", "dziedzin", "podwór", "podwor", "alejk", "alei", "skwer",
    "deptak", "zatok", "peron", "krawężnik", "kraweznik", "obrzeż", "obrzez", "bruk",
    "droga wewnętrzn", "drogi wewnętrzn", "dróg wewnętrzn", "odwodnieni liniow", "korytk",
    "zagospodarowan", "rynku", "rynek",
]

if not SZUKAJ_NAWIERZCHNI:
    CPV_NAWIERZCHNIE, SLOWA_MOCNE_NAWIERZCHNIE, SLOWA_SLABE_NAWIERZCHNIE = {}, [], []

CPV_PREFIKSY = {**CPV_METAL, **CPV_NAWIERZCHNIE}
SLOWA_MOCNE = SLOWA_MOCNE_METAL + SLOWA_MOCNE_NAWIERZCHNIE
SLOWA_SLABE = SLOWA_SLABE_METAL + SLOWA_SLABE_NAWIERZCHNIE
SLOWA_KLUCZOWE = SLOWA_MOCNE + SLOWA_SLABE

# Słowa w tytule, które wykluczają ogłoszenie (fałszywe trafienia)
WYKLUCZENIA = [
    "dostawa paliw", "olej opałow", "olej napędow", "ubezpieczen", "odśnieżan", "zimowe utrzymanie",
    "artykułów spożywcz", "żywnoś", "zywnos", "mięs", "pieczyw", "leków", "lekow", "odczynnik",
    "sprzętu komputer", "oprogramowan", "licencj", "usług pocztow", "energii elektryczn",
    "gazu ziemn", "sprzątan", "sprzatan", "ochrony osób", "transport uczniów", "dowóz",
    "szkoleni", "catering", "wywóz odpadów", "odbiór odpadów", "materiałów biurow",
    "tonerów", "kart paliw", "leasing", "samochod", "ambulans", "konserwacja dźwig",
    "konserwacja wind", "konserwacja system", "konserwacja instalacji",
    "remont cząstkow", "remonty cząstkow", "remontów cząstkow", "oznakowania poziom",
    "oznakowanie poziom", "sprzątanie ulic", "oczyszczani", "pielęgnacj", "koszeni",
    "lokali mieszkal", "lokalu mieszkal", "nadzór inwestorsk", "nadzoru inwestorsk",
    "pełnienie funkcji inspektor", "dokumentacji projekt", "dokumentacja projekt",
    "dokumentacj projekt", "opracowanie dokumentacji", "wykonanie dokumentacji",
]

# Słowa pomocnicze - na stronach gmin link musi zawierać słowo branżowe ORAZ
# (opcjonalnie) jedno z tych, żeby nie łapać np. aktualności o placu zabaw.
SLOWA_PRZETARGOWE = [
    "przetarg", "zapytani", "zamówieni", "zamowieni", "ofert", "postępowan", "postepowan",
    "zaproszeni", "rozeznani", "wykonanie", "dostawa", "budowa", "przebudowa", "remont",
    "modernizacj", "montaż", "montaz", "wymiana", "zakup",
]
STRONY_WYMAGAJ_SLOWA_PRZETARGOWEGO = True

DNI_WSTECZ = 2
ROZMIAR_STRONY = 100
MAKS_STRON = 80
DNI_TRZYMANIA_ZE_STRON = 30     # jak długo trzymać na liście znaleziska ze stron (brak terminu)

API_BZP = "https://ezamowienia.gov.pl/mo-board/api/v1/notice"
LINK_BZP = "https://ezamowienia.gov.pl/mo-client-board/bzp/notice-details/id/{}"
API_TED = "https://api.ted.europa.eu/v3/notices/search"
LINK_TED = "https://ted.europa.eu/pl/notice/-/detail/{}"

KATALOG = Path(__file__).parent
WYNIKI = KATALOG / "wyniki"
PLIK_ZRODLA = KATALOG / "zrodla_strony.csv"
PLIK_STANU = WYNIKI / "stan.json"
PLIK_AKTYWNE = WYNIKI / "aktywne.json"
PLIK_NAJNOWSZE = WYNIKI / "najnowsze.md"
UA = "Mozilla/5.0 (compatible; SW-przetargi-monitor/2.0)"

# ======================================================================

raport_zrodel = []   # (źródło, status, opis)


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def zawiera(tekst, rdzen):
    """Słowo zaczynające się od rdzenia ('wiat' nie łapie 'oświaty')."""
    return re.search(r"(?<!\w)" + re.escape(rdzen), tekst) is not None


def dopasuj_slowa(tekst, lista=None):
    t = tekst.lower()
    return sorted({s for s in (lista or SLOWA_KLUCZOWE) if zawiera(t, s)})


def wykluczone(tytul):
    t = tytul.lower()
    return any(zawiera(t, w) for w in WYKLUCZENIA)


def branza(kody, slowa):
    b = []
    if any(k.startswith(p) for p in CPV_METAL for k in kody) or \
            set(slowa) & set(SLOWA_MOCNE_METAL + SLOWA_SLABE_METAL):
        b.append("metal")
    if any(k.startswith(p) for p in CPV_NAWIERZCHNIE for k in kody) or \
            set(slowa) & set(SLOWA_MOCNE_NAWIERZCHNIE + SLOWA_SLABE_NAWIERZCHNIE):
        b.append("nawierzchnie")
    return " + ".join(b)


def dopasuj_cpv(kody):
    return sorted({opis for p, opis in CPV_PREFIKSY.items() for k in kody if k.startswith(p)})


def http(url, dane=None, json_body=None, timeout=60, proby=3):
    naglowki = {"User-Agent": UA, "Accept": "application/json, text/html;q=0.9, */*;q=0.8"}
    body = None
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        naglowki["Content-Type"] = "application/json"
    if dane:
        url = f"{url}?{urlencode(dane)}"
    ostatni = None
    for proba in range(1, proby + 1):
        try:
            with urlopen(Request(url, data=body, headers=naglowki), timeout=timeout) as r:
                surowe = r.read()
                kod = r.headers.get_content_charset()
                return surowe, kod
        except Exception as e:  # noqa: BLE001
            ostatni = e
            time.sleep(3 * proba)
    raise RuntimeError(f"{ostatni}")


def dekoduj(surowe, kod):
    kandydaci = [kod] if kod else []
    m = re.search(rb'charset=["\']?([\w-]+)', surowe[:3000], flags=re.I)
    if m:
        kandydaci.append(m.group(1).decode("ascii", "ignore"))
    kandydaci += ["utf-8", "cp1250", "iso-8859-2"]
    for k in kandydaci:
        try:
            return surowe.decode(k)
        except Exception:  # noqa: BLE001
            continue
    return surowe.decode("utf-8", "ignore")


def html_na_tekst(s):
    if not s:
        return ""
    s = re.sub(r"<(script|style).*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>|</p>|</h\d>|</li>|</tr>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"[ \t]+", " ", html.unescape(s)).strip()


def wyciagnij(tekst, wzorzec):
    m = re.search(wzorzec, tekst, flags=re.I)
    return m.group(1).strip() if m else ""


def plaski(v):
    """Spłaszcza wielojęzyczne pola TED do tekstu (preferuje polski)."""
    if v is None:
        return ""
    if isinstance(v, dict):
        for k in ("pol", "pl", "PL", "eng", "en"):
            if k in v:
                return plaski(v[k])
        return " ".join(plaski(x) for x in v.values())
    if isinstance(v, list):
        return " | ".join(plaski(x) for x in v if x is not None)
    return str(v)


# ------------------------------- BZP --------------------------------

def zrodlo_bzp(od, do):
    wyniki, pobrane = [], 0
    try:
        search_after, widziane = None, set()
        for strona in range(MAKS_STRON):
            p = {"NoticeType": "ContractNotice",
                 "PublicationDateFrom": od.strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "PublicationDateTo": do.strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "PageSize": ROZMIAR_STRONY}
            if search_after:
                p["SearchAfter"] = search_after
            surowe, kod = http(API_BZP, dane=p)
            dane = json.loads(surowe.decode(kod or "utf-8"))
            if isinstance(dane, dict):
                dane = dane.get("items") or dane.get("data") or dane.get("notices") or []
            nowe = [d for d in dane if d.get("objectId") not in widziane]
            if not nowe:
                break
            widziane.update(d.get("objectId") for d in nowe)
            pobrane += len(nowe)
            for o in nowe:
                w = ocen_bzp(o)
                if w:
                    wyniki.append(w)
            if len(dane) < ROZMIAR_STRONY:
                break
            search_after = dane[-1].get("objectId")
            time.sleep(0.4)
        raport_zrodel.append(("BZP", "OK", f"pobrano {pobrane}, pasuje {len(wyniki)}"))
    except Exception as e:  # noqa: BLE001
        raport_zrodel.append(("BZP", "BŁĄD", str(e)[:200]))
    log(f"BZP: pobrano {pobrane}, pasuje {len(wyniki)}")
    return wyniki


def ocen_bzp(o):
    woj = str(o.get("organizationProvince") or "").upper()
    if woj not in WOJEWODZTWA:
        return None
    tytul = str(o.get("orderObject") or "").strip()
    if wykluczone(tytul):
        return None
    tresc = html_na_tekst(o.get("htmlBody") or "")
    kody = re.findall(r"\d{8}", str(o.get("cpvCode") or ""))
    t_cpv = dopasuj_cpv(kody)
    t_tytul = dopasuj_slowa(tytul)
    t_tresc = sorted(set(dopasuj_slowa(tresc, SLOWA_MOCNE)) - set(t_tytul))
    if t_cpv or t_tytul:
        prio = "A"
    elif t_tresc:
        prio = "B"
    else:
        return None
    oid = o.get("objectId")
    return {
        "zrodlo": "BZP", "id": f"bzp:{oid}", "priorytet": prio, "tytul": tytul,
        "branza": branza(kody, t_tytul + t_tresc),
        "zamawiajacy": o.get("organizationName") or wyciagnij(tresc, r"Nazwa zamawiającego:\s*(.+)"),
        "miejscowosc": o.get("organizationCity") or wyciagnij(tresc, r"Miejscowość:\s*(.+)"),
        "wojewodztwo": WOJEWODZTWA[woj],
        "numer": o.get("bzpNumber") or o.get("noticeNumber") or "",
        "cpv": ", ".join(kody),
        "opublikowano": (o.get("publicationDate") or "")[:16].replace("T", " "),
        "termin_ofert": (o.get("submittingOffersDate") or "")[:16].replace("T", " "),
        "wartosc": wyciagnij(tresc, r"Wartość zamówienia[^:]*:\s*([\d\s,\.]+\s*PLN)"),
        "dopasowanie": ", ".join(t_cpv + t_tytul + t_tresc[:8]),
        "link": LINK_BZP.format(oid),
    }


# ------------------------------- TED --------------------------------

POLA_TED = ["publication-number", "notice-title", "buyer-name", "buyer-city",
            "place-of-performance", "classification-cpv",
            "deadline-receipt-tender-date-lot", "publication-date", "description-lot"]


def zrodlo_ted(od):
    wyniki, pobrane = [], 0
    try:
        zapytanie = (f"buyer-country=POL AND notice-type IN (cn-standard cn-social) "
                     f"AND publication-date>={od:%Y%m%d}")
        for strona in range(1, 30):
            body = {"query": zapytanie, "fields": POLA_TED, "limit": 250, "page": strona,
                    "scope": "ALL", "paginationMode": "PAGE_NUMBER"}
            surowe, _ = http(API_TED, json_body=body)
            dane = json.loads(surowe.decode("utf-8"))
            ogl = dane.get("notices") or []
            if not ogl:
                break
            pobrane += len(ogl)
            for o in ogl:
                w = ocen_ted(o)
                if w:
                    wyniki.append(w)
            if pobrane >= int(dane.get("totalNoticeCount") or 0):
                break
            time.sleep(0.5)
        raport_zrodel.append(("TED", "OK", f"pobrano {pobrane}, pasuje {len(wyniki)}"))
    except Exception as e:  # noqa: BLE001
        raport_zrodel.append(("TED", "BŁĄD", str(e)[:200]))
    log(f"TED: pobrano {pobrane}, pasuje {len(wyniki)}")
    return wyniki


def ocen_ted(o):
    miejsce = plaski(o.get("place-of-performance")).upper()
    woj = next((n for p, n in NUTS.items() if p in miejsce), None)
    if not woj:
        return None
    tytul = plaski(o.get("notice-title")).strip()
    if wykluczone(tytul):
        return None
    opis = plaski(o.get("description-lot"))
    kody = re.findall(r"\d{8}", plaski(o.get("classification-cpv")))
    t_cpv = dopasuj_cpv(kody)
    t_tytul = dopasuj_slowa(tytul)
    t_opis = sorted(set(dopasuj_slowa(opis, SLOWA_MOCNE)) - set(t_tytul))
    if t_cpv or t_tytul:
        prio = "A"
    elif t_opis:
        prio = "B"
    else:
        return None
    nr = plaski(o.get("publication-number"))
    termin = plaski(o.get("deadline-receipt-tender-date-lot")).split(" | ")[0]
    return {
        "zrodlo": "TED", "id": f"ted:{nr}", "priorytet": prio, "tytul": tytul[:300],
        "branza": branza(kody, t_tytul + t_opis),
        "zamawiajacy": plaski(o.get("buyer-name"))[:200],
        "miejscowosc": plaski(o.get("buyer-city"))[:80], "wojewodztwo": woj,
        "numer": nr, "cpv": ", ".join(kody[:6]),
        "opublikowano": plaski(o.get("publication-date"))[:10],
        "termin_ofert": termin[:16].replace("T", " "), "wartosc": "",
        "dopasowanie": ", ".join(t_cpv + t_tytul + t_opis[:8]),
        "link": LINK_TED.format(nr),
    }


# ------------------------------ STRONY ------------------------------

class ZbieraczLinkow(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.linki, self._href, self._tekst, self._title = [], None, [], ""

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            a = dict(attrs)
            self._href, self._tekst, self._title = a.get("href"), [], a.get("title") or ""

    def handle_data(self, data):
        if self._href is not None:
            self._tekst.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            tekst = re.sub(r"\s+", " ", " ".join(self._tekst)).strip()
            if len(self._title) > len(tekst):
                tekst = self._title.strip()
            self.linki.append((self._href, tekst))
            self._href = None


def wczytaj_zrodla():
    if not PLIK_ZRODLA.exists():
        return []
    zrodla = []
    with PLIK_ZRODLA.open(encoding="utf-8") as f:
        for wiersz in csv.DictReader(l for l in f if l.strip() and not l.startswith("#")):
            if (wiersz.get("url") or "").startswith("http"):
                zrodla.append(wiersz)
    return zrodla


def zrodlo_strony(widziane_strony):
    wyniki = []
    for z in wczytaj_zrodla():
        nazwa, url = z.get("nazwa", "").strip(), z["url"].strip()
        woj = (z.get("wojewodztwo") or "").strip()
        pierwszy_raz = url not in widziane_strony
        try:
            surowe, kod = http(url, timeout=40, proby=2)
            p = ZbieraczLinkow()
            p.feed(dekoduj(surowe, kod))
            trafienia = 0
            for href, tekst in p.linki:
                if len(tekst) < 15 or not href or href.startswith(("javascript", "mailto", "#")):
                    continue
                if wykluczone(tekst):
                    continue
                slowa = dopasuj_slowa(tekst)
                if not slowa:
                    continue
                t = tekst.lower()
                if STRONY_WYMAGAJ_SLOWA_PRZETARGOWEGO and not any(zawiera(t, s) for s in SLOWA_PRZETARGOWE):
                    continue
                link = urljoin(url, href)
                ident = "www:" + hashlib.sha1(f"{link}|{tekst}".encode()).hexdigest()[:16]
                trafienia += 1
                wyniki.append({
                    "zrodlo": "Strona", "id": ident, "priorytet": "S", "tytul": tekst[:300],
                    "branza": branza([], slowa),
                    "zamawiajacy": nazwa, "miejscowosc": "", "wojewodztwo": woj,
                    "numer": "", "cpv": "", "opublikowano": "", "termin_ofert": "",
                    "wartosc": "", "dopasowanie": ", ".join(slowa[:8]), "link": link,
                    "pierwszy_przeglad": pierwszy_raz,
                })
            widziane_strony[url] = datetime.now(timezone.utc).isoformat()
            raport_zrodel.append((nazwa, "OK", f"{len(p.linki)} linków, pasuje {trafienia}"))
        except Exception as e:  # noqa: BLE001
            raport_zrodel.append((nazwa, "BŁĄD", f"{url} – {str(e)[:120]}"))
        time.sleep(1)
    log(f"Strony: pasuje {len(wyniki)}")
    return wyniki


# ------------------------------ WYNIKI ------------------------------

def wczytaj(plik, domyslnie):
    try:
        return json.loads(plik.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return domyslnie


def nadal_aktywny(w, teraz):
    t = w.get("termin_ofert")
    if t:
        try:
            return datetime.strptime(t[:16], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc) > teraz
        except ValueError:
            pass
    znal = w.get("znaleziono")
    if znal:
        try:
            return datetime.fromisoformat(znal) > teraz - timedelta(days=DNI_TRZYMANIA_ZE_STRON)
        except ValueError:
            pass
    return True


KOLEJNOSC = {"A": 0, "S": 1, "B": 2}


def sortuj(lista):
    return sorted(lista, key=lambda x: (KOLEJNOSC.get(x["priorytet"], 9), x["termin_ofert"] or "9999"))


def markdown(nowe, aktywne, data):
    L = [f"# Przetargi SW Sp. z o.o. – {data}", "",
         f"Nowe: **{len(nowe)}** · Aktywne łącznie: **{len(aktywne)}**", ""]

    def sekcja(tytul, lista):
        L.extend([f"## {tytul}", ""])
        if not lista:
            L.extend(["_Brak._", ""])
            return
        for w in sortuj(lista):
            dop = " _(pierwszy przegląd strony – może być archiwalne)_" if w.get("pierwszy_przeglad") else ""
            L.append(f"### [{w['priorytet']}] {w['tytul']}{dop}")
            gdzie = ", ".join(x for x in (w["miejscowosc"], w["wojewodztwo"]) if x)
            L.append(f"- Branża: {w.get('branza', '')}")
            L.append(f"- Źródło: {w['zrodlo']} · Zamawiający: {w['zamawiajacy']}" + (f" ({gdzie})" if gdzie else ""))
            if w["termin_ofert"] or w["opublikowano"]:
                L.append(f"- Termin ofert: **{w['termin_ofert'] or 'sprawdź'}** · opublikowano: {w['opublikowano']}")
            if w["wartosc"]:
                L.append(f"- Wartość: {w['wartosc']}")
            if w["cpv"]:
                L.append(f"- CPV: {w['cpv']}")
            L.append(f"- Dopasowanie: {w['dopasowanie']}")
            L.append(f"- Link: {w['link']}")
            L.append("")

    sekcja("Nowe od ostatniego przeglądu", nowe)
    sekcja("Wszystkie aktywne", aktywne)
    L.extend(["## Stan źródeł", "", "| Źródło | Status | Szczegóły |", "|---|---|---|"])
    L.extend(f"| {a} | {b} | {c} |" for a, b, c in raport_zrodel)
    L.extend(["", "A = zakres w CPV/tytule · S = znalezione na stronie gminy/powiatu · "
              "B = zakres tylko w treści (sprawdź przedmiar)"])
    return "\n".join(L)


def html_maila(nowe, data):
    wiersze = "".join(
        f"<tr><td>{w['priorytet']}</td><td>{w.get('branza', '')}</td><td>{w['zrodlo']}</td>"
        f"<td><a href='{html.escape(w['link'])}'>{html.escape(w['tytul'])}</a></td>"
        f"<td>{html.escape(str(w['zamawiajacy']))}<br><small>{html.escape(str(w['miejscowosc']))} "
        f"{w['wojewodztwo']}</small></td><td><b>{w['termin_ofert'] or '–'}</b></td>"
        f"<td><small>{html.escape(w['dopasowanie'])}</small></td></tr>"
        for w in sortuj(nowe))
    bledy = [f"{a}: {c}" for a, b, c in raport_zrodel if b != "OK"]
    stopka = ("<p style='color:#a00'><small>Źródła z błędem: " + html.escape("; ".join(bledy))
              + "</small></p>") if bledy else ""
    return f"""<html><body style="font-family:Arial,sans-serif">
<h2>Przetargi – {data}</h2><p>Nowe: <b>{len(nowe)}</b></p>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-size:13px">
<tr style="background:#eee"><th>Pr.</th><th>Branża</th><th>Źródło</th><th>Przedmiot</th><th>Zamawiający</th>
<th>Termin</th><th>Dopasowanie</th></tr>{wiersze}</table>
<p><small>A = CPV/tytuł, S = strona gminy/powiatu, B = tylko w treści ogłoszenia.</small></p>
{stopka}</body></html>"""


def wyslij_mail(nowe, data):
    user, haslo, do = (os.environ.get(k) for k in ("SMTP_USER", "SMTP_PASS", "EMAIL_TO"))
    if not (user and haslo and do):
        log("Brak danych SMTP – pomijam e-mail.")
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Przetargi {data}: {len(nowe)} nowych"
    msg["From"], msg["To"] = user, do
    msg.attach(MIMEText(html_maila(nowe, data), "html", "utf-8"))
    with smtplib.SMTP_SSL(os.environ.get("SMTP_HOST", "smtp.gmail.com"),
                          int(os.environ.get("SMTP_PORT", "465"))) as s:
        s.login(user, haslo)
        s.sendmail(user, [a.strip() for a in do.split(",")], msg.as_string())
    log(f"Wysłano e-mail do {do}")


def main():
    teraz = datetime.now(timezone.utc)
    od = (teraz - timedelta(days=DNI_WSTECZ)).replace(hour=0, minute=0, second=0, microsecond=0)
    data = datetime.now().strftime("%Y-%m-%d")
    WYNIKI.mkdir(exist_ok=True)

    stan = wczytaj(PLIK_STANU, {})
    widziane = set(stan.get("widziane", []))
    widziane_strony = stan.get("strony", {})

    znalezione = zrodlo_bzp(od, teraz) + zrodlo_ted(od) + zrodlo_strony(widziane_strony)

    # usuń duplikaty w obrębie jednego przebiegu
    unikalne = {}
    for w in znalezione:
        unikalne.setdefault(w["id"], w)
    znalezione = list(unikalne.values())

    nowe = [w for w in znalezione if w["id"] not in widziane]
    for w in nowe:
        w["znaleziono"] = teraz.isoformat()

    aktywne = {w["id"]: w for w in wczytaj(PLIK_AKTYWNE, [])}
    for w in nowe:
        aktywne[w["id"]] = w
    aktywne = [w for w in aktywne.values() if nadal_aktywny(w, teraz)]

    md = markdown(nowe, aktywne, data)
    PLIK_NAJNOWSZE.write_text(md, encoding="utf-8")
    (WYNIKI / f"{data}.md").write_text(md, encoding="utf-8")
    PLIK_AKTYWNE.write_text(json.dumps(aktywne, ensure_ascii=False, indent=1), encoding="utf-8")
    widziane |= {w["id"] for w in znalezione}
    PLIK_STANU.write_text(json.dumps({"widziane": sorted(widziane)[-20000:], "strony": widziane_strony,
                                      "ostatni_przeglad": teraz.isoformat()}, indent=1), encoding="utf-8")
    log(f"Nowych: {len(nowe)}, aktywnych: {len(aktywne)}")
    for a, b, c in raport_zrodel:
        if b != "OK":
            log(f"  ! {a}: {c}")
    if nowe:
        wyslij_mail(nowe, data)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        log(f"BŁĄD KRYTYCZNY: {e}")
        sys.exit(1)
