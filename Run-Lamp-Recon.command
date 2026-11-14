#!/bin/zsh
# Double-click this file in Finder.
#
# It switches this Mac to the lamp's own Wi-Fi, runs the offline Meross
# recon/control tool, then switches back to the home Wi-Fi automatically.
#
# The assistant connection will drop for roughly 30-60 seconds while the
# Mac is on the lamp's access point. The script keeps running locally.
cd "$(dirname "$0")" || exit 1

if [[ -f lamp_env.sh ]]; then
  source lamp_env.sh
fi
LAMP_SSID="${LAMP_SSID:-Meross_XXXXXX}"
HOME_SSID="${HOME_SSID:-YOUR_HOME_WIFI}"

echo "============================================================"
echo " LampControll automatic recon"
echo "============================================================"
echo
echo "  Lamp AP:  $LAMP_SSID"
echo "  Home:     $HOME_SSID"
echo
echo "The lamp should visibly switch off and on once, turn green,"
echo "then return to its original state."
echo
echo "The assistant connection will drop while this Mac is on the"
echo "lamp's Wi-Fi. It comes back automatically when the script"
echo "reconnects to $HOME_SSID."
echo
read -r "?Press Enter to start..."

old_ip=$(ipconfig getifaddr en0 2>/dev/null || true)
echo
echo "Current IP: ${old_ip:-none}"

# If we are already on a 10.x lamp network, skip the switch.
if [[ "$old_ip" == 10.* ]]; then
  echo "Already on a 10.x network; assuming the lamp AP."
else
  echo "Switching Wi-Fi to $LAMP_SSID ..."
  networksetup -setairportnetwork en0 "$LAMP_SSID"
  sleep 3
fi

# Wait for a new DHCP lease (the lamp normally hands out 10.10.10.x).
lamp_ip=""
for i in {1..30}; do
  candidate=$(ipconfig getifaddr en0 2>/dev/null || true)
  if [[ -n "$candidate" && "$candidate" != "$old_ip" ]]; then
    lamp_ip="$candidate"
    break
  fi
  sleep 1
done

if [[ -z "$lamp_ip" ]]; then
  echo
  echo "ERROR: no DHCP lease from $LAMP_SSID."
  echo "Please connect to $LAMP_SSID manually in the Wi-Fi menu,"
  echo "then run: python3 tools/lamp_recon.py --control --color 00ff00"
  echo
  echo "Switching back to $HOME_SSID ..."
  networksetup -setairportnetwork en0 "$HOME_SSID"
  read -r "?Press Enter to close..."
  exit 1
fi

echo "Lamp AP IP: $lamp_ip"
echo
python3 tools/lamp_recon.py --control --color 00ff00
status=$?

echo
echo "Switching back to $HOME_SSID ..."
networksetup -setairportnetwork en0 "$HOME_SSID"
sleep 3
home_ip=""
for i in {1..30}; do
  candidate=$(ipconfig getifaddr en0 2>/dev/null || true)
  if [[ "$candidate" == 192.168.* ]]; then
    home_ip="$candidate"
    break
  fi
  sleep 1
done

echo
echo "------------------------------------------------------------"
if [[ -n "$home_ip" ]]; then
  echo "Back on $HOME_SSID ($home_ip)."
else
  echo "WARNING: could not confirm the home Wi-Fi connection."
  echo "Please reconnect to $HOME_SSID manually in the Wi-Fi menu."
fi
if [ $status -eq 0 ]; then
  echo "Lamp control verified. Report:"
else
  echo "Lamp control not confirmed (exit $status). Report:"
fi
echo "  $(pwd)/reports/lamp_report.txt"
echo
echo "Tell the assistant: done."
echo
read -r "?Press Enter to close this window..."
