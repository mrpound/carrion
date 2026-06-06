# carrion

Twilio-powered phone number toolkit with carrier lookup and calling capabilities.

## Scripts

- **`carrion.sh`** - Phone number lookup tool to analyze carrier information and assess VoIP/spam risk
- **`caller.sh`** - Simple calling script to make test calls using Twilio

## Features

- Phone number validation and formatting
- Carrier information lookup (name, type, MCC, MNC)
- VoIP and spam risk assessment
- Test calling functionality
- Pretty terminal output

## Setup

### Prerequisites

- `curl` (for API requests)
- `python3` (for JSON parsing)
- Twilio account with API credentials

### Configuration

Set your Twilio credentials using either method:

**Option 1: Environment Variables**
```bash
export TWILIO_ACCOUNT_SID="your_account_sid"
export TWILIO_AUTH_TOKEN="your_auth_token"
```

**Option 2: .env File**
Create a `.env` file in the same directory:
```bash
TWILIO_ACCOUNT_SID="your_account_sid"
TWILIO_AUTH_TOKEN="your_auth_token"
TWILIO_FROM_NUMBER="+1234567890"  # Required for caller.sh
```

## Usage

### Phone Number Lookup (`carrion.sh`)

```bash
./carrion.sh <phone_number>
```

**Examples:**
```bash
./carrion.sh 4704709474      # 10-digit (country code added automatically)
./carrion.sh 14704709474     # 11-digit with country code
```

### Making Test Calls (`caller.sh`)

```bash
./caller.sh <phone_number>
```

**Examples:**
```bash
./caller.sh 4704709474       # Makes a test call saying "Hello"
./caller.sh 14704709474      # 11-digit format also supported
```

## Output

### carrion.sh Output

The lookup tool provides:

- **Number Info**: E.164 format, national format, country code
- **Carrier Info**: Name, type, mobile codes, error codes
- **Risk Assessment**: VoIP/spam risk level with reasoning

### caller.sh Output

The calling script shows:

- Call details (to/from numbers)
- Raw Twilio API response
- Parsed call information (SID, status) or error details

Risk levels:
- 🟢 **LOW**: Standard mobile or landline
- 🟡 **MEDIUM**: Potential risk indicators
- 🔴 **HIGH**: VoIP or known virtual providers

## Risk Assessment

Will flag numbers as high risk if they are:
- VoIP type numbers
- From known virtual providers (Twilio, Google Voice, TextNow, etc.)

## Requirements
- Valid Twilio account credentials
