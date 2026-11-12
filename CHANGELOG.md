# Historia zmian

## 1.4.0 — 2026-11-12

### pracuj.pl — drugie źródło ofert i aplikacji

Wtyczka czyta strony pracuj.pl, które **sam otwierasz** w przeglądarce. Program nie łączy się z pracuj.pl i niczego nie pobiera w tle.

- **Zapisane wyszukiwania** z konta pracuj.pl importują się same po wejściu na pracuj.pl. Prowadzą do www.pracuj.pl,
  czyli do ofert ze wszystkich kategorii. Nowa zakładka **pracuj.pl** pozwala je otwierać, usuwać i dodawać ręcznie.
- **Oferty** z otwieranych wyszukiwań trafiają na wspólną listę ze znaczkiem *pracuj.pl*, w kategoriach jak na justjoin.it:
  według słowa z wyszukiwania (lista „php” → PHP), a bez niego według nazwy stanowiska. „Oferty rekomendowane” są pomijane.
- **Pasek na stronie oferty pracuj.pl**, tak jak na justjoin.it: „już aplikowałeś do tej firmy” i pytanie „Wysłałeś CV?”
  po kliknięciu „Aplikuj”. Pytanie czeka do 2 godzin, także po przejściu do formularza.
- **Znaczek na liście wyników pracuj.pl** przy firmach, do których już wysłałeś CV.
- **Import listy „Moje aplikacje”** z pracuj.pl do rejestru aplikacji, bez duplikatów.

### Pozostałe zmiany

- **„Już aplikowałeś na to stanowisko”** — oprócz tej samej firmy program rozpoznaje to samo stanowisko, także między
  serwisami. Pomija poziom i dopiski, np. „Senior Python Developer (K/M)” = „Python Developer”. To tylko ostrzeżenie, nic nie jest ukrywane.
- **„Aplikowałem”** pokazuje też aplikacje, których oferty nie ma na liście (spoza Twoich filtrów, ręczne, z historii,
  z wtyczki). Są w osobnej tabeli pod ofertami, a licznik je uwzględnia.
- Pasek wtyczki mówi wprost, gdy program trzeba uruchomić ponownie albo gdy nie rozpoznał ofert na stronie.

### Aktualizacja

- Baza z poprzednich wersji jest uzupełniana automatycznie: dochodzą nowe kolumny, nic nie jest usuwane.
  Dotychczasowe oferty dostają źródło „justjoin.it”, a odświeżanie justjoin.it nie zmienia ofert z pracuj.pl.
- **Wtyczka 1.3.0** ma nowe uprawnienie do pracuj.pl. Po `git pull` uruchom program ponownie i przeładuj wtyczkę na stronie rozszerzeń.

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
