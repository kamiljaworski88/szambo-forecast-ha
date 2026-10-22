# Prywatność

Integracja działa lokalnie wewnątrz Home Assistant. Nie otwiera połączeń HTTP,
nie używa pośredniczących serwerów, analityki ani telemetrii. Odczytuje historię
przez API lokalnego Recorder, korzystając z istniejącej konfiguracji bazy HA.
Jeżeli sam Recorder korzysta ze zdalnej bazy, integracja korzysta z tej samej bazy.

Rzeczywiste agregaty pomiarów, znaczniki odbiorów i diagnostyka pozostają
w `/config/.storage/septic_forecast` oraz stanach HA. Nie są dodawane do Git.
Kopia zapasowa HA może zawierać te dane zgodnie z ustawieniami użytkownika.

Repozytorium zawiera kod, przykładowe identyfikatory encji, parametr wysokości
1,60 m, polskie etykiety i syntetyczne dane testowe. Nie zawiera bazy Recorder,
rzeczywistej historii, adresów instalacji, haseł, kluczy ani tokenów.
Nazwa konta GitHub w metadanych wskazuje publicznego opiekuna projektu.

HACS i GitHub są używane do instalacji i aktualizacji kodu. Ich pobieranie
odbywa się przez sieć; nie oznacza to wysyłania historii szamba przez integrację.

Przed zgłoszeniem problemu usuń z logów i zrzutów ekranu dane swojej instalacji.
Nie dodawaj do repozytorium plików `secrets.yaml`, `.env`, baz, kopii zapasowych
ani zawartości `.storage`.
