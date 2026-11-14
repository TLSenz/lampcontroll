# Copy to lamp_env.sh and fill in your own values.
# The scripts source lamp_env.sh automatically when it exists.
export LAMP_SSID="Meross_XXXXXX"       # lamp's setup access point
export HOME_SSID="YOUR_HOME_WIFI"      # 2.4 GHz home network
export LAMP_UUID="YOUR_LAMP_UUID"      # from Appliance.System.All
export LAMP_MAC="aa:bb:cc:dd:ee:ff"
export HOME_BSSID="aa:bb:cc:dd:ee:ff"
export HOME_CHANNEL=1                   # 2.4 GHz channel 1-13
export HOME_ENCRYPTION=6                # WPA2 PSK
export HOME_CIPHER=3                    # CCMP
