from __future__ import annotations

LOGIN_INSTRUCTIONS = (
    "Et nettleservindu åpner seg nå.\n"
    "Logg inn på Studentweb slik du pleier, med ID-porten eller Feide.\n"
    "autofag ser aldri passordet, fødselsnummeret eller PIN-koden din.\n"
    "Når du er inne, tar autofag over av seg selv."
)
LOGIN_DONE = "Innlogget. Økten ligger i din egen lokale nettleserprofil."
LOGIN_FAILED = "Fikk ikke logget inn: {reason}"

SEARCH_PROMPT = "Søk etter emne (emnekode eller navn, tom linje for å gå videre)"
SEARCH_FILTER_SUBJECT = "Begrens til fag (valgfritt)"
SEARCH_FILTER_FACULTY = "Begrens til fakultet (valgfritt)"
SEARCH_NO_HITS = "Ingen treff. Prøv et annet søk."
SEARCH_HITS = "{shown} av {total} treff"
SEARCH_MORE_PAGES = "Det finnes flere sider med treff. Snevre inn søket for å se resten."

SELECT_COURSES = "Velg emnene du vil overvåke (mellomrom for å velge, enter for å bekrefte)"
SELECT_NONE_YET = "Du har ikke valgt noen emner ennå."
SELECT_ADDED = "Lagt til: {codes}"
SEARCH_AGAIN = "Vil du søke etter flere emner?"

WATCH_OPENS_AT = "Vet du når påmeldingen åpner for {code}? (ÅÅÅÅ-MM-DD TT:MM, tom for nei)"
WATCH_BAD_TIMESTAMP = "Forsto ikke tidspunktet. Hopper over det."

CHANNELS_SELECT = "Hvordan vil du varsles?"
CHANNEL_LABELS = {
    "ntfy": "ntfy.sh (push til mobil)",
    "email": "E-post",
    "sms": "SMS via Twilio",
    "macos": "macOS-varsel",
}
CHANNEL_NTFY_TOPIC = "ntfy-topic (hold den hemmelig, den er nøkkelen til varslene dine)"
CHANNEL_NTFY_SERVER = "ntfy-server"
CHANNEL_EMAIL_HOST = "SMTP-vert"
CHANNEL_EMAIL_PORT = "SMTP-port"
CHANNEL_EMAIL_USERNAME = "SMTP-brukernavn"
CHANNEL_EMAIL_PASSWORD = "SMTP-passord"
CHANNEL_EMAIL_RECIPIENT = "Send e-post til"
CHANNEL_SMS_SID = "Twilio account SID"
CHANNEL_SMS_TOKEN = "Twilio auth token"
CHANNEL_SMS_FROM = "Twilio-nummer du sender fra"
CHANNEL_SMS_TO = "Telefonnummer som skal varsles"

CHANNEL_TEST_SENDING = "Sender en testvarsling på {channel} ..."
CHANNEL_TEST_CONFIRM = "Kom testvarslingen fram på {channel}?"
CHANNEL_TEST_FAILED = "{channel} svarte: {detail}"
CHANNEL_TEST_RETRY = "Vil du prøve å sette opp {channel} på nytt?"
CHANNEL_NONE_WORKING = (
    "Ingen kanaler virker. Da finner du aldri ut at en plass ble ledig, så autofag stopper her."
)

TEST_NOTIFICATION_TITLE = "autofag virker"
TEST_NOTIFICATION_BODY = "Dette er en testvarsling fra autofag. Du trenger ikke gjøre noe."

REVIEW_HEADER = "Klar til å starte"
REVIEW_COURSES = "Emner"
REVIEW_CHANNELS = "Varsling"
REVIEW_AUTO_ENROLL = "Auto-påmelding"
REVIEW_AUTO_ENROLL_ON = "på for alle emnene i lista"
REVIEW_AUTO_ENROLL_DRY = "av (tørrkjøring, stopper før bekreftelsen)"
REVIEW_CONFIRM = "Starter overvåkingen?"
REVIEW_ABORTED = "Avbrutt. Ingenting er lagret."

WATCH_STARTED = "Overvåker {count} emne(r). La vinduet stå åpent, eller kjør autofag watch senere."
WATCH_NOTHING_TO_DO = "Ingen aktive emner å overvåke. Kjør autofag init først."

DOCTOR_OK = "Alt ser riktig ut. Studentweb-release {release}, {rows} rad(er) parset."
DOCTOR_NO_ROWS = "Fant ingen rader med gjenkjent status. Studentweb har trolig endret seg."
DOCTOR_CHANNELS = "Kanaler: {channels}"

LOGOUT_DONE = "Nettleserprofilen er slettet. Kjør autofag init for å logge inn igjen."
STATUS_EMPTY = "Watchlisten er tom."

NOTIFY_AVAILABLE_TITLE = "Ledig plass: {code}"
NOTIFY_AVAILABLE_BODY = "{code} {name} har ledig plass på undervisningen nå."
NOTIFY_SESSION_EXPIRED_TITLE = "autofag mistet innloggingen"
NOTIFY_SESSION_EXPIRED_BODY = (
    "Kjør `autofag init` for å logge inn igjen. Overvåkingen står stille inntil da."
)
NOTIFY_BUDGET_TITLE = "autofag har brukt opp timesbudsjettet"
NOTIFY_BUDGET_BODY = "{detail}. Overvåkingen er satt på pause."
NOTIFY_UNKNOWN_STATUS_TITLE = "Ukjent status for {code}"
NOTIFY_UNKNOWN_STATUS_BODY = (
    "Studentweb svarte med tekst autofag ikke kjenner igjen:\n{text}\n"
    "Legg frasen inn i status_vocabulary i config."
)

ENROLL_CONFIRMED = "Påmeldt {code}"
ENROLL_WAITLISTED = "Venteliste på {code}"
ENROLL_FULL = "{code} ble fullt før vi rakk det"
ENROLL_REJECTED = "{code} avviste påmeldingen"
ENROLL_UNVERIFIED = "{code}: bekreft manuelt"
ENROLL_ABORTED = "{code}: påmelding avbrutt"
ENROLL_DISABLED = "auto-påmelding er slått av"
ENROLL_ALREADY_DONE = "allerede meldt på i denne kjøringen"
ENROLL_TOO_MANY_UNVERIFIED = "for mange ubekreftede forsøk"
ENROLL_NO_ATTEMPT = "ingen forsøk ble gjort"
ENROLL_VERIFIED_AFTER_DROP = "verifisert etter avbrutt forsøk"
ENROLL_COULD_NOT_VERIFY = "{detail}; kunne ikke verifisere: {error}"
ENROLL_COURSE_MISSING = "{detail}; emnet ble ikke funnet"
