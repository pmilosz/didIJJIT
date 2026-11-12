# Historia zmian

## 1.4.0 — w przygotowaniu

**pracuj.pl** — drugie źródło ofert i aplikacji (przez wtyczkę, ze stron, które sam otwierasz; program nie łączy się z pracuj.pl):
- zapisane wyszukiwania z konta pracuj.pl importują się same (prowadzą do www.pracuj.pl, czyli wszystkich kategorii);
  oferty z otwieranych wyszukiwań trafiają na listę z oznaczeniem *pracuj.pl*, bez „ofert rekomendowanych”;
- ten sam filtr zapisany różnie w adresie („/praca/php;kw/gdynia;wp” i „/praca?kw=php&wp=Gdynia”) to jedno wyszukiwanie;
- pasek mówi wprost, gdy program jest w starszej wersji i trzeba go uruchomić ponownie;
- filtry z wieloma wartościami („wm=home-office,hybrid”) i kategorie w ścieżce są rozpoznawane jako to samo wyszukiwanie;
- gdy wtyczka nie rozpozna ofert na stronie wyszukiwania, mówi o tym zamiast milczeć;

**„Aplikowałem”** pokazuje też aplikacje, których oferty nie ma na liście (spoza Twoich filtrów, zapisane wtyczką,
ręczne, z historii, z pracuj.pl) — w osobnej tabeli pod ofertami; licznik je uwzględnia.
- nowa zakładka **pracuj.pl** z listą wyszukiwań (otwórz / usuń / dodaj adres ręcznie) i instrukcją;
- import listy „Moje aplikacje” z pracuj.pl do rejestru aplikacji, bez duplikatów;
- pasek „już aplikowałeś do tej firmy” i pytanie „Wysłałeś CV?” na stronach ofert pracuj.pl;
- znaczek przy ofertach firm, do których już aplikowałeś, bezpośrednio na liście wyników pracuj.pl.

**Ostrzeżenie „na to samo stanowisko”** — oprócz tej samej firmy program rozpoznaje to samo stanowisko także między serwisami
(pomija poziom i dopiski, np. „Senior Python Developer (K/M)” = „Python Developer”).

**Zgodność wstecz:** baza z poprzednich wersji jest uzupełniana automatycznie (nowe kolumny, nic nie jest usuwane);
dotychczasowe oferty dostają źródło „justjoin.it”. Odświeżanie justjoin.it nie zmienia ofert z pracuj.pl.

**Wtyczka 1.3.0** — nowe uprawnienie do pracuj.pl. Po aktualizacji przeładuj wtyczkę na stronie rozszerzeń.

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
