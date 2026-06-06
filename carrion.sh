#!/bin/bash

if [ -z "$1" ]; then
  echo "Usage: $0 <phone_number>"
  echo "Example: $0 4704709474  (10-digit, country code added automatically)"
  echo "         $0 14704709474 (11-digit with country code)"
  exit 1
fi

INPUT="$1"
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

RESPONSE=$(curl -s -X GET "https://lookups.twilio.com/v1/PhoneNumbers/%2B${PHONE_NUMBER}?Type=carrier" \
  -u "${ACCOUNT_SID}:${AUTH_TOKEN}")

PHONE=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('phone_number','N/A'))")
NATIONAL=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('national_format','N/A'))")
COUNTRY=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('country_code','N/A'))")
CARRIER=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); c=d.get('carrier',{}); print(c.get('name','N/A') if c else 'N/A')")
TYPE=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); c=d.get('carrier',{}); print(c.get('type','N/A') if c else 'N/A')")
MCC=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); c=d.get('carrier',{}); print(c.get('mobile_country_code','N/A') if c else 'N/A')")
MNC=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); c=d.get('carrier',{}); print(c.get('mobile_network_code','N/A') if c else 'N/A')")
ERR=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); c=d.get('carrier',{}); v=c.get('error_code') if c else None; print(v if v is not None else 'None')")

# VOIP/spam risk assessment
RISK_LEVEL="Low"
RISK_REASONS=()

TYPE_UPPER=$(echo "$TYPE" | tr '[:lower:]' '[:upper:]')
if [[ "$TYPE_UPPER" == "VOIP" ]]; then
  RISK_LEVEL="High"
  RISK_REASONS+=("Number type is VoIP")
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
echo ""
echo -e "${BOLD}📡 Carrier Info${RESET}"
echo -e "   Name          : ${CARRIER}"
echo -e "   Type          : ${TYPE}"
echo -e "   MCC           : ${MCC}"
echo -e "   MNC           : ${MNC}"
echo -e "   Error Code    : ${ERR}"
echo ""
echo -e "${BOLD}🚨 Spam / VoIP Risk${RESET}"
echo -e "   Risk Level    : ${RISK_COLOR}${RISK_ICON}${RESET}"
for reason in "${RISK_REASONS[@]}"; do
  echo -e "   • ${reason}"
done
echo ""
