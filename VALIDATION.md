# Wynik walidacji — 22 października 2026

## Wykonane z powodzeniem

- `python scripts/check.py`: składnia Pythona, JSON, YAML (w tym duplikaty
  kluczy) i **25 testów jednostkowych**.
- `python scripts/smoke_ha.py` w środowisku **Python 3.13.16 / HA Core
  2025.10.4**: rzeczywiste uruchomienie integracji bez atrap API HA, na
  tymczasowej bazie SQLite.

Test uruchomieniowy potwierdził:

1. Walidację i załadowanie dostarczonego pakietu integracji i helpera.
2. Utworzenie czterech sensorów oraz helpera ustawionego na 90%.
3. Stan `unknown` przy braku odpowiedniej historii.
4. Odczyt syntetycznych statystyk z prawdziwej bazy Recorder, w tym punktu
   sprzed ponad 400 dni; model nie ograniczył importu do 7–14 dni.
5. Tempo około 2 p.p./dobę dla syntetycznego wzrostu i obliczenie prognozy.
6. Renderowanie polskiego komunikatu karty dashboardu przez silnik szablonów HA.
7. Skrócenie prognozy po zmianie helpera z 90% na 85%.
8. Wyzerowanie wiedzy o nowym bieżącym cyklu po ręcznym oznaczeniu odbioru,
   bez liczenia spadku jako ujemnego tempa.
9. Trwały zapis i ponowne odczytanie agregatów oraz ręcznego znacznika.

Testy jednostkowe pokryły krótką historię, stabilny wzrost, stagnację, tempo
ujemne, wartości spoza zakresu, `unknown`, `unavailable`, NaN, niespójne dane,
pojedyncze skoki, oczekiwanie na potwierdzenie opróżnienia, pełne cykle,
większą wagę odmiennie zachowującego się bieżącego cyklu, ręczny odbiór,
długą historię, zatrzymanie wzrostu w ostatnich dniach, przerwy, rzadkie dane,
osiągnięty i zmieniony próg, nieaktualne dane, zmianę czasu oraz niestabilny trend.
Adapter przetestowano pod kątem częstych raportów, ważenia czasem, przerwania
przenoszenia po `unavailable`, limitu przenoszenia stanu, jednostek odległości,
priorytetu surowych danych i pomijania godziny zawierającej pompowanie.

## Granice weryfikacji

- Brak dostępu do rzeczywistej instalacji, wersji HA, bazy, konfiguracji Recorder
  i dashboardu użytkownika. Nie wykonano wdrożenia w domu ani testu na jego danych.
- Nie potwierdzono zgodności z HA Core 2026.10 ani innymi wersjami poza 2025.10.4.
  Po instalacji wymagane są lokalna kontrola konfiguracji i sprawdzenie dziennika.
- Nie wykonano wizualnego testu w przeglądarce z istniejącym motywem/card-mod.
  Sprawdzono YAML i szablon komunikatu, a nie wygląd rzeczywistego dashboardu.
- Nie mierzono błędu predykcji na rzeczywistych, oznaczonych cyklach użytkownika.
  Zmienne zużycie wody ogranicza trafność daty; „wysoka” to jakość danych według
  reguł modelu, a nie gwarancja terminu ani procentowy poziom ufności.
- Test nie uruchamia HTTP, frontendu ani skanowania interfejsów sieciowych;
  bada część Core, która jest potrzebna tej integracji.

Po publikacji na GitHub workflow `Validate configuration and forecast` przeszedł:
kontrole plików, 25 testów i test rzeczywistego HA Core 2025.10.4.
Aktualne wyniki kolejnych uruchomień, w tym kontroli HACS, są dostępne
w [GitHub Actions](https://github.com/kamiljaworski88/szambo-forecast-ha/actions).
