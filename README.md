# ONVIF Camera Control 0.2.0 (portabel betaversjon)

Egendefinert Home Assistant-integrasjon for **ONVIF Media1-videoinnstillinger**. Kan registrere flere kameraer, lese sensorverdier, endre H.264-oppløsning, FPS og I-frame-intervall, og endre bitrate når sikre kameraspesifikke grenser er kjent.

Dette er en **beta** basert på en allerede fungerende F5G-installasjon. Den nye, generelle Media2-oppdagelsen og flere forskjellige kameramodeller er *testet med simulerte svar, ikke mot fysiske kameraer*. Den erstatter ikke Home Assistants vanlige `ONVIF`-integrasjon for livevideo.

## Innhold

- `custom_components/onvif_camera_control/`: selve integrasjonen
- `tools/generate_dashboard.py`: lager dashboard-YAML ut fra entitetsregisteret på HA, uten ekstra avhengigheter
- `examples/f5g_dashboard_v3.yaml`: dagens dashboard for F5G (ikke generelt)
- `examples/f5g_profiler.yaml`: valgfritt F5G-profiloppsett (ikke generelt)
- `tests/`: offline regresjonstester

## Installasjon på en annen Home Assistant

1. Ta en sikkerhetskopi av Home Assistant. Kopier mappen `custom_components/onvif_camera_control/` til `/config/custom_components/onvif_camera_control/`. Ikke kopier `tests` og `examples` inn i `custom_components`.
2. Kjør `ha core check && ha core restart` i Home Assistant Terminal & SSH, eller start HA fra brukergrensesnittet.
3. Under **Innstillinger → Enheter og tjenester → Legg til integrasjon** velger du **ONVIF Camera Control**. Legg til kameraets IP/vertsnavn, ONVIF-port og innlogging. Gjenta for hvert kamera.
4. For videobildet: legg samme kamera inn i Home Assistants vanlige **ONVIF**-integrasjon. Finn riktig `camera.`-entitet i **Utviklerverktøy → Tilstander**.
5. Kopier `tools/generate_dashboard.py` til `/config/onvif_generate_dashboard.py`. Kjør først:

   ```bash
   python3 /config/onvif_generate_dashboard.py
   ```

   Dette oppretter `/config/onvif_kontrollpanel.yaml` uten videobilde og skriver ut config-entry-ID-ene.

6. Kjør deretter generatoren med kameraets faktiske entitet, og om ønskelig navn:

   ```bash
   python3 /config/onvif_generate_dashboard.py --overwrite \
     --camera 'ENTRY_ID=camera.ditt_kamera' --name 'ENTRY_ID=Salong'
   ```

   For flere kameraer legger du til et `--camera ENTRY_ID=camera.entitet` og et valgfritt `--name ENTRY_ID=Navn` per kamera. `ENTRY_ID` hentes fra utskriften i steg 5. Generatoren lager faner for alle registrerte kameraer og en felles oversikt.

7. Opprett et **tomt** Home Assistant-kontrollpanel med URL-sti `onvif-kontroll`. Åpne **Rå konfigurasjonseditor**, lim inn hele innholdet fra `/config/onvif_kontrollpanel.yaml`, og lagre. Dashboardets URL må samsvare med generatorens `--dashboard-url` (standard `/onvif-kontroll`) for at oversiktsknappene skal navigere riktig.
8. Når et nytt kamera er registrert, kjør generatoren på nytt med `--overwrite`, og lim den oppdaterte filen inn i dashboard-editoren. **Dette skjer ikke automatisk**. Overskriving lager en datostemplet `.bak`.

Ingen tilgang til `.storage` skrives av generatoren, og den leser bare `.storage/core.entity_registry`, ikke `core.config_entries` med passord. Den velger ikke automatisk riktig videobilde for et kamera, fordi den vanlige ONVIF-integrasjonen har egne entiteter.

## Oppgradering av eksisterende F5G-installasjon

1. Ta backup av `/config/custom_components/onvif_camera_control/`, `/config/packages/onvif_f5g_profiler.yaml` og dashboard-YAML. Pass på at eksisterende script og dashboard fortsetter å ligge der de er.
2. Erstatt kun `custom_components/onvif_camera_control/` med den nye versjonen. **Ikke fjern den gamle config entry**: unike ID-er for sensor, select og number er bevart.
3. Start Home Assistant på nytt etter `ha core check`. Sjekk de eksisterende sensorene og kontrollene.
4. Bitrate forsøkes nå oppdaget via Media2 i stedet for å være hardkodet til `192.168.1.100`. Hvis `Bitrate` mangler, gå til **Innstillinger → Enheter og tjenester → ONVIF Camera Control → Konfigurer**, sett min `64` og maks `2048` for dette F5G-kameraet, og lagre. Dette er en **per-kamera** reserveinnstilling; den bør bare settes når grensene er bekreftet for kameraet.
5. La ditt eksisterende F5G-dashboard og profilskript stå urørt. De fungerer videre med samme entitets-ID-er. Ny dashboard-generator kan tas i bruk senere ved behov.

## Funksjoner og avgrensninger

- **Oppløsning, FPS, I-frame:** Hentes fra og skrives til ONVIF Media1. Styring tilbys der H.264-options rapporteres.
- **Bitrate:** Leser ONVIF Media2-alternativer per videokoding og oppløsning. Prøver en konfigurasjonsspesifikk forespørsel, deretter generiske alternativer hvis token ikke støttes; avviser motstridende eller ukjente grenser. Noen kameraer krever særskilt autentisering eller annonserer ikke Media2. Da kan man bruke manuelle grenser i **Konfigurer**. Begge grenseverdier `0` gir automatikk.
- **Begrensninger:** Den manuelle grensen gjelder alle H.264-strømmer på ett kamera; pass på at den er gyldig for alle. Media2 WS-Security UsernameToken er et beste-forsøk og er ikke garantert å fungere mot alle produsenter eller ulik klokke på kameraene. Bare lokale/private kameraendepunkter med samsvarende host aksepteres. Ikke støttede bitratekontroller utelates.
- **Strømmer:** Fanges opp basert på encoder-konfigurasjoner, ikke faste `VEToken_1` / `VEToken_2`-navn. Visningsnavn ordnes ved første innlesning etter oppløsningsstørrelse. Profilnavn fra ONVIF er også tilgjengelige internt. Fysisk testing anbefales for kameraer med flere lignende profiler.
- **Skriving:** Endringer kontrolleres før sending, serialiseres per kamera og leses tilbake. Ved ny oppløsning kontrolleres bitrategrensene på nytt. Kameraets videostrøm kan kortvarig falle ut under endring.
- **F5G-profilknapper:** Eksemplene under `examples/` er spesialtilpasset den opprinnelige installasjonen og blir *ikke* installert automatisk på andre HA-systemer. Nye kameraer trenger egne verifiserte profilvalg før knapper opprettes. Valgfritt kan generatoren legge inn knapper med `--preset 'ENTRY_ID=Høy kvalitet:script.ditt_script'`.
- **Navn:** Eksisterende `unique_id` er bevart. Home Assistant kan beholde manuelt endrede visningsnavn i sitt entitetsregister, som ikke overskrives.

## Sikkerhet og vedlikehold

Kopier aldri `.storage/core.config_entries` eller hemmeligheter inn i en distribusjonspakke. Media2-klienten tillater ikke omdirigeringer, sjekker at tjenesteadressen peker mot kameraets adresse og begrenser XML-svar til 1 MiB. Ingen konfigurasjonsendringer sendes automatisk under installasjon. Ta en backup før du bruker betaversjonen i produksjon.

## Utvikling og testing

Det er ingen avhengighet til Home Assistant for enhetstestene. Kjør i prosjektroten:

```bash
python3 -m compileall -q custom_components tools tests
python3 -m pytest tests -q
```

Disse er **offline tester**. Kjør `ha core check` på den faktiske installasjonen, og test hver kameramodell forsiktig før du tar den i produksjon. Full HA-livssyklustest og fysisk kameratest er ikke utført på denne byggemaskinen.

## Lisens og kommersiell bruk

**PolyForm Noncommercial License 1.0.0** (se [LICENSE](LICENSE)). Prosjektet er tilgjengelig for personlige og andre ikke-kommersielle formål under vilkårene i lisensen. **Kommersiell bruk er ikke tillatt uten separat skriftlig tillatelse fra rettighetshaveren.** Dette er en *source-available* lisens, ikke en OSI-godkjent åpen kildekode-lisens.

Required Notice: Copyright (c) 2026 l4r53n

## HACS

Prosjektstrukturen inneholder `hacs.json` og er klargjort for et eget Git-repository. Det er **ikke publisert i HACS**. Legg pakken i et GitHub-repository, publiser en versjon og legg repositoriet til som en egendefinert integrasjon dersom du senere vil installere via HACS.

## GitHub and HACS beta testing

See [GITHUB_SETUP.md](GITHUB_SETUP.md) for publishing the repository and installing it
as a HACS custom repository. Run `python3 tools/configure_github.py USERNAME`
before the initial public push to populate the GitHub URLs and code owner in the
integration manifest. HACS installs only the custom component, not the dashboard
or example camera profiles.
