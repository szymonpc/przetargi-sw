# Przetargi – SW Sp. z o.o.

Codzienny przegląd (pon–pt, 7:00) dla województw: warmińsko-mazurskie, kujawsko-pomorskie,
mazowieckie, pomorskie.

## Źródła
1. **BZP / e-Zamówienia** – wszystkie przetargi Pzp (≥130 tys. zł), niezależnie od platformy
   (platformazakupowa, ezamawiajacy, smartpzp itd.).
2. **TED** – duże przetargi unijne.
3. **Strony gmin, miast, powiatów i platform** – lista w `zrodla_strony.csv`.
   Tu łapią się zapytania ofertowe poniżej 130 tys. zł.

## Jak dodać stronę
Dopisz linię do `zrodla_strony.csv`: `nazwa,adres,województwo,uwagi`.
Najlepiej podać podstronę z listą przetargów/zapytań (np. BIP → Zamówienia publiczne)
albo profil zamawiającego na platformazakupowa.pl/pn/...
Po przebiegu sprawdź tabelę „Stan źródeł” w `wyniki/najnowsze.md` – BŁĄD oznacza zły adres.

## Pliki wyników
- `wyniki/najnowsze.md` – ostatni przegląd + stan źródeł
- `wyniki/aktywne.json` – aktywne przetargi (dane)
- `wyniki/RRRR-MM-DD.md` – archiwum

## Branże
- **metal** – ogrodzenia, balustrady, konstrukcje, wiaty, stal nierdzewna…
- **nawierzchnie** – kostka brukowa, chodniki, place, parkingi, ścieżki (wyłączysz: `SZUKAJ_NAWIERZCHNI = False`)

## Priorytety
- **A** – branża w CPV lub tytule
- **S** – znalezione na stronie gminy/powiatu
- **B** – branża tylko w treści ogłoszenia (np. balustrada w remoncie szkoły – sprawdź przedmiar)

## Ustawienia
Słowa kluczowe, CPV, wykluczenia i województwa: sekcja KONFIGURACJA w `przetargi.py`.
`SLOWA_MOCNE` – szukane w tytule i treści; `SLOWA_SLABE` – tylko w tytule.
