# Prognoza odbioru szamba dla Home Assistant

[![Dodaj do HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=kamiljaworski88&repository=szambo-forecast-ha&category=integration)

Lokalna integracja prognozująca dni i datę osiągnięcia progu zapełnienia.
Od wersji **0.2.0** konfigurację dodaje się z interfejsu Home Assistant.
Domyślny próg: **90%**. Zachowuje istniejące sensory i wzór
`(1 - distance / 1.60) * 100`. Nie steruje urządzeniami i nie wysyła danych do chmury.

To **nowe, samodzielne repozytorium**, a nie kopia całej konfiguracji domu.
Nie było dostępu do Twojej wersji HA, ustawień Recorder, istniejącego widoku
ani rzeczywistej historii. Przykład dashboardu wymaga wklejenia do Twojego widoku.

## Instalacja w istniejącym Home Assistant

### Instalacja przez HACS

W HACS otwórz **⋮ → Repozytoria niestandardowe**, dodaj adres
`https://github.com/kamiljaworski88/szambo-forecast-ha` i wybierz typ
**Integracja**. Następnie wyszukaj **Septic Forecast — Prognoza szamba**
i pobierz wydanie. Możesz też użyć przycisku „Dodaj do HACS” powyżej.

To repozytorium niestandardowe; nie jest automatycznie częścią domyślnego
katalogu HACS. **HACS pobiera kod integracji, ale nie kopiuje przykładów do
Twojej konfiguracji ani nie edytuje dashboardu.** Aktualizacje kodu wykonujesz
przez HACS, z restartem HA po aktualizacji; archiwum pozostaje w HA.

### Konfiguracja w interfejsie HA (zalecana)

1. Pobierz **0.2.0 lub nowszą** w HACS i **zrestartuj Home Assistant**.
2. Otwórz **Ustawienia → Urządzenia i usługi → Dodaj integrację → Prognoza szamba**.
3. Wybierz sensor procentu `sensor.procent_szamba` oraz sensor odległości
   `sensor.czujnik_szamba_distance_sensor`. Pozostaw próg 90% i datę początku
   historii 2000-01-01, aby wykorzystać całą dostępną historię.
4. Pole istniejącego helpera pozostaw puste. Integracja utworzy
   `number.szambo_prognoza_prog` z trwałym progiem — jego zmiana przeżywa restart.
   Możesz zamiast tego wskazać istniejący `input_number` lub `number`.
   Wtedy jego wartość jest progiem, a integracja nie tworzy dodatkowego pola liczbowego.
5. Dodaj kartę z `examples/dashboard_szambo_ui.yaml` do własnego dashboardu.
   Jeżeli wybrano zewnętrzny helper, zastąp w karcie ID progu jego identyfikatorem.

**Nie dopisujesz niczego do `configuration.yaml` przy instalacji przez UI.**
Opcje sensorów, początku historii i wykrywania odbioru można później zmienić
w opcjach integracji. Próg zmieniasz przez encję liczbową na dashboardzie.

Jeśli nadal pojawia się komunikat o braku możliwości dodania przez interfejs,
sprawdź zainstalowaną wersję w HACS, uruchom ponownie HA po aktualizacji,
a następnie odśwież przeglądarkę. Wersja 0.1.0 obsługiwała wyłącznie YAML.

### Istniejąca instalacja YAML / instalacja alternatywna

Konfiguracja z wersji 0.1.0 zostanie automatycznie zaimportowana jako jedna
pozycja w integracjach. Zachowuje dotychczasowe identyfikatory sensorów,
zewnętrzny helper oraz archiwum historii i znaczniki odbioru. Nie dodawaj drugiej
instancji przez UI. Po udanym imporcie możesz usunąć sekcję `septic_forecast:`
z YAML; pozostaw definicję helpera `input_number`, jeżeli nadal go używasz.

1. Jeśli instalujesz ręcznie zamiast przez HACS, skopiuj folder
   `custom_components/septic_forecast` do `/config/custom_components/septic_forecast`.
   Przy poniższym wariancie YAML import nastąpi automatycznie.
   Wersja przetestowana: **HA Core 2025.10.4**.
   Nowsze wersje wymagają sprawdzenia konfiguracji i testu uruchomienia na Twoim HA.
2. Jeśli nie używasz pakietów, **dopisz** `packages: !include_dir_named packages`
   do istniejącego klucza `homeassistant:` w `configuration.yaml`.
   Nie twórz drugiego klucza. Jeśli pakiety już działają, użyj istniejącej organizacji.
3. Skopiuj `examples/package_szambo.yaml` do
   `/config/packages/szambo_prognoza.yaml`. Nie dodawaj ponownie istniejących
   sensorów procentu ani odległości. Jeśli masz już helper progu, wpisz jego ID
   w `threshold_entity` i pomiń sekcję `input_number` z przykładu.
4. Uruchom kontrolę konfiguracji w HA, a potem zrestartuj HA.
   Helper startuje od **90%**. Jeśli chcesz zachować jego późniejsze zmiany
   pomiędzy restartami, po pierwszym poprawnym uruchomieniu usuń tylko linię
   `initial: 90` z jego definicji. Bez tej zmiany każdy restart przywraca 90%.
5. Poczekaj na pierwszy import historii. Przy dużej bazie może potrwać dłużej.
   Baza jest odczytywana w wykonawcy Recorder, poza pętlą zdarzeń HA.
6. Dodaj część prognozy z `examples/dashboard_szambo.yaml` obok obecnych
   informacji o szambie. Pełny przykład zawiera również istniejące dwa wiersze.
   Możesz pozostawić własne wiersze i dodać tylko kolejne dwie karty.
   Ich prognoza korzysta z kart wbudowanych w HA.
7. Sprawdź nazwy encji w Narzędziach deweloperskich → Stany. Jeśli HA nadał
   przyrostek `_2` z powodu wcześniejszej encji o tej samej nazwie, odpowiednio
   popraw odwołania w dashboardzie. Wyświetlane polskie nazwy można edytować w UI.

Kolory oryginalnego procentu pozostają: **<60 zielony, 60–<90 pomarańczowy,
≥90 czerwony**. Zmiana progu prognozy nie zmienia tych kolorów.
Kolorowanie z przykładu wymaga już używanego `card-mod`; prognoza go nie wymaga.

## Encje i akcja

| ID domyślne | Znaczenie |
| --- | --- |
| `sensor.szambo_dni_do_odbioru` | Liczba dni; `unknown` przy niewiarygodnym wyniku |
| `sensor.szambo_przewidywana_data_odbioru` | Data/czas osiągnięcia progu; `unknown` bez prognozy |
| `sensor.szambo_tempo_napelniania` | Tempo użyte w prognozie, w punktach procentowych na dobę |
| `sensor.szambo_wiarygodnosc_prognozy` | `brak`, `ograniczona`, `wysoka` lub `próg osiągnięty` |
| `number.szambo_prognoza_prog` | Trwały próg, domyślnie 90%, tworzony przy konfiguracji UI bez zewnętrznego helpera |
| `input_number.szambo_prognoza_prog` | Zewnętrzny helper z przykładu YAML; opcjonalny przy konfiguracji UI |
| `septic_forecast.mark_emptying` | Akcja ręcznego oznaczenia zakończonego odbioru |

Sensor wiarygodności zawiera powód decyzji, liczbę dni bieżącego cyklu,
liczbę pełnych cykli, tempa bieżące i historyczne, wagę, liczbę odrzuconych
godzin oraz diagnostykę rzeczywiście zaimportowanej historii.
To opis jakości danych według reguł modelu, **nie statystyczny poziom ufności**.

## Skąd pochodzi historia

Repozytorium nie zawiera bazy, eksportu danych ani prawdziwych odczytów.
Integracja uzyskuje dostęp dopiero **wewnątrz uruchomionego HA**, przez jego
API Recorder i jego wykonawcę. Nie potrzebuje URL bazy, loginu ani tokenu.
Nie otwiera bezpośrednio pliku SQLite i nie uzależnia się od schematu SQL.

Pierwszy import prosi o **całą dostępną historię od 1 stycznia 2000**, czyli
praktycznie całą historię HA, a nie ostatnie 7–14 dni. Opcjonalne `history_start`
pozwala świadomie wykluczyć np. okres przed kalibracją czujnika.

- Pobierane są godzinowe statystyki długoterminowe procentu; jeśli procent nie
  ma statystyk, używana jest dostępna odległość, przeliczona tym samym wzorem.
  Akceptowane jednostki odległości: `m`, `cm`, `mm` (brak jednostki oznacza `m`).
  Procent ze statystyk musi mieć jednostkę `%`.
- Pobierane są także wszystkie zachowane surowe stany, w porcjach do 31 dni.
  Wspólny zakres zastępują agregaty surowych danych; procent ma pierwszeństwo
  przed odległością. Dalsze odczyty obejmują sześciogodzinne nakładanie ostatniego
  importu, które służy obsłudze opóźnionych zapisów. To **nie okno modelowania**.
- Własne agregaty godzinowe i znaczniki ręczne są zachowane w
  `/config/.storage/septic_forecast`. Restart i późniejszy purge Recorder nie
  usuwają już wczytanych cykli. Nie edytuj tego pliku ręcznie przy uruchomionym HA.
- Zmiana źródeł lub `history_start` powoduje nowy import zamiast mieszania
  niezgodnych historii. Ręczne znaczniki poprzedniej konfiguracji nie są przenoszone.

**Przed wdrożeniem sprawdź Recorder** w swoim `configuration.yaml`, pakietach
i plikach dołączonych przez `!include`:

1. Czy `include`/`exclude` nie wyłącza obu źródeł?
2. Jakie jest `purge_keep_days`? Domyślnie surowa historia Recorder ma 10 dni.
3. Czy w Narzędziach deweloperskich → Statystyki jest procent lub odległość
   z poprawną jednostką i `state_class: measurement`?
4. Czy wykres historii rzeczywiście sięga do wcześniejszych opróżnień?

Nie zmieniaj ustawień Recorder ani filtrów na ślepo. Repo nie narzuca
globalnego okresu retencji. Już usuniętej historii nie da się odzyskać przez
wydłużenie `purge_keep_days` ani dodanie teraz `state_class`. Jeśli historia
jest tylko w zewnętrznym InfluxDB, ten projekt nie odczytuje jej automatycznie.
Gdy nie ma starszej historii ani statystyk, model zaczyna od zachowanych danych
i uczciwie nie pokazuje poprzednich pełnych cykli.

Diagnostyka `historia.initial_import` pokazuje zakres żądania, źródła statystyk
i liczniki importu. `archived_hours`, `oldest_hour`, `newest_hour` pokazują
faktycznie zachowane agregaty. Liczniki źródeł mogą nakładać się w czasie;
nie sumuj ich jako liczby unikalnych godzin. `recorded_entities` pokazuje filtry
bieżącej konfiguracji Recorder, a nie gwarantowaną dostępność historii.

## Algorytm

1. Surowe odczyty są próbkowane co kwadrans z uwzględnieniem czasu trwania
   stanu, a potem redukowane do median godzinowych. Godzina wymaga co najmniej
   3 próbek. Stan jest przenoszony maksymalnie 6 godzin; `unknown`/`unavailable`
   przerywa przenoszenie. Statystyki historyczne dostarczają średniej godzinowej;
   godziny o rozpiętości min–max ≥15 p.p. są odrzucane.
2. Spadek o co najmniej `emptying_drop` (domyślnie 15 p.p.) względem mediany
   sześciu ostatnich zaakceptowanych godzin sugeruje opróżnienie. Potwierdzają
   je dwie niskie godziny oddalone o co najmniej godzinę. Do tego czasu prognoza
   jest wstrzymana. Pojedynczy niski odczyt nie kończy cyklu.
3. Duży skok dodatni lub mniejszy nagły spadek jest odrzucany przy odchyleniu
   przekraczającym większą z wartości 8 p.p. i 25 p.p. × upływ czasu w dobach.
   Przerwa >48 godzin rozdziela ciąg danych, bo mogła ukryć odbiór.
4. Z każdego cyklu osobno powstają mediany dni lokalnych. Dzień wymaga ≥6 godzin
   rozciągniętych na ≥5 godzin; dzisiejszy dzień jest wyłączony z dopasowania.
   Minimum do modelowania to 3 takie dni rozciągnięte na około 2 doby.
5. Tempo jest medianą nachyleń par punktów (Theil–Sen), odporną na pojedyncze
   odchylenia. Wykorzystuje **cały bieżący cykl**. Dla cyklu >120 dni obliczenie
   obejmuje 120 punktów równomiernie wybranych z całego okresu.
6. Poprzednie cykle liczą się jako pełne dopiero między dwoma rozpoznanymi lub
   ręcznie oznaczonymi opróżnieniami. Wymagają ≥5 dni, wzrostu ≥10 p.p.
   i mediany błędu ≤2,5 p.p. Pierwszy niepełny fragment historii nie jest pełnym
   cyklem. Mediana tempa wszystkich poprawnych pełnych cykli stanowi odniesienie.
7. Bieżący cykl ma wagę 65% na początku, 80% od 7 dni i 90%, gdy różni się
   od typowego o >30% lub >0,5 p.p./dobę (obowiązuje większy próg).
   Bez poprzednich cykli waga wynosi 100%. Ostatnie 7 dni służy dodatkowo
   wykrywaniu zmiany zużycia: przy wyraźnej zmianie bieżące tempo łączy 80%
   tempa ostatnich dni i 20% tempa całego cyklu. Nie zastępuje to długiej historii.
8. Prognoza: **(próg − bieżący procent) / tempo**, a data to teraz + liczba dni.
   Bieżący procent zawsze pochodzi z Twojego oryginalnego sensora.

Nie ma prognozy przy błędnych danych, rozbieżności procentu i odległości >5 p.p.,
braku świeżych źródeł lub agregatów przez 6 godzin, braku wystarczających dni,
nierozstrzygniętym opróżnieniu, tempie ≤0,05 albo >25 p.p./dobę,
zbyt niestabilnym trendzie lub horyzoncie >365 dni. Ostatni tydzień bez wzrostu
również wstrzymuje prognozę mimo starszego dodatniego trendu.
Przy poprawnym, potwierdzonym poziomie ≥próg pokazywane jest 0 dni i „zamów
odbiór”; tempo może wtedy pozostawać `unknown`.

Godziny importowane są co 15 minut (tylko godziny zakończone), a zmiana źródeł
lub progu natychmiast przelicza wynik. Data zależy od aktualnego poziomu;
tempo od zakończonych dni. Dlatego wynik może zmienić się po północy.

## Ręczne oznaczanie odbioru

Po **zakończeniu** odbioru i ustabilizowaniu obu odczytów kliknij przycisk
dashboardu albo wywołaj w Narzędziach deweloperskich → Akcje:

```yaml
action: septic_forecast.mark_emptying
data: {}
```

Wywołaj raz, nie podczas pompowania. Integracja odrzuca niespójne odczyty.
Znacznik rozpoczyna nowy cykl i pomija godzinę zawierającą odbiór, nie usuwając
historii. Nowy trend wymaga nowych dni danych — spadek nie trafia do nachylenia.
Użyj tej akcji szczególnie przy częściowym opróżnieniu <15 p.p., przerwach
w odczytach lub niepewnym automatycznym wykryciu. Dwie niskie godziny mogą
być też trwałą awarią czujnika; sam poziom nie dowodzi, że był prawdziwy odbiór.

## Walidacja

Lokalnie, bez HA (Python ≥3.12 i PyYAML):

```bash
python -m pip install PyYAML
python scripts/check.py
```

Kontrola obejmuje składnię Pythona, JSON, YAML z wykrywaniem duplikatów kluczy
oraz testy numeryczne i jednostkowe adaptera. Testy adaptera jawnie podstawiają
API HA; **nie są testem uruchomienia na prawdziwym Home Assistant**.

Osobny test rzeczywistego HA Core (Python 3.13, środowisko testowe):

```bash
python -m pip install homeassistant==2025.10.4 PyYAML 'pycares<5'
python scripts/smoke_ha.py
python scripts/smoke_ha.py --ui
```

Ograniczenie `pycares<5` dotyczy środowiska testowego starego HA i jego `aiodns`;
nie instaluj tych pakietów ręcznie w produkcyjnym HA OS.
Test tworzy i usuwa tymczasową bazę SQLite, importuje syntetyczne statystyki
obejmujące okres sprzed ponad 400 dni, uruchamia prawdziwe integracje Recorder,
sensorów i helpera, sprawdza wynik, szablon dashboardu, zmianę progu,
ręczny reset oraz ponowne wczytanie archiwum. Drugi wariant sprawdza konfigurator
UI, walidację pól, opcje i ponowne ładowanie integracji, trwałość progu,
ochronę przed duplikatami oraz wyłączenie i ponowne włączenie. Wariant YAML
sprawdza zachowanie starego archiwum i migrację encji bez dodawania `_2`.
Testy nie uruchamiają serwera HTTP.
Wyniki wykonanych kontroli opisuje `VALIDATION.md`.

Sprawdzenie na docelowym HA:

1. Narzędzia deweloperskie → YAML → **Sprawdź konfigurację**; alternatywnie
   z terminala HA OS: `ha core check`. Dla HA Core: `hass --script check_config -c /config`.
2. Po restarcie sprawdź dziennik pod kątem `septic_forecast` oraz cztery nowe
   sensory i helper. Początkowo wynik może być `unknown` podczas importu.
3. Otwórz atrybuty sensora wiarygodności i porównaj początek archiwum z historią
   rzeczywiście dostępną w HA. Sprawdź liczbę pełnych cykli i powody odrzucenia.
4. Zmień próg np. 90 → 85 i sprawdź, że liczba dni maleje, a kolory oryginalnego
   procentu zachowują progi 60 i 90. Wróć do żądanego progu.
5. Przelicz ręcznie `(próg − procent) / tempo` i porównaj wynik (zaokrąglenia).
6. Po prawdziwym odbiorze sprawdź, czy pojawia się nowy cykl i tymczasowy brak
   prognozy. Nie oznaczaj fikcyjnego odbioru w produkcji tylko na potrzeby testu.

## Ograniczenia i bezpieczeństwo

- Przyjazd gości, wyjazdy, podlewanie, zmiana liczby domowników, nieszczelność
  lub wody gruntowe mogą zmieniać przyszłe tempo. Data nie jest gwarancją.
  Nie czekaj z zamówieniem do ostatniej chwili; zachowaj zapas logistyczny.
- Model zakłada, że procent obliczony z wysokości jest użytecznym przybliżeniem
  zapełnienia. Geometria zbiornika może powodować nieliniowość objętości.
- Statystyki godzinowe tracą szczegóły odbioru, którego czas może przesunąć się
  o 1–2 godziny. Nie wykryją zdarzenia całkowicie ukrytego w przerwie danych.
- Nie importuje historii z kopii zapasowej, InfluxDB ani plików CSV.
  Nie dodaje `state_class` do istniejących sensorów i nie zmienia Recorder.
- Własne archiwum rośnie z historią (około 8760 agregatów na rok).
  Początkowy import długiej surowej historii obciąża bazę; uruchom poza szczytem.
  Późniejsze dopisanie starszej historii do Recorder wymaga ponownego importu:
  zatrzymaj HA, zabezpiecz kopię `/config/.storage/septic_forecast`, usuń ten
  plik i uruchom HA. To także usuwa ręczne znaczniki — zachowaj ich kopię.
- Wszystko działa lokalnie. Brak zależności pip w integracji, HTTP, chmury,
  tokenów i usług pośredniczących. Dokumentacja/testy deweloperskie mogą pobierać
  pakiety przy ich instalacji; działająca integracja tego nie robi.
- Integracja używa wewnętrznych API Recorder, więc po aktualizacji HA sprawdź
  dziennik i import. Nie deklarujemy zgodności ze wszystkimi przyszłymi wersjami.

## Pliki

- `custom_components/septic_forecast/`: integracja, model, import historii,
  definicja akcji, cztery sensory i manifest.
- `examples/package_szambo.yaml`: integracja i jeden helper.
- `examples/configuration_fragment.yaml`: dołączanie pakietów.
- `examples/dashboard_szambo.yaml`: karta z polskim komunikatem i progiem.
- `examples/dashboard_szambo_ui.yaml`: karta dla progu utworzonego przez integrację UI.
- `tests/`: scenariusze modelu i adaptera historii.
- `scripts/check.py`: kontrole offline.
- `scripts/smoke_ha.py`: test na rzeczywistym HA Core i tymczasowej bazie SQLite.
- `.github/workflows/check.yml`: automatyczne kontrole po publikacji repozytorium.
- `.github/workflows/hacs.yml`: walidacja struktury i metadanych HACS.
- `hacs.json`: manifest HACS, instalacja z katalogu `custom_components`.
- `PRIVACY.md`: przepływ i zakres danych.
- `CHANGELOG.md`, `LICENSE`: historia wydań i licencja MIT.
- `VALIDATION.md`: wynik wykonanych kontroli i granice weryfikacji.

Usunięcie integracji z UI usuwa jej encje i zatrzymuje odczyty; archiwum
`.storage/septic_forecast` pozostaje do ponownego dodania. Nie usuwa źródłowych
sensorów ani historii Recorder. Przed zmianą sensorów lub daty początku historii
zachowaj kopię zapasową HA — inny zestaw źródeł rozpoczyna inne archiwum.

Źródła projektu: [Recorder](https://www.home-assistant.io/integrations/recorder/),
[statystyki a statystyki długoterminowe](https://www.home-assistant.io/integrations/statistics/),
[API historii Core 2025.10.4](https://github.com/home-assistant/core/blob/2025.10.4/homeassistant/components/recorder/history/__init__.py),
[API statystyk Core 2025.10.4](https://github.com/home-assistant/core/blob/2025.10.4/homeassistant/components/recorder/statistics.py).

## Publikowanie kolejnych wersji

Podnieś `version` w `custom_components/septic_forecast/manifest.json`, uzupełnij
`CHANGELOG.md`, uruchom kontrole i opublikuj GitHub Release z tagiem `vX.Y.Z`
zgodnym z wersją manifestu. HACS pobiera pliki integracji bezpośrednio z repozytorium;
nie jest wymagane ręczne załączanie paczki ZIP do wydania.
