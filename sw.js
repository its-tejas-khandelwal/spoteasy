name: Keep SpotEasy Awake

on:
  schedule:
    - cron: '*/14 * * * *'   # Every 14 minutes — GitHub allows min 5 mins
  workflow_dispatch:           # Manual trigger anytime

jobs:
  wake:
    runs-on: ubuntu-latest
    steps:
      - name: Wake SpotEasy (Render)
        run: |
          echo "🏓 Pinging SpotEasy at $(date '+%d %b %Y %H:%M IST')"
          # First ping — wakes the server
          curl -s -o /dev/null -w "Status: %{http_code} | Time: %{time_total}s\n" \
            https://parksmart-india.onrender.com/health || true
          echo "Waiting 20 seconds for server to fully wake..."
          sleep 20
          # Second ping — confirms it's up
          RESPONSE=$(curl -s https://parksmart-india.onrender.com/health || echo "failed")
          echo "Response: $RESPONSE"
          if echo "$RESPONSE" | grep -q "ok"; then
            echo "✅ SpotEasy is LIVE and running!"
          else
            echo "⚠️ Server still waking up — will retry next cycle"
          fi
