#!/bin/zsh
# Onboarding fallback: switch the Mac to the lamp AP, send the home Wi-Fi
# credentials through the Meross local API, switch back, then find and
# control the lamp over the home LAN.
#
# Everything is logged to reports/onboard_run.log, so even if the assistant
# connection drops during the Wi-Fi switch, the full run can be inspected
# afterwards.
cd "$(dirname "$0")" || exit 1

if [[ -f lamp_env.sh ]]; then
  source lamp_env.sh
fi
LAMP_SSID="${LAMP_SSID:-Meross_XXXXXX}"
HOME_SSID="${HOME_SSID:-YOUR_HOME_WIFI}"
LAMP_UUID="${LAMP_UUID:-YOUR_LAMP_UUID}"
LAMP_MAC="${LAMP_MAC:-aa:bb:cc:dd:ee:ff}"
HOME_BSSID="${HOME_BSSID:-aa:bb:cc:dd:ee:ff}"
HOME_CHANNEL="${HOME_CHANNEL:-1}"
HOME_ENCRYPTION="${HOME_ENCRYPTION:-6}"
HOME_CIPHER="${HOME_CIPHER:-3}"

mkdir -p reports
LOG="$(pwd)/reports/onboard_run.log"
exec > >(tee -a "$LOG") 2>&1

PASS_FILE="/tmp/lampcontroll_wifi_pass.$$"
cleanup() {
  rm -f "$PASS_FILE"
}
trap cleanup EXIT INT TERM

reconnect_home() {
  local candidate
  for attempt in 1 2 3; do
    echo "Reconnecting to $HOME_SSID (attempt $attempt) ..."
    networksetup -setairportnetwork en0 "$HOME_SSID" 2>&1
    sleep 3
    for i in {1..15}; do
      candidate=$(ipconfig getifaddr en0 2>/dev/null || true)
      if [[ "$candidate" == 192.168.* ]]; then
        home_ip="$candidate"
        echo "Back on $HOME_SSID ($home_ip)."
        return 0
      fi
      sleep 1
    done
    echo "Still not back; power-cycling Wi-Fi ..."
    networksetup -setairportpower en0 off 2>&1
    sleep 3
    networksetup -setairportpower en0 on 2>&1
    sleep 5
  done
  return 1
}

echo "============================================================"
echo " LampControll onboarding"
echo "============================================================"
echo
echo "This switches the Mac to $LAMP_SSID, sends your saved"
echo "$HOME_SSID Wi-Fi password to the lamp once, switches back,"
echo "then finds and controls the lamp over the home LAN."
echo
echo "The assistant connection drops for about 1-2 minutes."
echo "The password is kept in a 0600 temp file and deleted on exit."
echo "Log: $LOG"
echo
read -r "?Continue? [y/N] " answer
if [[ ! "$answer" =~ ^[Yy]$ ]]; then
  echo "Cancelled."
  exit 0
fi

echo
echo "Reading the saved Wi-Fi password from the keychain ..."
if ! security find-generic-password -D "AirPort network password" -a "$HOME_SSID" -w > "$PASS_FILE" 2>/dev/null; then
  echo "Keychain read failed or was denied."
  printf "Home Wi-Fi password for %s: " "$HOME_SSID"
  read -r -s WIFI_PASS
  echo
  printf '%s' "$WIFI_PASS" > "$PASS_FILE"
fi
chmod 600 "$PASS_FILE"
if [[ ! -s "$PASS_FILE" ]]; then
  echo "No password available; aborting."
  exit 1
fi

old_ip=$(ipconfig getifaddr en0 2>/dev/null || true)
echo
echo "Current IP: ${old_ip:-none}"

if [[ "$old_ip" == 10.* ]]; then
  echo "Already on a 10.x network; assuming the lamp AP."
  lamp_ip="$old_ip"
else
  lamp_ip=""
  for attempt in 1 2; do
    echo "Switching Wi-Fi to $LAMP_SSID (attempt $attempt) ..."
    networksetup -setairportnetwork en0 "$LAMP_SSID" 2>&1
    sleep 3
    for i in {1..20}; do
      candidate=$(ipconfig getifaddr en0 2>/dev/null || true)
      if [[ -n "$candidate" && "$candidate" != "$old_ip" ]]; then
        lamp_ip="$candidate"
        break
      fi
      sleep 1
    done
    [[ -n "$lamp_ip" ]] && break
    echo "No lease yet; power-cycling Wi-Fi ..."
    networksetup -setairportpower en0 off 2>&1
    sleep 3
    networksetup -setairportpower en0 on 2>&1
    sleep 5
  done
fi

if [[ -z "$lamp_ip" ]]; then
  echo "ERROR: could not join $LAMP_SSID."
  reconnect_home
  read -r "?Press Enter to close..."
  exit 1
fi
echo "Lamp AP IP: $lamp_ip"

echo
python3 tools/lamp_onboard.py \
  --host 10.10.10.1 \
  --password-file "$PASS_FILE" \
  --ssid "$HOME_SSID" \
  --uuid "$LAMP_UUID" \
  --mac "$LAMP_MAC" \
  --bssid "$HOME_BSSID" \
  --channel "$HOME_CHANNEL" \
  --encryption "$HOME_ENCRYPTION" \
  --cipher "$HOME_CIPHER"
onboard_status=$?
rm -f "$PASS_FILE"

echo
if ! reconnect_home; then
  echo "WARNING: could not confirm the home Wi-Fi connection."
  echo "Please reconnect to $HOME_SSID manually."
  read -r "?Press Enter to close..."
  exit 1
fi

if [ $onboard_status -ne 0 ]; then
  echo "Onboarding was not acknowledged (exit $onboard_status)."
  echo "See the log: $LOG"
  read -r "?Press Enter to close..."
  exit $onboard_status
fi

echo
echo "Waiting for the lamp to appear on the home LAN ..."
lan_status=1
for i in {1..8}; do
  if python3 tools/lamp_lan.py \
    --uuid "$LAMP_UUID" \
    --mac "$LAMP_MAC" \
    --control \
    --color ffffff; then
    lan_status=0
    break
  fi
  echo "  not found yet; retrying in 8s ($i/8)"
  sleep 8
done

echo
echo "------------------------------------------------------------"
if [ $lan_status -eq 0 ]; then
  echo "SUCCESS: the lamp is on the home LAN and responded to control."
else
  echo "The lamp did not appear on the home LAN yet."
  echo "It may still be connecting. Run: python3 tools/lamp_lan.py --control"
fi
echo "Log:     $LOG"
echo "Report:  $(pwd)/reports/lan_report.txt"
echo
read -r "?Press Enter to close this window..."
