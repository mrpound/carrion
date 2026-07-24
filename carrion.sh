#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Parse args: --full anywhere enables the manual vetting worksheet; remaining
# positional args are <phone_number> [claimed_location].
FULL_MODE=0
POSITIONAL=()
for arg in "$@"; do
  case "$arg" in
    --full) FULL_MODE=1 ;;
    *) POSITIONAL+=("$arg") ;;
  esac
done

if [ ${#POSITIONAL[@]} -eq 0 ]; then
  echo "Usage: $0 <phone_number> [claimed_location] [--full]"
  echo "Example: $0 4704709474              (10-digit, country code added automatically)"
  echo "         $0 14704709474             (11-digit with country code)"
  echo "         $0 4704709474 \"Atlanta, GA\" (cross-check area code vs. claimed location)"
  echo "         $0 4704709474 \"Atlanta, GA\" --full (also run interactive vetting worksheet + log)"
  exit 1
fi

INPUT="${POSITIONAL[0]}"
CLAIMED_LOCATION="${POSITIONAL[1]:-}"
if [[ ${#INPUT} -eq 11 && "${INPUT:0:1}" == "1" ]]; then
  PHONE_NUMBER="$INPUT"
elif [[ ${#INPUT} -eq 10 ]]; then
  PHONE_NUMBER="1${INPUT}"
else
  PHONE_NUMBER="$INPUT"
fi

if [ -f .env ] && { [ -z "$TWILIO_ACCOUNT_SID" ] || [ -z "$TWILIO_AUTH_TOKEN" ]; }; then
  set -a
  while IFS='=' read -r key value; do
    if [[ "$key" =~ ^[[:space:]]*# ]] || [[ -z "$key" ]]; then
      continue
    fi
    value="${value%\"}"
    value="${value#\"}"
    export "$key=$value"
  done < .env
  set +a
fi

if [ -z "$TWILIO_ACCOUNT_SID" ]; then
  echo "Error: TWILIO_ACCOUNT_SID not found in environment variables or .env file"
  echo "Set the environment variable or create a .env file with:"
  echo "TWILIO_ACCOUNT_SID=your_account_sid"
  echo "TWILIO_AUTH_TOKEN=your_auth_token"
  exit 1
fi

if [ -z "$TWILIO_AUTH_TOKEN" ]; then
  echo "Error: TWILIO_AUTH_TOKEN not found in environment variables or .env file"
  echo "Set the environment variable or create a .env file with:"
  echo "TWILIO_ACCOUNT_SID=your_account_sid"
  echo "TWILIO_AUTH_TOKEN=your_auth_token"
  exit 1
fi

ACCOUNT_SID="$TWILIO_ACCOUNT_SID"
AUTH_TOKEN="$TWILIO_AUTH_TOKEN"

RESPONSE=$(curl -s -X GET "https://lookups.twilio.com/v2/PhoneNumbers/%2B${PHONE_NUMBER}?Fields=line_type_intelligence,sms_pumping_risk" \
  -u "${ACCOUNT_SID}:${AUTH_TOKEN}")

PHONE=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('phone_number','N/A'))")
NATIONAL=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('national_format','N/A'))")
COUNTRY=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('country_code') or 'N/A')")
CALLING_CC=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('calling_country_code') or 'N/A')")
VALID=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('valid'))")
CARRIER=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); c=d.get('line_type_intelligence') or {}; print(c.get('carrier_name') or 'N/A')")
TYPE=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); c=d.get('line_type_intelligence') or {}; print(c.get('type') or 'N/A')")
MCC=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); c=d.get('line_type_intelligence') or {}; print(c.get('mobile_country_code') or 'N/A')")
MNC=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); c=d.get('line_type_intelligence') or {}; print(c.get('mobile_network_code') or 'N/A')")
ERR=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); c=d.get('line_type_intelligence') or {}; v=c.get('error_code'); print(v if v is not None else 'None')")

# sms_pumping_risk fields
PUMP_SCORE=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); c=d.get('sms_pumping_risk') or {}; v=c.get('sms_pumping_risk_score'); print(v if v is not None else 'N/A')")
PUMP_CATEGORY=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); c=d.get('sms_pumping_risk') or {}; print(c.get('carrier_risk_category') or 'N/A')")
PUMP_BLOCKED=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); c=d.get('sms_pumping_risk') or {}; v=c.get('number_blocked'); print(v if v is not None else 'N/A')")

# Area code (NANP: first 3 digits after +1)
AREA_CODE=$(echo "$PHONE" | python3 -c "import sys,re; s=sys.stdin.read().strip(); m=re.match(r'^\+1(\d{3})', s); print(m.group(1) if m else 'N/A')")

# Resolve the area code to its registered US state and compare to the claimed
# location, if one was provided. Output: STATUS<tab>ABBR<tab>NAME
GEO_RESULT=$(python3 "$SCRIPT_DIR/areacodes.py" "$AREA_CODE" "$CLAIMED_LOCATION" 2>/dev/null)
GEO_STATUS=$(echo "$GEO_RESULT" | cut -f1)
GEO_STATE_ABBR=$(echo "$GEO_RESULT" | cut -f2)
GEO_STATE_NAME=$(echo "$GEO_RESULT" | cut -f3)

# VOIP/spam risk assessment
RISK_LEVEL="Low"
RISK_REASONS=()

if [[ "$VALID" == "False" ]]; then
  RISK_LEVEL="High"
  RISK_REASONS+=("Number is not a valid phone number")
fi

TYPE_UPPER=$(echo "$TYPE" | tr '[:lower:]' '[:upper:]')
if [[ "$TYPE_UPPER" == *"VOIP"* ]]; then
  RISK_LEVEL="High"
  RISK_REASONS+=("Number type is VoIP ($TYPE)")
fi

CARRIER_UPPER=$(echo "$CARRIER" | tr '[:lower:]' '[:upper:]')
for keyword in "TWILIO" "BANDWIDTH" "GOOGLE" "VONAGE" "MAGICJACK" "LINGO" "VOIP" "SKYPE" "TEXTPLUS" "TEXTNOW" "GOOGLE VOICE"; do
  if [[ "$CARRIER_UPPER" == *"$keyword"* ]]; then
    if [[ "$RISK_LEVEL" != "High" ]]; then
      RISK_LEVEL="High"
    fi
    RISK_REASONS+=("Carrier is a known VoIP/virtual provider: $CARRIER")
    break
  fi
done

# Geo check: caller wants US-based applicants. A +1 number can still be
# Canada / Caribbean (NANP), so verify the resolved country is actually US.
if [[ "$VALID" != "False" && "$COUNTRY" != "N/A" && "$COUNTRY" != "US" ]]; then
  RISK_LEVEL="High"
  RISK_REASONS+=("Number is not US-based (country: $COUNTRY)")
fi

# Area code vs. claimed location. Registration != residence (people move,
# overlays exist), so a mismatch only nudges to Medium as a prompt to verify.
if [[ "$GEO_STATUS" == "MISMATCH" ]]; then
  if [[ "$RISK_LEVEL" != "High" ]]; then
    RISK_LEVEL="Medium"
  fi
  RISK_REASONS+=("Area code $AREA_CODE is registered to $GEO_STATE_NAME, not the claimed location \"$CLAIMED_LOCATION\" — verify (people relocate)")
fi

# sms_pumping_risk: Twilio's fraud score (0-100). High score or a blocked
# number is a strong scam signal.
if [[ "$PUMP_BLOCKED" == "True" ]]; then
  RISK_LEVEL="High"
  RISK_REASONS+=("Number is on Twilio's SMS-pumping block list")
fi
if [[ "$PUMP_SCORE" =~ ^[0-9]+$ ]]; then
  if [[ "$PUMP_SCORE" -ge 66 ]]; then
    RISK_LEVEL="High"
    RISK_REASONS+=("High SMS-pumping/fraud risk score ($PUMP_SCORE/100)")
  elif [[ "$PUMP_SCORE" -ge 33 ]]; then
    if [[ "$RISK_LEVEL" != "High" ]]; then
      RISK_LEVEL="Medium"
    fi
    RISK_REASONS+=("Elevated SMS-pumping/fraud risk score ($PUMP_SCORE/100)")
  fi
fi

# No identifiable carrier data => treat as suspicious (at least Medium)
if [[ "$CARRIER" == "N/A" || -z "$CARRIER" || "$TYPE" == "N/A" || -z "$TYPE" || "$ERR" != "None" ]]; then
  if [[ "$RISK_LEVEL" != "High" ]]; then
    RISK_LEVEL="Medium"
  fi
  if [[ "$ERR" != "None" ]]; then
    RISK_REASONS+=("Carrier lookup returned an error code ($ERR) — carrier data unavailable")
  else
    RISK_REASONS+=("No identifiable carrier/type data returned")
  fi
fi

if [[ ${#RISK_REASONS[@]} -eq 0 ]]; then
  RISK_REASONS+=("Appears to be a standard mobile or landline number")
fi

# Color codes
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

if [[ "$RISK_LEVEL" == "High" ]]; then
  RISK_COLOR=$RED
  RISK_ICON="⚠️  HIGH"
elif [[ "$RISK_LEVEL" == "Medium" ]]; then
  RISK_COLOR=$YELLOW
  RISK_ICON="⚡ MEDIUM"
else
  RISK_COLOR=$GREEN
  RISK_ICON="✅ LOW"
fi

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║          PHONE NUMBER LOOKUP RESULTS         ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "${BOLD}📞 Number Info${RESET}"
echo -e "   E.164 Format  : ${CYAN}${PHONE}${RESET}"
echo -e "   Formatted     : ${NATIONAL}"
echo -e "   Country       : ${COUNTRY}"
echo -e "   Calling Code  : +${CALLING_CC}"
echo -e "   Area Code     : ${AREA_CODE}"
echo -e "   Valid         : ${VALID}"
echo ""
echo -e "${BOLD}🌍 Location Check${RESET}"
case "$GEO_STATUS" in
  KNOWN)
    echo -e "   Reg. Region   : ${GEO_STATE_NAME} (${GEO_STATE_ABBR})" ;;
  MATCH)
    echo -e "   Reg. Region   : ${GEO_STATE_NAME} (${GEO_STATE_ABBR})"
    echo -e "   Claimed       : ${CLAIMED_LOCATION}"
    echo -e "   Match         : ${GREEN}✓ area code matches claimed location${RESET}" ;;
  MISMATCH)
    echo -e "   Reg. Region   : ${GEO_STATE_NAME} (${GEO_STATE_ABBR})"
    echo -e "   Claimed       : ${CLAIMED_LOCATION}"
    echo -e "   Match         : ${YELLOW}✗ area code does not match claimed location${RESET}" ;;
  TOLLFREE)
    echo -e "   Reg. Region   : Toll-free / non-geographic number" ;;
  *)
    echo -e "   Reg. Region   : Unknown (area code not recognized)" ;;
esac
echo ""
echo -e "${BOLD}📡 Carrier Info${RESET}"
echo -e "   Name          : ${CARRIER}"
echo -e "   Type          : ${TYPE}"
echo -e "   MCC           : ${MCC}"
echo -e "   MNC           : ${MNC}"
echo -e "   Error Code    : ${ERR}"
echo ""
echo -e "${BOLD}🎣 SMS Pumping / Fraud${RESET}"
echo -e "   Risk Score    : ${PUMP_SCORE}"
echo -e "   Carrier Risk  : ${PUMP_CATEGORY}"
echo -e "   Blocked       : ${PUMP_BLOCKED}"
echo ""
echo -e "${BOLD}🚨 Spam / VoIP Risk${RESET}"
echo -e "   Risk Level    : ${RISK_COLOR}${RISK_ICON}${RESET}"
for reason in "${RISK_REASONS[@]}"; do
  echo -e "   • ${reason}"
done
echo ""
# Everything below runs only with --full: the interactive vetting worksheet,
# the composite verdict, and logging. A plain lookup stops at the phone checks.
if [ "$FULL_MODE" -eq 1 ]; then

# ── Manual vetting worksheet ────────────────────────────────────────────────
# Signals carrion can't check itself (LinkedIn authenticity, verifiable work
# history, resume/profile consistency). Answer y for each RED FLAG present.
MANUAL_FLAGS=0
MANUAL_CODES=""

ask_flag() {
  local prompt="$1" code="$2" answer=""
  read -r -p "   $prompt [y/N] " answer
  if [[ "$answer" =~ ^[Yy] ]]; then
    MANUAL_FLAGS=$((MANUAL_FLAGS + 1))
    MANUAL_CODES="${MANUAL_CODES:+$MANUAL_CODES,}$code"
  fi
}

if [ -t 0 ] && [ -z "$CARRION_NO_PROMPT" ]; then
  echo -e "${BOLD}📝 Manual Vetting (answer y for each red flag present)${RESET}"
  ask_flag "No LinkedIn, or profile looks copied/altered?" "LINKEDIN"
  ask_flag "Past roles unverifiable online?" "ROLES"
  ask_flag "Resume generic or doesn't match LinkedIn?" "RESUME_DRIFT"
  echo ""
else
  MANUAL_CODES="skipped"
fi

# ── Composite verdict ───────────────────────────────────────────────────────
# Combine the automated phone risk with the manual flags into an overall
# "how hard should I look" signal. This is a decision aid, not a verdict —
# the reasons above are what matter.
case "$RISK_LEVEL" in
  High)   PHONE_POINTS=2 ;;
  Medium) PHONE_POINTS=1 ;;
  *)      PHONE_POINTS=0 ;;
esac
TOTAL_POINTS=$((PHONE_POINTS + MANUAL_FLAGS))

if [[ "$TOTAL_POINTS" -ge 3 ]]; then
  FINAL_VERDICT="HIGH"
  FINAL_COLOR=$RED
  FINAL_ICON="⚠️  HIGH — multiple independent red flags, scrutinize hard"
elif [[ "$TOTAL_POINTS" -eq 2 ]]; then
  FINAL_VERDICT="MEDIUM"
  FINAL_COLOR=$YELLOW
  FINAL_ICON="⚡ MEDIUM — some signals, verify before proceeding"
elif [[ "$TOTAL_POINTS" -eq 1 ]]; then
  FINAL_VERDICT="LOW"
  FINAL_COLOR=$YELLOW
  FINAL_ICON="• LOW — one minor signal; see notes above"
else
  FINAL_VERDICT="LOW"
  FINAL_COLOR=$GREEN
  FINAL_ICON="✅ LOW — nothing notable flagged"
fi

echo -e "${BOLD}🧮 Composite Verdict${RESET}"
echo -e "   Phone Risk    : ${RISK_LEVEL}"
echo -e "   Manual Flags  : ${MANUAL_FLAGS} (${MANUAL_CODES:-none})"
echo -e "   Overall       : ${FINAL_COLOR}${FINAL_ICON}${RESET}"
echo ""

# ── Log the result ──────────────────────────────────────────────────────────
LOG_FILE="$SCRIPT_DIR/vetting-log.tsv"
if [ ! -f "$LOG_FILE" ]; then
  printf 'timestamp\tphone\tnational\tcountry\tarea_code\treg_state\tclaimed_location\tgeo_status\ttype\tcarrier\tpump_score\tphone_risk\tmanual_flags\tmanual_codes\tfinal_verdict\n' > "$LOG_FILE"
fi
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
  "$TIMESTAMP" "$PHONE" "$NATIONAL" "$COUNTRY" "$AREA_CODE" "$GEO_STATE_ABBR" \
  "${CLAIMED_LOCATION:-}" "$GEO_STATUS" "$TYPE" "$CARRIER" "$PUMP_SCORE" \
  "$RISK_LEVEL" "$MANUAL_FLAGS" "${MANUAL_CODES:-none}" "$FINAL_VERDICT" >> "$LOG_FILE"
echo -e "   ${CYAN}Logged to ${LOG_FILE}${RESET}"
echo ""

fi  # end --full

echo -e "${BOLD}🧾 Full API Response${RESET}"
echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
echo ""
