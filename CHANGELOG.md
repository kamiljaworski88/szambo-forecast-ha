# Zmiany

## 0.2.0

- Konfigurator przez Ustawienia → Urządzenia i usługi → Dodaj integrację.
- Wybór istniejących sensorów i opcjonalnego helpera w interfejsie HA.
- Trwały próg `number.szambo_prognoza_prog` (domyślnie 90%), gdy nie wybrano helpera.
- Opcje integracji, przeładowanie, wyłączenie i ponowne włączenie.
- Automatyczny import konfiguracji YAML z zachowaniem identyfikatorów encji i archiwum.
- Polskie i angielskie etykiety oraz komunikaty błędów formularza.
- Oddzielny przykład dashboardu dla konfiguracji UI.

## 0.1.0

- Pierwsze wydanie integracji do instalacji przez HACS jako repozytorium niestandardowe.
- Dni, data, tempo napełniania i opis jakości prognozy.
- Import całej dostępnej historii Recorder i statystyk długoterminowych.
- Rozdzielanie cykli, odporne dopasowanie trendu i odniesienie do poprzednich cykli.
- Automatyczne wykrywanie opróżnienia oraz ręczna akcja oznaczenia odbioru.
- Jeden helper progu (domyślnie 90%) i przykładowa karta dashboardu.
- Dane pomiarowe pozostają w HA; repozytorium zawiera jedynie dane syntetyczne.
- Testy jednostkowe oraz test uruchomieniowy na HA Core 2025.10.4.

HACS instaluje kod integracji. Pakiet YAML i kartę dashboardu dodaje się
zgodnie z README. Nie ma jeszcze konfiguratora integracji przez interfejs HA.
