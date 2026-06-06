#!/bin/bash

if [ -z "$1" ]; then
  echo "Usage: $0 <10-digit-number>"
  exit 1
fi

INPUT="$1"
if [[ ${#INPUT} -eq 10 ]]; then
  TO="1${INPUT}"
elif [[ ${#INPUT} -eq 11 ]]; then
  TO="$INPUT"
else
  TO="$INPUT"
fi

if [ -f .env ] && { [ -z "$TWILIO_ACCOUNT_SID" ] || [ -z "$TWILIO_AUTH_TOKEN" ] || [ -z "$TWILIO_FROM_NUMBER" ]; }; then
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
  echo "TWILIO_FROM_NUMBER=+1234567890"
  exit 1
fi

if [ -z "$TWILIO_AUTH_TOKEN" ]; then
  echo "Error: TWILIO_AUTH_TOKEN not found in environment variables or .env file"
  echo "Set the environment variable or create a .env file with:"
  echo "TWILIO_ACCOUNT_SID=your_account_sid"
  echo "TWILIO_AUTH_TOKEN=your_auth_token"
  echo "TWILIO_FROM_NUMBER=+1234567890"
  exit 1
fi

if [ -z "$TWILIO_FROM_NUMBER" ]; then
  echo "Error: TWILIO_FROM_NUMBER not found in environment variables or .env file"
  echo "Set the environment variable or create a .env file with:"
  echo "TWILIO_ACCOUNT_SID=your_account_sid"
  echo "TWILIO_AUTH_TOKEN=your_auth_token"
  echo "TWILIO_FROM_NUMBER=+1234567890"
  exit 1
fi

ACCOUNT_SID="$TWILIO_ACCOUNT_SID"
AUTH_TOKEN="$TWILIO_AUTH_TOKEN"
FROM="$TWILIO_FROM_NUMBER"

echo "Making call to: +${TO} from: ${FROM}"

RESPONSE=$(curl -s -X POST "https://api.twilio.com/2010-04-01/Accounts/${ACCOUNT_SID}/Calls.json" \
  -u "${ACCOUNT_SID}:${AUTH_TOKEN}" \
  --data-urlencode "To=+${TO}" \
  --data-urlencode "From=${FROM}" \
  --data-urlencode "Twiml=<Response><Say>Hello</Say></Response>")

echo "Raw response:"
echo "$RESPONSE"
echo ""

echo "$RESPONSE" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    if 'code' in d:
        print('ERROR:', d.get('message', 'Unknown error'))
        print('Code :', d.get('code', 'N/A'))
    else:
        print('SID    :', d.get('sid', 'N/A'))
        print('Status :', d.get('status', 'N/A'))
        print('To     :', d.get('to', 'N/A'))
        print('From   :', d.get('from', 'N/A'))
except json.JSONDecodeError:
    print('Invalid JSON response')
"
