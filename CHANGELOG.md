# Historia zmian

## 1.3.0 — 2026-11-11

**Program**
- Nowy checkbox **„Ukryj firmy, do których aplikowałem”** nad listą ofert. Ukrywa wszystkie oferty firm, do których
  wysłałeś już CV. Wybór jest zapamiętywany, a liczniki kategorii go uwzględniają. W widoku „Aplikowałem” go nie ma.
- Lista ofert sama się odświeża: aplikacja zapisana z wtyczki na justjoin.it pojawia się bez przeładowania strony
  (po powrocie na kartę programu i co 15 s, gdy karta jest widoczna). Odświeżanie nie przerywa pisania w formularzach.

**Wtyczka 1.2.1**
- Poprawka: po kliknięciu górnego przycisku „Aplikuj” (w prawym górnym rogu oferty) pasek z pytaniem
  „Wysłałeś CV?” znikał od razu. Teraz zostaje, tak jak po kliknięciu dolnego przycisku.
- Przycisk „Aplikuj” jest rozpoznawany pewniej (kliknięcie w ikonę lub napis w środku, `aria-label`, `role="button"`).

Aktualizacja: `git pull`, uruchom program ponownie i przeładuj wtyczkę na stronie rozszerzeń przeglądarki.

## 1.2.0 — 2026-10-28

- Nowy wygląd: menu boczne z licznikami, kafelki ze statystykami, tabela ofert z inicjałami firm.
- 4 motywy do wyboru: Dashboard, Aurora, Brutal, Radar.
- Wtyczka 1.2.0: nazwa firmy odczytywana z danych strukturalnych strony oferty.

Starsze wersje: [wydania na GitHubie](https://github.com/pmilosz/didIJJIT/releases).
