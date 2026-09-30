"""booking_config.py — tunable settings (what "healthy" and "top performer" mean).

This is the one place a salon adjusts the product to its own norms. Everything
downstream reads from here, so changing a number here changes the whole scorecard
consistently. All thresholds are percentages unless noted.
"""

# Minimum appointments before a sliced rate or finding is trusted.
MIN_SUPPORT = 25

# --- Health-check absolute guardrails ---
NOSHOW_WATCH, NOSHOW_ACT = 8.0, 12.0      # no-show rate: watch above 8%, act above 12%
CANCEL_WATCH, CANCEL_ACT = 10.0, 15.0     # cancellation rate
IDLE_WATCH, IDLE_ACT = 40.0, 55.0         # idle time between appointments
UTIL_LOW = 45.0                           # a staffer below this looks under-utilised

# --- Relative effect sizes vs the business's OWN average (ignore smaller gaps) ---
EFF_CANCEL_SVC = 5.0     # a service this many points above the avg cancel rate
EFF_UTIL = 10.0          # a staffer this many points below the team's avg utilisation
EFF_REBOOK = 10.0        # a staffer this many points below salon-wide rebooking
EFF_NOSHOW_SRC = 5.0     # a booking source this many points above the rest

# --- Growth-potential score weights (should sum to 1) ---
GROWTH_W_TREND, GROWTH_W_YIELD, GROWTH_W_RELIAB = 0.4, 0.3, 0.3

# --- Star-performer score weights: utilisation, rebooking, revenue/hr (sum to 1) ---
STAR_W_UTIL, STAR_W_REBOOK, STAR_W_YIELD = 0.34, 0.33, 0.33

# --- Most-improved: min completed appointments per half-period to qualify,
#     and the minimum % revenue gain to be worth recognising. ---
IMPROVED_MIN_PER_PERIOD = 15
IMPROVED_MIN_PCT = 10.0

# Where the weekly history is stored (local SQLite file).
BOOKING_HISTORY_DB = "outputs/booking_history.db"

# Prime-time yield: $/hr gap (overall minus peak) to watch / act on.
PRIME_GAP_WATCH, PRIME_GAP_ACT = 4.0, 8.0

# Structural/recurring areas — framed "ongoing"; they do not by themselves
# set the verdict to "needs attention".
CHRONIC_AREAS = ["Schedule gaps"]

# Smallest revenue move ($) worth calling out as a driver / decline.
TREND_MIN_DELTA = 200.0
